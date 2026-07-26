from aqa_ai_workflows_pe.domain.models import DraftRisk, RiskBand
from aqa_ai_workflows_pe.domain.risk import rank_risks, score_risk


def draft(**updates: object) -> DraftRisk:
    values = {
        "title": "Risk",
        "hypothesis": "If X, Y may happen.",
        "impact_reason": "Impact",
        "likelihood_reason": "Likelihood",
        "regression_reason": "Reach",
        "detectability_reason": "Detection",
        "evidence_strength_reason": "Evidence",
        "impact": 5,
        "likelihood": 5,
        "regression_reach": 5,
        "detectability": 5,
        "evidence_strength": 4,
        "evidence_ids": ["E0001"],
    }
    values.update(updates)
    return DraftRisk.model_validate(values)


def test_critical_score_matches_public_policy() -> None:
    result = score_risk(draft(), 1)
    assert result.score == 50
    assert result.band == RiskBand.CRITICAL


def test_evidence_strength_reduces_unsupported_risk() -> None:
    result = score_risk(draft(evidence_strength=0), 1)
    assert result.score == 30
    assert result.band == RiskBand.MEDIUM


def test_rank_is_deterministic() -> None:
    ordered = rank_risks([draft(title="Lower", impact=2), draft(title="Higher")])
    assert [item.title for item in ordered] == ["Higher", "Lower"]
    assert [item.id for item in ordered] == ["R01", "R02"]
