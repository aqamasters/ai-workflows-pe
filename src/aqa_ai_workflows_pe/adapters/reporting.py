from __future__ import annotations

import html
import json
from pathlib import Path

from ..domain.models import CanonicalReview, EvidenceUnit, RiskHypothesis, TestScenario
from .artifacts import ArtifactStore


class ReportWriter:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def write_all(self, review: CanonicalReview) -> dict[str, Path]:
        directory = self.artifacts.assessment_dir(review.meta.assessment_id)
        paths = {
            "product.md": directory / "product-report.md",
            "qa.md": directory / "qa-report.md",
            "report.html": directory / "review.html",
            "review.json": directory / "canonical-review.json",
            "transmission.json": directory / "transmission-manifest.json",
        }
        self.artifacts.write_text(paths["product.md"], product_markdown(review))
        self.artifacts.write_text(paths["qa.md"], qa_markdown(review))
        self.artifacts.write_text(paths["report.html"], standalone_html(review))
        self.artifacts.write_text(
            paths["review.json"],
            json.dumps(review.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
        )
        self.artifacts.write_text(
            paths["transmission.json"],
            json.dumps(
                [item.model_dump(mode="json") for item in review.transmission],
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
        )
        return paths


def product_markdown(review: CanonicalReview) -> str:
    impact = review.product_impact
    lines = [
        "# Product change brief",
        "",
        review.disclaimer,
        "",
        "## What appears to be changing",
        "",
        review.change_summary,
        "",
        "## Intended outcome",
        "",
        review.intended_outcome,
        "",
        "## Likely product impact",
        "",
        f"**Outcome:** {impact.outcome}",
        "",
        _list("Affected users", impact.affected_users),
        _list("Affected journeys", impact.affected_journeys),
        _list("Business rules to confirm", impact.business_rules),
        _list("Data and interfaces", impact.data_and_interfaces),
        _list("Operations and rollout", impact.operations_and_rollout),
        _list("Assumptions", impact.assumptions),
        "## Decision questions",
        "",
        *[f"- {item}" for item in review.gaps_and_questions],
        "",
        "## Ranked risk hypotheses",
        "",
    ]
    for risk in review.risks:
        lines.extend(_risk_markdown(risk))
    lines.extend(
        [
            "## Repository and service impact",
            "",
            *[
                f"- **{item.service}** ({item.confidence}): {item.possible_impact} "
                f"{_citations(item.evidence_ids)}"
                for item in review.service_impacts
            ],
            "",
            "## Evidence and limits",
            "",
            *[f"- {item}" for item in review.limitations],
            "",
            _evidence_appendix(review.evidence),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def qa_markdown(review: CanonicalReview) -> str:
    lines = [
        "# QA testing brief",
        "",
        review.disclaimer,
        "",
        "## Recommended order",
        "",
        "Start with P0/P1 scenarios tied to the highest-ranked risks, then use the exploratory "
        "charters to challenge assumptions and recovery behavior.",
        "",
        "## Test scenarios",
        "",
    ]
    for scenario in review.scenarios:
        lines.extend(_scenario_markdown(scenario))
    lines.extend(["## Exploratory charters", ""])
    for charter in review.exploratory_charters:
        lines.extend(
            [
                f"### {charter.title}",
                "",
                charter.mission,
                "",
                f"**Focus:** {', '.join(charter.focus_areas)}",
                "",
                f"**Stop when:** {', '.join(charter.stop_conditions)}",
                "",
                f"**Evidence:** {_citations(charter.evidence_ids)}",
                "",
            ]
        )
    lines.extend(["## Limitations", "", *[f"- {item}" for item in review.limitations], ""])
    return "\n".join(lines).rstrip() + "\n"


def standalone_html(review: CanonicalReview) -> str:
    risks = "".join(
        f"<article><span class='badge {html.escape(risk.band.value)}'>{html.escape(risk.band.value)} "
        f"· {risk.score}</span><h3>{html.escape(risk.title)}</h3>"
        f"<p>{html.escape(risk.hypothesis)}</p><small>{html.escape(_citations(risk.evidence_ids))}</small></article>"
        for risk in review.risks
    )
    scenarios = "".join(
        f"<article><span class='badge'>{html.escape(item.priority)} · {html.escape(item.test_layer)}</span>"
        f"<h3>{html.escape(item.id)} — {html.escape(item.title)}</h3>"
        f"<p>{html.escape(item.objective)}</p><ol>{''.join(f'<li>{html.escape(step)}</li>' for step in item.steps)}</ol>"
        f"<small>{html.escape(_citations(item.evidence_ids))}</small></article>"
        for item in review.scenarios
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AQA AI Workflows Public Edition</title><style>
body{{font:16px/1.55 system-ui,sans-serif;margin:0;background:#f4f5f7;color:#172034}}
main{{max-width:980px;margin:auto;padding:48px 24px}}article{{background:white;padding:22px;border-radius:14px;margin:16px 0;border:1px solid #dde2eb}}
.notice{{background:#fff8db;border:1px solid #ead98f;padding:16px;border-radius:10px}}.badge{{font-size:12px;text-transform:uppercase;font-weight:700;background:#e8edf7;padding:5px 8px;border-radius:999px}}
.critical{{background:#ffd9dc}}.high{{background:#ffe4c2}}.medium{{background:#fff1bd}}small{{color:#596579}}
</style></head><body><main><p class="badge">AQA AI Workflows Public Edition</p>
<h1>{html.escape(review.intended_outcome)}</h1><p class="notice">{html.escape(review.disclaimer)}</p>
<h2>What appears to be changing</h2><p>{html.escape(review.change_summary)}</p>
<h2>Ranked risk hypotheses</h2>{risks}<h2>Prioritized testing</h2>{scenarios}
<h2>Questions to resolve</h2><ul>{"".join(f"<li>{html.escape(item)}</li>" for item in review.gaps_and_questions)}</ul>
<p><small>Generated at {html.escape(review.meta.generated_at.isoformat())} from commits {html.escape(review.meta.base_sha[:12])} → {html.escape(review.meta.head_sha[:12])}. Model: {html.escape(review.meta.provider.value)} / {html.escape(review.meta.model)}.</small></p>
</main></body></html>"""


def _list(title: str, values: list[str]) -> str:
    return (
        f"### {title}\n\n"
        + ("\n".join(f"- {value}" for value in values) or "- None identified")
        + "\n"
    )


def _risk_markdown(risk: RiskHypothesis) -> list[str]:
    return [
        f"### {risk.id} — {risk.title}",
        "",
        f"**{risk.band.value.upper()} · {risk.score}**",
        "",
        risk.hypothesis,
        "",
        f"- Impact: {risk.impact_reason}",
        f"- Likelihood: {risk.likelihood_reason}",
        f"- Regression reach: {risk.regression_reason}",
        f"- Detectability: {risk.detectability_reason}",
        f"- Evidence: {_citations(risk.evidence_ids)}",
        "",
    ]


def _scenario_markdown(item: TestScenario) -> list[str]:
    return [
        f"### {item.id} — {item.title}",
        "",
        f"**{item.priority} · {item.test_layer}**",
        "",
        item.objective,
        "",
        "**Preconditions**",
        "",
        *[f"- {value}" for value in item.preconditions],
        "",
        "**Steps**",
        "",
        *[f"{index}. {value}" for index, value in enumerate(item.steps, 1)],
        "",
        "**Expected signals**",
        "",
        *[f"- {value}" for value in item.expected_signals],
        "",
        f"**Evidence:** {_citations(item.evidence_ids)}",
        "",
    ]


def _citations(values: list[str]) -> str:
    return " ".join(f"[{value}]" for value in values) or "[No direct citation]"


def _evidence_appendix(evidence: list[EvidenceUnit]) -> str:
    lines = ["## Evidence appendix", ""]
    for item in evidence:
        lines.append(
            f"- **{item.id}** · `{item.repository_slug}@{item.commit_sha[:12]}` · "
            f"`{item.path}` lines {item.start_line}–{item.end_line} · {item.reason}"
        )
    return "\n".join(lines)
