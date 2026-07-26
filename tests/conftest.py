from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from aqa_ai_workflows_pe.config import Settings
from aqa_ai_workflows_pe.domain.models import (
    ChangedFile,
    ContextPack,
    DraftRisk,
    EvidenceUnit,
    ExploratoryCharter,
    ProductImpact,
    ProviderConfig,
    ProviderName,
    ProviderReview,
    PullRequestMetadata,
    RepositoryManifest,
    RepositoryPin,
    ReviewRequest,
    ServiceImpact,
    SourceKind,
    TestScenario,
)
from aqa_ai_workflows_pe.paths import AppPaths


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    paths = AppPaths(
        data=data,
        cache=tmp_path / "cache",
        logs=tmp_path / "logs",
        database=data / "state.sqlite3",
        artifacts=data / "assessments",
        repositories=tmp_path / "cache" / "repositories",
    )
    paths.ensure()
    return Settings(paths=paths)


@pytest.fixture
def review_request() -> ReviewRequest:
    return ReviewRequest(
        pull_request_url="https://github.com/acme/shop/pull/42",
        provider=ProviderConfig(
            provider=ProviderName.FAKE,
            model="deterministic-demo-v1",
            credential_source="none",
            destination_class="local",
        ),
    )


@pytest.fixture
def context_pack() -> ContextPack:
    metadata = PullRequestMetadata(
        owner="acme",
        repository="shop",
        number=42,
        url="https://github.com/acme/shop/pull/42",
        title="Increase payment retry ceiling",
        body="Allow one additional retry for transient gateway failures.",
        author="developer",
        draft=False,
        state="open",
        base_sha="a" * 40,
        head_sha="b" * 40,
        base_ref="main",
        head_ref="retry",
        clone_url="https://github.com/acme/shop.git",
        changed_files=[
            ChangedFile(
                path="src/retry.py",
                status="modified",
                additions=1,
                deletions=1,
                patch="-attempts = 2\n+attempts = 3",
            )
        ],
    )
    pin = RepositoryPin(
        alias="primary",
        owner="acme",
        repository="shop",
        commit_sha="b" * 40,
        source_kind=SourceKind.PRIMARY_REPOSITORY,
        relationship="Primary pull-request repository",
        clone_url="https://github.com/acme/shop.git",
    )
    evidence = EvidenceUnit(
        id="E0001",
        source_kind=SourceKind.PULL_REQUEST,
        repository_alias="primary",
        repository_slug="acme/shop",
        commit_sha="b" * 40,
        path="src/retry.py",
        start_line=1,
        end_line=2,
        reason="Changed file",
        content="-attempts = 2\n+attempts = 3",
        sha256="c" * 64,
    )
    manifest = RepositoryManifest(
        repository_alias="primary",
        commit_sha="b" * 40,
        languages=["Python"],
        frameworks=["Python project"],
        manifests=["pyproject.toml"],
        test_paths=["tests/test_retry.py"],
        contract_paths=[],
        documentation_paths=["README.md"],
        entry_count=4,
        excluded_count=0,
        parser_coverage={"Python": "AST + lexical"},
        notes=[],
    )
    return ContextPack(
        schema_version="context-pack-v1",
        assessment_id="11111111-1111-1111-1111-111111111111",
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
        pull_request=metadata,
        repositories=[pin],
        manifests=[manifest],
        evidence=[evidence],
        exclusions=[],
        context_notes=[],
        estimated_tokens=8,
    )


@pytest.fixture
def provider_review() -> ProviderReview:
    return ProviderReview(
        change_summary="Retry attempts move from two to three.",
        intended_outcome="Recover from one more transient gateway failure.",
        product_impact=ProductImpact(
            outcome="More checkout recoveries may complete without user action.",
            affected_users=["Checkout customers"],
            affected_journeys=["Payment confirmation"],
            business_rules=["Retry only transient failures"],
            data_and_interfaces=["Payment attempt counter"],
            operations_and_rollout=["Monitor retry and duplicate-payment signals"],
            assumptions=["Payment writes are idempotent"],
            evidence_ids=["E0001"],
        ),
        gaps_and_questions=["Is the payment operation idempotent across three attempts?"],
        risks=[
            DraftRisk(
                title="A third retry may repeat a non-idempotent side effect",
                hypothesis="If attempt state is not idempotent, an extra retry could duplicate a charge.",
                impact_reason="Duplicate charges damage revenue trust.",
                likelihood_reason="The diff changes attempts but does not show idempotency.",
                regression_reason="Payment and confirmation consumers may both be affected.",
                detectability_reason="Requires controlled transient failure injection.",
                evidence_strength_reason="Direct diff supports the retry change; side effect is inferred.",
                impact=5,
                likelihood=3,
                regression_reach=4,
                detectability=4,
                evidence_strength=2,
                evidence_ids=["E0001"],
            )
        ],
        scenarios=[
            TestScenario(
                id="",
                title="Recover after two transient failures",
                priority="P0",
                objective="Validate one successful payment and one confirmation.",
                preconditions=["Gateway fails twice, then accepts"],
                steps=["Start checkout", "Observe three attempts", "Inspect final state"],
                expected_signals=["One charge", "One confirmation", "Retry metric is three"],
                risk_titles=["A third retry may repeat a non-idempotent side effect"],
                evidence_ids=["E0001"],
                test_layer="integration",
            )
        ],
        exploratory_charters=[
            ExploratoryCharter(
                title="Retry interruption",
                mission="Explore cancellation, timeout, and retry transitions.",
                focus_areas=["recovery"],
                stop_conditions=["All attempt transitions are observed"],
                evidence_ids=["E0001"],
            )
        ],
        service_impacts=[
            ServiceImpact(
                service="primary",
                relationship="Checkout API",
                possible_impact="Confirmation timing may change.",
                confidence="inferred",
                evidence_ids=["E0001"],
            )
        ],
        context_requests=[],
        limitations=["No product execution."],
    )
