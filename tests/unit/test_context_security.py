from aqa_ai_workflows_pe.adapters.context import _denied, _redact


def test_denies_secret_like_paths() -> None:
    assert _denied("config/.private/settings")
    assert _denied("config/credentials.json")
    assert _denied("certs/server.pem")
    assert not _denied("src/environment.py")


def test_redacts_high_confidence_tokens() -> None:
    source = "api_key = synthetic-secret-value-123456\nname = safe"
    redacted, count = _redact(source)
    assert "synthetic-secret-value" not in redacted
    assert "[REDACTED]" in redacted
    assert count >= 1
