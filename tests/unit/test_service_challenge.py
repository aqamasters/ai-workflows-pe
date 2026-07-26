from aqa_ai_workflows_pe.domain.models import ContextRequest
from aqa_ai_workflows_pe.service import _challenge, _has_new_evidence, _safe_claim


def test_challenge_filters_unknown_evidence(provider_review, context_pack) -> None:
    bad = provider_review.model_copy(deep=True)
    bad.risks[0].evidence_ids = ["E9999"]
    try:
        _challenge(bad, context_pack)
    except Exception as exc:
        assert "valid evidence citation" in str(exc)
    else:
        raise AssertionError("Unsupported risk should fail validation")


def test_challenge_assigns_scenario_ids(provider_review, context_pack) -> None:
    challenged = _challenge(provider_review, context_pack)
    assert challenged.scenarios[0].id == "T01"
    assert challenged.context_requests == []


def test_prohibited_execution_claims_are_rewritten() -> None:
    value = _safe_claim("All tests passed, a defect was found, and it is safe to ship.")
    assert "tests passed" not in value.casefold()
    assert "defect was found" not in value.casefold()
    assert "safe to ship" not in value.casefold()


def test_unresolved_context_becomes_an_explicit_question(provider_review, context_pack) -> None:
    provider_review.context_requests = [
        ContextRequest(
            repository_alias="primary",
            kind="test",
            query="idempotency",
            reason="The retry contract is not explicit.",
        )
    ]
    challenged = _challenge(provider_review, context_pack)
    assert challenged.context_requests == []
    assert any("idempotency" in item for item in challenged.gaps_and_questions)
    assert any("approved round limit" in item for item in challenged.limitations)


def test_context_expansion_detects_only_new_evidence(context_pack) -> None:
    unchanged = context_pack.model_copy(deep=True)
    assert not _has_new_evidence(context_pack, unchanged)
    expanded = context_pack.model_copy(deep=True)
    expanded.evidence.append(
        context_pack.evidence[0].model_copy(
            update={"id": "E0002", "path": "tests/test_retry.py", "sha256": "d" * 64}
        )
    )
    assert _has_new_evidence(context_pack, expanded)
