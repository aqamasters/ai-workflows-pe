import os
import stat

import pytest

from aqa_ai_workflows_pe.adapters.artifacts import ArtifactStore
from aqa_ai_workflows_pe.adapters.reporting import ReportWriter
from aqa_ai_workflows_pe.domain.models import (
    CanonicalReview,
    ReviewMeta,
    ReviewRoundState,
    TransmissionManifest,
)
from aqa_ai_workflows_pe.domain.risk import rank_risks
from aqa_ai_workflows_pe.service import DISCLAIMER


def test_writes_all_public_report_formats(settings, context_pack, provider_review) -> None:
    artifacts = ArtifactStore(settings.paths.artifacts)
    review = CanonicalReview(
        meta=ReviewMeta(
            assessment_id=context_pack.assessment_id,
            generated_at=context_pack.created_at,
            provider="fake",
            model="demo",
            method_version="v1",
            context_schema_version="v1",
            report_schema_version="v1",
            risk_policy_version="v1",
            base_sha=context_pack.pull_request.base_sha,
            head_sha=context_pack.pull_request.head_sha,
            stale=False,
        ),
        change_summary=provider_review.change_summary,
        intended_outcome=provider_review.intended_outcome,
        product_impact=provider_review.product_impact,
        gaps_and_questions=provider_review.gaps_and_questions,
        risks=rank_risks(provider_review.risks),
        scenarios=provider_review.scenarios,
        exploratory_charters=provider_review.exploratory_charters,
        service_impacts=provider_review.service_impacts,
        limitations=provider_review.limitations,
        evidence=context_pack.evidence,
        transmission=[
            TransmissionManifest(
                provider="fake",
                model="demo",
                destination="local",
                repository_pins=["acme/shop@" + "b" * 40],
                evidence_ids=["E0001"],
                evidence_hashes=["c" * 64],
                content_bytes=32,
                estimated_tokens=8,
                prompt_version="v1",
                sent_at=context_pack.created_at,
            )
        ],
        disclaimer=DISCLAIMER,
    )
    paths = ReportWriter(artifacts).write_all(review)
    assert set(paths) == {"product.md", "qa.md", "report.html", "review.json", "transmission.json"}
    assert "Analysis only" in paths["product.md"].read_text()
    assert "Recover after two transient failures" in paths["qa.md"].read_text()
    assert '"provider": "fake"' in paths["review.json"].read_text()


def test_review_round_state_is_atomic_and_clearable(settings, context_pack) -> None:
    artifacts = ArtifactStore(settings.paths.artifacts)
    transmission = TransmissionManifest(
        provider="fake",
        model="demo",
        destination="local",
        repository_pins=["acme/shop@" + "b" * 40],
        evidence_ids=["E0001"],
        evidence_hashes=["c" * 64],
        content_bytes=32,
        estimated_tokens=8,
        prompt_version="v1",
        sent_at=context_pack.created_at,
    )
    state = ReviewRoundState(next_round=1, transmissions=[transmission])
    artifacts.write_review_state(context_pack.assessment_id, state)
    assert artifacts.read_review_state(context_pack.assessment_id) == state
    artifacts.clear_review_state(context_pack.assessment_id)
    assert artifacts.read_review_state(context_pack.assessment_id) is None


def test_invalid_assessment_id_never_creates_an_artifact_directory(settings) -> None:
    artifacts = ArtifactStore(settings.paths.artifacts)
    before = set(settings.paths.artifacts.iterdir())

    with pytest.raises(ValueError, match="Invalid assessment identifier"):
        artifacts.assessment_dir("../outside")

    assert set(settings.paths.artifacts.iterdir()) == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not available")
def test_artifact_directories_are_private(settings, context_pack) -> None:
    artifacts = ArtifactStore(settings.paths.artifacts)
    artifacts.write_context(context_pack)

    root_mode = stat.S_IMODE(settings.paths.artifacts.stat().st_mode)
    assessment_mode = stat.S_IMODE(
        artifacts.assessment_dir(context_pack.assessment_id).stat().st_mode
    )

    assert root_mode == 0o700
    assert assessment_mode == 0o700
