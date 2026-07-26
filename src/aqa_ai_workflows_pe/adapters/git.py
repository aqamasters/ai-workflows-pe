from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, overload

from ..config import Settings
from ..domain.errors import RepositoryError
from ..domain.models import RepositoryPin

SAFE_CONFIG = (
    "-c",
    "credential.helper=",
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.safecrlf=false",
    "-c",
    "filter.lfs.smudge=",
    "-c",
    "filter.lfs.process=",
    "-c",
    "filter.lfs.required=false",
    "-c",
    "diff.external=",
    "-c",
    "core.commitGraph=false",
    "-c",
    "gc.writeCommitGraph=false",
    "-c",
    "fetch.writeCommitGraph=false",
)


@dataclass(frozen=True, slots=True)
class TreeEntry:
    mode: str
    kind: str
    object_id: str
    size: int
    path: str


class GitRunner:
    def __init__(self, settings: Settings, token: str = "") -> None:
        self.settings = settings
        self.token = token
        self.git = shutil.which("git")
        if not self.git:
            raise RepositoryError("Git 2.42 or newer is required and was not found on PATH.")
        package = Path(__file__).resolve().parents[1]
        self.askpass = (
            package / "resources" / ("git-askpass.cmd" if os.name == "nt" else "git-askpass")
        )
        if not self.askpass.is_file():
            raise RepositoryError("The installed Git credential helper is missing.")
        self.disabled_hooks = settings.paths.cache / "disabled-hooks"
        self.disabled_hooks.mkdir(parents=True, exist_ok=True)

    @overload
    def run(
        self,
        arguments: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 300,
        text: Literal[True] = True,
    ) -> subprocess.CompletedProcess[str]: ...

    @overload
    def run(
        self,
        arguments: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 300,
        text: Literal[False],
    ) -> subprocess.CompletedProcess[bytes]: ...

    def run(
        self,
        arguments: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 300,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
        command = [
            self.git,
            *SAFE_CONFIG,
            "-c",
            f"core.hooksPath={self.disabled_hooks}",
            *arguments,
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": str(self.askpass),
                "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PROTOCOL_FROM_USER": "0",
                "GIT_ALLOW_PROTOCOL": "https",
                "AQA_GIT_TOKEN": self.token,
            }
        )
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=text,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RepositoryError("Git timed out while reading the repository.") from exc
        if result.returncode != 0:
            stderr = result.stderr if text else result.stderr.decode("utf-8", errors="replace")
            safe_error = _sanitize_git_error(stderr, self.token)
            raise RepositoryError(f"Git could not read the repository: {safe_error}")
        return result


def _sanitize_git_error(value: str, token: str) -> str:
    clean = value.replace(token, "[REDACTED]") if token else value
    clean = clean.replace("\r", " ").replace("\n", " ").strip()
    return clean[:800] or "unknown Git error"


