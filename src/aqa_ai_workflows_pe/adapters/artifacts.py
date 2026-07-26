from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from ..domain.models import ContextPack, ReviewRoundState


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self.root.chmod(0o700)

    def assessment_dir(self, assessment_id: str, *, create: bool = True) -> Path:
        try:
            parsed = UUID(assessment_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("Invalid assessment identifier") from exc
        if str(parsed) != assessment_id:
            raise ValueError("Invalid assessment identifier")
        path = self.root / assessment_id
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                path.chmod(0o700)
        return path

    def write_context(self, pack: ContextPack) -> Path:
        path = self.assessment_dir(pack.assessment_id) / "context-pack.json"
        self.write_text(path, pack.model_dump_json(indent=2))
        return path

    def read_context(self, assessment_id: str) -> ContextPack:
        path = self.assessment_dir(assessment_id, create=False) / "context-pack.json"
        return ContextPack.model_validate_json(path.read_text(encoding="utf-8"))

    def write_review_state(self, assessment_id: str, state: ReviewRoundState) -> Path:
        path = self.assessment_dir(assessment_id, create=False) / "review-round-state.json"
        self.write_text(path, state.model_dump_json(indent=2))
        return path

    def read_review_state(self, assessment_id: str) -> ReviewRoundState | None:
        path = self.assessment_dir(assessment_id, create=False) / "review-round-state.json"
        if not path.is_file():
            return None
        return ReviewRoundState.model_validate_json(path.read_text(encoding="utf-8"))

    def clear_review_state(self, assessment_id: str) -> None:
        path = self.assessment_dir(assessment_id) / "review-round-state.json"
        if path.is_file():
            path.unlink()

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def delete(self, assessment_id: str) -> None:
        path = self.assessment_dir(assessment_id, create=False)
        if path.is_dir() and path.parent == self.root:
            shutil.rmtree(path)

    def files(self, assessment_id: str) -> list[Path]:
        path = self.assessment_dir(assessment_id, create=False)
        if not path.is_dir():
            return []
        return sorted(item for item in path.iterdir() if item.is_file())
