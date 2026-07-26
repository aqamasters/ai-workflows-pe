from __future__ import annotations

import os
from dataclasses import dataclass

from .paths import AppPaths


@dataclass(frozen=True, slots=True)
class Limits:
    related_repositories: int = 3
    tree_entries_per_repo: int = 100_000
    blob_bytes: int = 512 * 1024
    evidence_units: int = 1_500
    provider_input_tokens: int = 200_000
    provider_response_bytes: int = 8 * 1024 * 1024
    extra_context_rounds: int = 2
    risks: int = 20
    scenarios: int = 50


@dataclass(frozen=True, slots=True)
class Settings:
    paths: AppPaths
    limits: Limits = Limits()
    github_api_base: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"
    log_level: str = "INFO"
    network_timeout_seconds: float = 45.0
    provider_timeout_seconds: float = 240.0

    @classmethod
    def load(cls) -> Settings:
        return cls(
            paths=AppPaths.discover(),
            log_level=os.getenv("AQA_AI_WORKFLOWS_LOG_LEVEL", "INFO").upper(),
        )
