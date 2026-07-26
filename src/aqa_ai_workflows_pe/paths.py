from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_data_path, user_log_path

PRODUCT_NAME = "AQA AI Workflows Public Edition"
PRODUCT_AUTHOR = "AQA Masters"
DATA_DIR_ENV = "AQA_AI_WORKFLOWS_DATA_DIR"


@dataclass(frozen=True, slots=True)
class AppPaths:
    data: Path
    cache: Path
    logs: Path
    database: Path
    artifacts: Path
    repositories: Path

    @classmethod
    def discover(cls) -> AppPaths:
        override = os.getenv(DATA_DIR_ENV, "").strip()
        data = (
            Path(override).expanduser().resolve()
            if override
            else user_data_path(PRODUCT_NAME, PRODUCT_AUTHOR)
        )
        cache = data / "cache" if override else user_cache_path(PRODUCT_NAME, PRODUCT_AUTHOR)
        logs = data / "logs" if override else user_log_path(PRODUCT_NAME, PRODUCT_AUTHOR)
        return cls(
            data=data,
            cache=cache,
            logs=logs,
            database=data / "state.sqlite3",
            artifacts=data / "assessments",
            repositories=cache / "repositories",
        )

    def ensure(self) -> None:
        for path in (self.data, self.cache, self.logs, self.artifacts, self.repositories):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                path.chmod(0o700)
