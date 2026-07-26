from __future__ import annotations

import subprocess
from pathlib import Path

from aqa_ai_workflows_pe.adapters.git import BareRepository, GitRunner


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def test_reads_tree_and_blobs_without_checkout(settings, tmp_path: Path) -> None:
    working = tmp_path / "working"
    working.mkdir()
    run("init", "-b", "main", cwd=working)
    run("config", "user.email", "test@example.invalid", cwd=working)
    run("config", "user.name", "Test", cwd=working)
    (working / "src").mkdir()
    (working / "src" / "policy.py").write_text("ATTEMPTS = 3\n", encoding="utf-8")
    run("add", ".", cwd=working)
    run("commit", "-m", "Initial", cwd=working)
    sha = run("rev-parse", "HEAD", cwd=working)
    bare = tmp_path / "repository.git"
    subprocess.run(
        ["git", "clone", "--bare", str(working), str(bare)], check=True, capture_output=True
    )

    repository = BareRepository(bare, GitRunner(settings), settings)
    tree = repository.tree(sha)
    assert [item.path for item in tree] == ["src/policy.py"]
    assert repository.read_blob(tree[0]) == "ATTEMPTS = 3\n"
    assert not (bare / "src").exists()
