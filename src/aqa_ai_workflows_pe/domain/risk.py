from __future__ import annotations

from .models import DraftRisk, RiskBand, RiskHypothesis


def score_risk(draft: DraftRisk, sequence: int) -> RiskHypothesis:
    base = (
        4 * draft.impact + 3 * draft.likelihood + 2 * draft.regression_reach + draft.detectability
    )
    evidence_factor = 0.60 + 0.10 * draft.evidence_strength
    score = round(base * evidence_factor)
    if score >= 50 and draft.impact >= 4:
        band = RiskBand.CRITICAL
    elif score >= 38:
        band = RiskBand.HIGH
    elif score >= 25:
        band = RiskBand.MEDIUM
    else:
        band = RiskBand.LOW
    return RiskHypothesis(
        **draft.model_dump(),
        id=f"R{sequence:02d}",
        score=score,
        band=band,
    )


def rank_risks(risks: list[DraftRisk]) -> list[RiskHypothesis]:
    scored = [score_risk(risk, index + 1) for index, risk in enumerate(risks)]
    scored.sort(key=lambda item: (-item.score, item.title.casefold()))
    return [item.model_copy(update={"id": f"R{index:02d}"}) for index, item in enumerate(scored, 1)]
