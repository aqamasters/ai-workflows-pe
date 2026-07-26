from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

import aqa_ai_workflows_pe.web as web_module
from aqa_ai_workflows_pe.web import WebState, create_app


def _client(settings, monkeypatch):
    credentials: dict[str, str] = {}
    monkeypatch.setattr(
        web_module,
        "persist_profile_key",
        lambda profile_id, value: credentials.__setitem__(profile_id, value),
    )
    monkeypatch.setattr(
        web_module,
        "resolve_profile_key",
        lambda profile_id: credentials.get(profile_id, ""),
    )
    monkeypatch.setattr(
        web_module,
        "profile_key_is_configured",
        lambda profile_id: bool(credentials.get(profile_id)),
    )
    monkeypatch.setattr(
        web_module,
        "delete_profile_key",
        lambda profile_id: credentials.pop(profile_id, None),
    )
    state = WebState(settings)
    return TestClient(create_app(settings, state)), state, credentials


def _authenticate(client: TestClient, state: WebState) -> None:
    response = client.get(f"/?launch={state.launch_secret}", follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies.get("aqa_ai_workflows_session") == state.launch_secret


def test_private_launch_and_browser_security_headers(settings, monkeypatch) -> None:
    client, state, _ = _client(settings, monkeypatch)

    assert client.get("/profile").status_code == 401
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in health.headers["content-security-policy"]

    _authenticate(client, state)
    assert client.get("/profile").status_code == 200
    assert client.get("/", headers={"host": "attacker.example"}).status_code == 400
    blocked = client.post(
        "/profile/ai-models",
        headers={"origin": "https://attacker.example"},
        data={"csrf_token": state.csrf_token},
    )
    assert blocked.status_code == 403


def test_profile_is_the_only_ai_credential_entry_path(settings, monkeypatch) -> None:
    client, state, credentials = _client(settings, monkeypatch)
    _authenticate(client, state)

    rejected = client.post(
        "/profile/ai-models",
        data={"csrf_token": "expired", "provider": "openai", "model": "gpt-test"},
    )
    assert rejected.status_code == 400
    assert "local form expired" in rejected.text.casefold()

    created = client.post(
        "/profile/ai-models",
        follow_redirects=False,
        data={
            "csrf_token": state.csrf_token,
            "label": "Production model",
            "provider": "openai",
            "model": "gpt-test",
            "api_key": "test-provider-secret",
            "is_default": "1",
        },
    )
    assert created.status_code == 303
    profile = state.store.list_ai_profiles()[0]
    assert credentials[profile.id] == "test-provider-secret"
    assert b"test-provider-secret" not in settings.paths.database.read_bytes()

    home = client.get("/")
    assert home.status_code == 200
    assert "Production model" in home.text
    assert "API key stored in OS credential manager" in home.text
    assert "test-provider-secret" not in home.text

    removed = client.post(
        f"/profile/ai-models/{profile.id}/credential/delete",
        follow_redirects=False,
        data={"csrf_token": state.csrf_token},
    )
    assert removed.status_code == 303
    assert profile.id not in credentials
    assert "No AI model configured yet" in client.get("/").text


def test_profile_creation_rolls_back_keyring_when_metadata_write_fails(
    settings, monkeypatch
) -> None:
    client, state, credentials = _client(settings, monkeypatch)
    _authenticate(client, state)

    def fail_metadata_write(_):
        raise RuntimeError("simulated metadata failure")

    monkeypatch.setattr(state.store, "create_ai_profile", fail_metadata_write)
    response = client.post(
        "/profile/ai-models",
        data={
            "csrf_token": state.csrf_token,
            "label": "Production model",
            "provider": "openai",
            "model": "gpt-test",
            "api_key": "test-provider-secret",
        },
    )

    assert response.status_code == 400
    assert credentials == {}


@pytest.mark.asyncio
async def test_background_jobs_are_owned_and_cancelled_by_assessment(settings) -> None:
    state = WebState(settings)
    started = asyncio.Event()

    async def running_review() -> None:
        started.set()
        await asyncio.Event().wait()

    state.start_job("assessment-one", running_review())
    await started.wait()

    assert "assessment-one" in state.jobs
    await state.cancel_job("assessment-one")
    assert "assessment-one" not in state.jobs
