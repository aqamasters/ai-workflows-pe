from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ..domain.models import (
    AIModelProfile,
    AssessmentStatus,
    AssessmentSummary,
    CanonicalReview,
    ReviewRequest,
    utc_now,
)

SCHEMA_VERSION = 2


class AssessmentStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA secure_delete=ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
            row = connection.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
                stored_version = SCHEMA_VERSION
            else:
                stored_version = int(row["version"])
            if stored_version not in {1, SCHEMA_VERSION}:
                raise RuntimeError(
                    "Unsupported local database version. Run `aqa-ai-workflows repair`."
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS assessments (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_assessments_updated ON assessments(updated_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_model_profiles (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    base_url TEXT NOT NULL DEFAULT '',
                    credential_source TEXT NOT NULL,
                    destination_class TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_model_profiles_default
                ON ai_model_profiles(is_default) WHERE is_default = 1
                """
            )
            if stored_version == 1:
                connection.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
            terminal = (
                AssessmentStatus.COMPLETE.value,
                AssessmentStatus.FAILED.value,
                AssessmentStatus.CANCELLED.value,
                AssessmentStatus.READY.value,
            )
            now = utc_now().isoformat()
            connection.execute(
                """
                UPDATE assessments
                SET status = ?, progress = 100,
                    message = 'The previous local process stopped before completion.',
                    error = 'Interrupted. Start a new assessment; cached repositories can be reused.',
                    updated_at = ?
                WHERE status NOT IN (?, ?, ?, ?)
                """,
                (AssessmentStatus.FAILED.value, now, *terminal),
            )
        if os.name != "nt":
            self.path.chmod(0o600)

    def create(self, assessment_id: str, request: ReviewRequest) -> AssessmentSummary:
        now = utc_now()
        summary = AssessmentSummary(
            id=assessment_id,
            status=AssessmentStatus.QUEUED,
            progress=0,
            message="Queued locally",
            created_at=now,
            updated_at=now,
            request=request,
        )
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO assessments(
                    id, status, progress, message, created_at, updated_at, request_json, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    summary.id,
                    summary.status.value,
                    summary.progress,
                    summary.message,
                    summary.created_at.isoformat(),
                    summary.updated_at.isoformat(),
                    request.model_dump_json(),
                ),
            )
        return summary

    def update(
        self,
        assessment_id: str,
        status: AssessmentStatus,
        progress: int,
        message: str,
        *,
        result: CanonicalReview | None = None,
        error: str = "",
    ) -> None:
        result_json = result.model_dump_json() if result else None
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE assessments
                SET status = ?, progress = ?, message = ?, updated_at = ?,
                    result_json = COALESCE(?, result_json), error = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    progress,
                    message,
                    utc_now().isoformat(),
                    result_json,
                    error,
                    assessment_id,
                ),
            )

    def get(self, assessment_id: str) -> AssessmentSummary | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
            ).fetchone()
        return _row_to_summary(row) if row else None

    def update_request(self, assessment_id: str, request: ReviewRequest) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE assessments
                SET request_json = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    request.model_dump_json(),
                    utc_now().isoformat(),
                    assessment_id,
                    AssessmentStatus.READY.value,
                ),
            )
        return cursor.rowcount > 0

    def list(self, limit: int = 20) -> list[AssessmentSummary]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM assessments ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_summary(row) for row in rows]

    def delete(self, assessment_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute("DELETE FROM assessments WHERE id = ?", (assessment_id,))
        return cursor.rowcount > 0

    def create_ai_profile(self, profile: AIModelProfile) -> AIModelProfile:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing_count = int(
                    connection.execute("SELECT COUNT(*) FROM ai_model_profiles").fetchone()[0]
                )
                make_default = profile.is_default or existing_count == 0
                if make_default:
                    connection.execute("UPDATE ai_model_profiles SET is_default = 0")
                connection.execute(
                    """
                    INSERT INTO ai_model_profiles(
                        id, label, provider, model, base_url, credential_source,
                        destination_class, is_default, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile.id,
                        profile.label,
                        profile.provider.value,
                        profile.model,
                        profile.base_url,
                        profile.credential_source,
                        profile.destination_class,
                        int(make_default),
                        profile.created_at.isoformat(),
                        profile.updated_at.isoformat(),
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return profile.model_copy(update={"is_default": make_default})

    def update_ai_profile(self, profile: AIModelProfile) -> AIModelProfile | None:
        updated = profile.model_copy(update={"updated_at": utc_now()})
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT id FROM ai_model_profiles WHERE id = ?", (profile.id,)
                ).fetchone()
                if existing is None:
                    connection.execute("ROLLBACK")
                    return None
                if updated.is_default:
                    connection.execute("UPDATE ai_model_profiles SET is_default = 0")
                connection.execute(
                    """
                    UPDATE ai_model_profiles
                    SET label = ?, provider = ?, model = ?, base_url = ?,
                        credential_source = ?, destination_class = ?, is_default = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        updated.label,
                        updated.provider.value,
                        updated.model,
                        updated.base_url,
                        updated.credential_source,
                        updated.destination_class,
                        int(updated.is_default),
                        updated.updated_at.isoformat(),
                        updated.id,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return updated

    def get_ai_profile(self, profile_id: str) -> AIModelProfile | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM ai_model_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        return _row_to_ai_profile(row) if row else None

    def list_ai_profiles(self) -> list[AIModelProfile]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM ai_model_profiles ORDER BY is_default DESC, updated_at DESC"
            ).fetchall()
        return [_row_to_ai_profile(row) for row in rows]

    def set_default_ai_profile(self, profile_id: str) -> bool:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT id FROM ai_model_profiles WHERE id = ?", (profile_id,)
                ).fetchone()
                if existing is None:
                    connection.execute("ROLLBACK")
                    return False
                connection.execute("UPDATE ai_model_profiles SET is_default = 0")
                connection.execute(
                    "UPDATE ai_model_profiles SET is_default = 1, updated_at = ? WHERE id = ?",
                    (utc_now().isoformat(), profile_id),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return True

    def delete_ai_profile(self, profile_id: str) -> bool:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT is_default FROM ai_model_profiles WHERE id = ?", (profile_id,)
                ).fetchone()
                if row is None:
                    connection.execute("ROLLBACK")
                    return False
                connection.execute("DELETE FROM ai_model_profiles WHERE id = ?", (profile_id,))
                if bool(row["is_default"]):
                    replacement = connection.execute(
                        "SELECT id FROM ai_model_profiles ORDER BY updated_at DESC LIMIT 1"
                    ).fetchone()
                    if replacement:
                        connection.execute(
                            "UPDATE ai_model_profiles SET is_default = 1 WHERE id = ?",
                            (replacement["id"],),
                        )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return True

    def integrity_check(self) -> str:
        with self._lock, self._connection() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"


def _row_to_summary(row: sqlite3.Row) -> AssessmentSummary:
    result = CanonicalReview.model_validate_json(row["result_json"]) if row["result_json"] else None
    return AssessmentSummary(
        id=str(row["id"]),
        status=AssessmentStatus(str(row["status"])),
        progress=int(row["progress"]),
        message=str(row["message"]),
        created_at=datetime.fromisoformat(str(row["created_at"])).astimezone(UTC),
        updated_at=datetime.fromisoformat(str(row["updated_at"])).astimezone(UTC),
        request=_request_from_json(str(row["request_json"])),
        result=result,
        error=str(row["error"]),
    )


def _row_to_ai_profile(row: sqlite3.Row) -> AIModelProfile:
    return AIModelProfile.model_validate(
        {
            "id": str(row["id"]),
            "label": str(row["label"]),
            "provider": str(row["provider"]),
            "model": str(row["model"]),
            "base_url": str(row["base_url"]),
            "credential_source": str(row["credential_source"]),
            "destination_class": str(row["destination_class"]),
            "is_default": bool(row["is_default"]),
            "created_at": datetime.fromisoformat(str(row["created_at"])).astimezone(UTC),
            "updated_at": datetime.fromisoformat(str(row["updated_at"])).astimezone(UTC),
        }
    )


def _request_from_json(payload: str) -> ReviewRequest:
    """Read persisted v1 requests without reviving retired credential sources."""
    data = json.loads(payload)
    provider = data.get("provider") if isinstance(data, dict) else None
    if isinstance(provider, dict) and provider.get("credential_source") not in {"keyring", "none"}:
        provider["credential_source"] = "none"
    return ReviewRequest.model_validate(data)
