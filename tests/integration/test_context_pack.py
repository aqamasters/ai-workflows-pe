from __future__ import annotations

import subprocess
from pathlib import Path

from aqa_ai_workflows_pe.adapters.context import ContextEngine
from aqa_ai_workflows_pe.adapters.git import BareRepository, GitRunner
from aqa_ai_workflows_pe.domain.models import (
    ChangedFile,
    ContextRequest,
    PullRequestMetadata,
    RepositoryPin,
    SourceKind,
)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_builds_bounded_evidence_and_redacts(settings, tmp_path: Path) -> None:
    working = tmp_path / "working"
    working.mkdir()
    git("init", "-b", "main", cwd=working)
    git("config", "user.email", "test@example.invalid", cwd=working)
    git("config", "user.name", "Test", cwd=working)
    (working / "src").mkdir()
    (working / "tests").mkdir()
    (working / "src" / "retry.py").write_text(
        "API_KEY = 'synthetic-secret-value-123456'\nATTEMPTS = 3\n",
        encoding="utf-8",
    )
    (working / "tests" / "test_retry.py").write_text("def test_retry(): pass\n", encoding="utf-8")
    (working / "operations").mkdir()
    (working / "operations" / "idempotency-notes.txt").write_text(
        "Payment attempt identifiers must remain stable across retries.\n", encoding="utf-8"
    )
    (working / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    git("add", ".", cwd=working)
    git("commit", "-m", "Fixture", cwd=working)
    sha = git("rev-parse", "HEAD", cwd=working)
    bare = tmp_path / "repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(working), str(bare)], check=True, capture_output=True
    )
    pin = RepositoryPin(
        alias="primary",
        owner="acme",
        repository="shop",
        commit_sha=sha,
        source_kind=SourceKind.PRIMARY_REPOSITORY,
        relationship="Primary",
        clone_url="https://github.com/acme/shop.git",
    )
    metadata = PullRequestMetadata(
        owner="acme",
        repository="shop",
        number=1,
        url="https://github.com/acme/shop/pull/1",
        title="Increase retry attempts",
        body="Retry transient payment failures.",
        author="dev",
        draft=False,
        state="open",
        base_sha=sha,
        head_sha=sha,
        base_ref="main",
        head_ref="change",
        clone_url=pin.clone_url,
        changed_files=[
            ChangedFile(path="src/retry.py", status="modified", patch="-ATTEMPTS=2\n+ATTEMPTS=3")
        ],
    )
    engine = ContextEngine(settings)
    engine.register(pin, BareRepository(bare, GitRunner(settings), settings))
    pack = engine.build("33333333-3333-3333-3333-333333333333", metadata, "Checkout")
    assert pack.repositories[0].commit_sha == sha
    assert any(item.path == "tests/test_retry.py" for item in pack.evidence)
    assert any(item.path == "pyproject.toml" for item in pack.evidence)
    assert all("synthetic-secret-value" not in item.content for item in pack.evidence)
    assert sum(item.redactions for item in pack.evidence) >= 1

    resumed_engine = ContextEngine(settings)
    resumed_engine.register(pin, BareRepository(bare, GitRunner(settings), settings))
    expanded = resumed_engine.resolve_requests(
        pack,
        [
            ContextRequest(
                repository_alias="primary",
                kind="documentation",
                query="idempotency notes",
                reason="Confirm the retry identity contract.",
            )
        ],
    )
    assert any(item.path == "operations/idempotency-notes.txt" for item in expanded.evidence)
    assert len({item.id for item in expanded.evidence}) == len(expanded.evidence)
