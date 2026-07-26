import os
import sqlite3
import stat

import pytest

from aqa_ai_workflows_pe.adapters.persistence import AssessmentStore
from aqa_ai_workflows_pe.domain.models import AIModelProfile, AssessmentStatus, utc_now


def test_assessment_lifecycle(settings, review_request) -> None:
    store = AssessmentStore(settings.paths.database)
    created = store.create("11111111-1111-1111-1111-111111111111", review_request)
    assert created.status == AssessmentStatus.QUEUED
    store.update(created.id, AssessmentStatus.CONTEXT, 35, "Building context")
    loaded = store.get(created.id)
    assert loaded is not None
    assert loaded.progress == 35
    assert loaded.request.provider.model == "deterministic-demo-v1"
    assert store.integrity_check() == "ok"
    assert store.delete(created.id)
    assert store.get(created.id) is None


def test_credentials_are_not_in_persisted_request(settings, review_request) -> None:
    store = AssessmentStore(settings.paths.database)
    store.create("22222222-2222-2222-2222-222222222222", review_request)
    raw = settings.paths.database.read_bytes()
    assert b"provider_key" not in raw
    assert b"github_token" not in raw


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not available")
def test_local_database_is_private(settings) -> None:
    AssessmentStore(settings.paths.database)

    assert stat.S_IMODE(settings.paths.database.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings.paths.data.stat().st_mode) == 0o700


def test_ready_assessment_can_update_its_selected_profile(settings, review_request) -> None:
    store = AssessmentStore(settings.paths.database)
    created = store.create("33333333-3333-3333-3333-333333333333", review_request)
    store.update(created.id, AssessmentStatus.READY, 45, "Ready for approval")
    replacement = review_request.model_copy(
        update={
            "provider": review_request.provider.model_copy(
                update={"model": "replacement-model", "profile_id": "profile-two"}
            )
        }
    )

    assert store.update_request(created.id, replacement)
    assert store.get(created.id).request.provider.model == "replacement-model"

    store.update(created.id, AssessmentStatus.REVIEWING, 52, "Reviewing")
    assert not store.update_request(created.id, review_request)


def test_ai_model_profile_lifecycle_and_default_selection(settings) -> None:
    store = AssessmentStore(settings.paths.database)
    created_at = utc_now()
    first = AIModelProfile(
        id="profile-one",
        label="Primary model",
        provider="fake",
        model="deterministic-demo-v1",
        credential_source="none",
        destination_class="local",
        created_at=created_at,
        updated_at=created_at,
    )
    created_first = store.create_ai_profile(first)
    assert created_first.is_default

    second = first.model_copy(
        update={
            "id": "profile-two",
            "label": "Secondary model",
            "model": "deterministic-demo-v2",
            "is_default": True,
        }
    )
    store.create_ai_profile(second)
    profiles = store.list_ai_profiles()
    assert profiles[0].id == "profile-two"
    assert profiles[0].is_default
    assert not store.get_ai_profile("profile-one").is_default

    updated = profiles[0].model_copy(update={"label": "Updated model"})
    assert store.update_ai_profile(updated).label == "Updated model"
    assert store.delete_ai_profile("profile-two")
    assert store.get_ai_profile("profile-one").is_default


def test_schema_v1_is_migrated_for_ai_profiles(settings) -> None:
    with sqlite3.connect(settings.paths.database) as connection:
        connection.execute("CREATE TABLE schema_meta (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_meta(version) VALUES (1)")

    store = AssessmentStore(settings.paths.database)
    with sqlite3.connect(settings.paths.database) as connection:
        version = connection.execute("SELECT version FROM schema_meta").fetchone()[0]
        profile_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_model_profiles'"
        ).fetchone()
    assert version == 2
    assert profile_table is not None
    assert store.list_ai_profiles() == []