class BareRepository:
    def __init__(self, path: Path, runner: GitRunner, settings: Settings) -> None:
        self.path = path
        self.runner = runner
        self.settings = settings

    def fetch(self, pin: RepositoryPin, *, pull_number: int | None = None) -> None:
        refspec = (
            f"+refs/pull/{pull_number}/head:refs/aqa/pull/{pull_number}"
            if pull_number
            else pin.commit_sha
        )
        self._run_fetch(refspec)
        self.assert_commit(pin.commit_sha)

    def fetch_commit(self, commit_sha: str) -> None:
        if not _is_object_id(commit_sha):
            raise RepositoryError("GitHub returned an invalid commit identifier.")
        try:
            self.assert_commit(commit_sha)
            return
        except RepositoryError:
            pass
        self._run_fetch(commit_sha)
        self.assert_commit(commit_sha)

    def _run_fetch(self, refspec: str) -> None:
        arguments = [
            "--git-dir",
            str(self.path),
            "fetch",
            "--no-tags",
            "--force",
            "--filter=blob:none",
            "origin",
            refspec,
        ]
        try:
            self.runner.run(arguments, timeout=600)
        except RepositoryError as exc:
            error_text = str(exc).lower()
            if (
                "--refetch" in error_text
                or "commit-graph" in error_text
                or "object database" in error_text
                or "bad object" in error_text
                or "did not send all necessary objects" in error_text
            ):
                self.runner.run([*arguments, "--refetch"], timeout=600)
            else:
                raise

    def assert_commit(self, commit_sha: str) -> None:
        if not _is_object_id(commit_sha):
            raise RepositoryError("GitHub returned an invalid commit identifier.")
        self.runner.run(["--git-dir", str(self.path), "cat-file", "-e", f"{commit_sha}^{{commit}}"])

    def tree(self, commit_sha: str) -> list[TreeEntry]:
        self.assert_commit(commit_sha)
        result = self.runner.run(
            ["--git-dir", str(self.path), "ls-tree", "-r", "-z", "-l", commit_sha],
            text=False,
            timeout=600,
        )
        entries: list[TreeEntry] = []
        for record in result.stdout.split(b"\0"):
            if not record:
                continue
            header, raw_path = record.split(b"\t", 1)
            mode, kind, object_id, raw_size = header.decode("ascii").split(" ", 3)
            path = raw_path.decode("utf-8", errors="replace")
            if not _safe_repo_path(path):
                continue
            raw_size = raw_size.strip()
            size = int(raw_size) if raw_size.isdigit() else -1
            entries.append(TreeEntry(mode, kind, object_id, size, path))
            if len(entries) > self.settings.limits.tree_entries_per_repo:
                raise RepositoryError(
                    "Repository tree exceeds the configured 100,000-entry safety limit."
                )
        return entries

    def read_blob(self, entry: TreeEntry) -> str:
        if entry.kind != "blob" or not _is_object_id(entry.object_id):
            raise RepositoryError("Refusing to read a non-blob Git object.")
        if entry.size < 0 or entry.size > self.settings.limits.blob_bytes:
            return ""
        result = self.runner.run(
            ["--git-dir", str(self.path), "cat-file", "blob", entry.object_id],
            text=False,
            timeout=60,
        )
        payload = result.stdout
        if len(payload) > self.settings.limits.blob_bytes or b"\0" in payload[:8_192]:
            return ""
        return payload.decode("utf-8", errors="replace")


class GitCache:
    def __init__(self, settings: Settings, token: str = "") -> None:
        self.settings = settings
        self.runner = GitRunner(settings, token)

    def prepare(self, pin: RepositoryPin, *, pull_number: int | None = None) -> BareRepository:
        key = hashlib.sha256(f"github.com/{pin.slug}".casefold().encode()).hexdigest()[:24]
        path = self.settings.paths.repositories / f"{key}.git"
        if not path.exists():
            self._clone(pin.clone_url, path)

        repository = BareRepository(path, self.runner, self.settings)
        try:
            repository.assert_commit(pin.commit_sha)
        except RepositoryError:
            try:
                repository.fetch(pin, pull_number=pull_number)
            except RepositoryError:
                # If fetch fails even after internal retries, delete the cache and try once more.
                # We remove the directory completely to clear any deep corruption.
                if path.exists():
                    try:
                        shutil.rmtree(path)
                    except OSError:
                        shutil.rmtree(path, ignore_errors=True)
                self._clone(pin.clone_url, path)
                repository.fetch(pin, pull_number=pull_number)
        return repository

    def _clone(self, clone_url: str, path: Path) -> None:
        self.runner.run(
            [
                "clone",
                "--bare",
                "--filter=blob:none",
                "--no-tags",
                "--no-checkout",
                clone_url,
                str(path),
            ],
            timeout=600,
        )


def _is_object_id(value: str) -> bool:
    return len(value) in {40, 64} and all(character in "0123456789abcdef" for character in value)


def _safe_repo_path(value: str) -> bool:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts
