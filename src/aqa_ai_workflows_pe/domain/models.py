from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    COMPATIBLE = "compatible"
    FAKE = "fake"


class SourceKind(StrEnum):
    PULL_REQUEST = "pull_request"
    PRIMARY_REPOSITORY = "primary_repository"
    RELATED_REPOSITORY = "related_repository"


class AssessmentStatus(StrEnum):
    QUEUED = "queued"
    ACQUIRING = "acquiring"
    CONTEXT = "context"
    READY = "ready"
    REVIEWING = "reviewing"
    REPORTING = "reporting"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskBand(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RelatedSourceInput(StrictModel):
    url: HttpUrl
    label: Annotated[str, Field(min_length=1, max_length=80)]
    relationship: Annotated[str, Field(max_length=240)] = "Related service"
    ref: Annotated[str, Field(max_length=160)] = ""


class ProviderConfig(StrictModel):
    provider: ProviderName
    model: Annotated[str, Field(min_length=1, max_length=200)]
    base_url: Annotated[str, Field(max_length=500)] = ""
    credential_source: Literal["keyring", "none"] = "none"
    destination_class: Literal["cloud", "local", "custom"] = "cloud"
    profile_id: Annotated[str, Field(max_length=64)] = ""


class AIModelProfile(StrictModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    provider: ProviderName
    model: Annotated[str, Field(min_length=1, max_length=200)]
    base_url: Annotated[str, Field(default="", max_length=500)]
    credential_source: Literal["keyring", "none"]
    destination_class: Literal["cloud", "local", "custom"]
    is_default: bool = False
    created_at: datetime
    updated_at: datetime

    def provider_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            credential_source=self.credential_source,
            destination_class=self.destination_class,
            profile_id=self.id,
        )


class ReviewRequest(StrictModel):
    pull_request_url: HttpUrl
    related_sources: list[RelatedSourceInput] = Field(default_factory=list, max_length=3)
    provider: ProviderConfig
    product_notes: Annotated[str, Field(max_length=4_000)] = ""


class ChangedFile(StrictModel):
    path: str
    previous_path: str = ""
    status: str
    additions: int = 0
    deletions: int = 0
    patch: str = ""


class PullRequestMetadata(StrictModel):
    owner: str
    repository: str
    number: int
    url: str
    title: str
    body: str
    author: str
    draft: bool
    state: str
    base_sha: str
    head_sha: str
    base_ref: str
    head_ref: str
    clone_url: str
    changed_files: list[ChangedFile]


class RepositoryPin(StrictModel):
    alias: str
    owner: str
    repository: str
    commit_sha: str
    source_kind: SourceKind
    relationship: str
    clone_url: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repository}"


class RepositoryManifest(StrictModel):
    repository_alias: str
    commit_sha: str
    languages: list[str]
    frameworks: list[str]
    manifests: list[str]
    test_paths: list[str]
    contract_paths: list[str]
    documentation_paths: list[str]
    entry_count: int
    excluded_count: int
    parser_coverage: dict[str, str]
    notes: list[str]


class EvidenceUnit(StrictModel):
    id: str
    source_kind: SourceKind
    repository_alias: str
    repository_slug: str
    commit_sha: str
    path: str
    start_line: int
    end_line: int
    reason: str
    content: str
    sha256: str
    redactions: int = 0


class ContextRequest(StrictModel):
    repository_alias: str
    kind: Literal["file", "symbol", "contract", "test", "documentation", "reference"]
    query: Annotated[str, Field(min_length=1, max_length=240)]
    reason: Annotated[str, Field(min_length=1, max_length=360)]
    max_results: Annotated[int, Field(ge=1, le=12)] = 5


class ContextPack(StrictModel):
    schema_version: str
    assessment_id: str
    created_at: datetime
    pull_request: PullRequestMetadata
    repositories: list[RepositoryPin]
    manifests: list[RepositoryManifest]
    evidence: list[EvidenceUnit]
    exclusions: list[str]
    context_notes: list[str]
    estimated_tokens: int


class TransmissionManifest(StrictModel):
    provider: ProviderName
    model: str
    destination: str
    repository_pins: list[str]
    evidence_ids: list[str]
    evidence_hashes: list[str]
    content_bytes: int
    estimated_tokens: int
    prompt_version: str
    sent_at: datetime


class ReviewRoundState(StrictModel):
    next_round: Annotated[int, Field(ge=1, le=2)]
    transmissions: list[TransmissionManifest]


class ProductImpact(StrictModel):
    outcome: str
    affected_users: list[str]
    affected_journeys: list[str]
    business_rules: list[str]
    data_and_interfaces: list[str]
    operations_and_rollout: list[str]
    assumptions: list[str]
    evidence_ids: list[str]


class DraftRisk(StrictModel):
    title: str
    hypothesis: str
    impact_reason: str
    likelihood_reason: str
    regression_reason: str
    detectability_reason: str
    evidence_strength_reason: str
    impact: Annotated[int, Field(ge=1, le=5)]
    likelihood: Annotated[int, Field(ge=1, le=5)]
    regression_reach: Annotated[int, Field(ge=1, le=5)]
    detectability: Annotated[int, Field(ge=1, le=5)]
    evidence_strength: Annotated[int, Field(ge=0, le=4)]
    evidence_ids: list[str]


class RiskHypothesis(DraftRisk):
    id: str
    score: int
    band: RiskBand


class TestScenario(StrictModel):
    id: str = ""
    title: str
    priority: Literal["P0", "P1", "P2", "P3"]
    objective: str
    preconditions: list[str]
    steps: list[str]
    expected_signals: list[str]
    risk_titles: list[str]
    evidence_ids: list[str]
    test_layer: Literal[
        "manual",
        "exploratory",
        "api",
        "integration",
        "ui",
        "accessibility",
        "performance",
        "security",
        "data",
    ]


class ExploratoryCharter(StrictModel):
    title: str
    mission: str
    focus_areas: list[str]
    stop_conditions: list[str]
    evidence_ids: list[str]


class ServiceImpact(StrictModel):
    service: str
    relationship: str
    possible_impact: str
    confidence: Literal["explicit", "structural", "inferred"]
    evidence_ids: list[str]


class ProviderReview(StrictModel):
    change_summary: str
    intended_outcome: str
    product_impact: ProductImpact
    gaps_and_questions: list[str]
    risks: list[DraftRisk]
    scenarios: list[TestScenario]
    exploratory_charters: list[ExploratoryCharter]
    service_impacts: list[ServiceImpact]
    context_requests: list[ContextRequest]
    limitations: list[str]


class ReviewMeta(StrictModel):
    assessment_id: str
    generated_at: datetime
    provider: ProviderName
    model: str
    method_version: str
    context_schema_version: str
    report_schema_version: str
    risk_policy_version: str
    base_sha: str
    head_sha: str
    stale: bool
    analysis_only: bool = True


class CanonicalReview(StrictModel):
    meta: ReviewMeta
    change_summary: str
    intended_outcome: str
    product_impact: ProductImpact
    gaps_and_questions: list[str]
    risks: list[RiskHypothesis]
    scenarios: list[TestScenario]
    exploratory_charters: list[ExploratoryCharter]
    service_impacts: list[ServiceImpact]
    limitations: list[str]
    evidence: list[EvidenceUnit]
    transmission: list[TransmissionManifest]
    disclaimer: str


class AssessmentSummary(StrictModel):
    id: str
    status: AssessmentStatus
    progress: int
    message: str
    created_at: datetime
    updated_at: datetime
    request: ReviewRequest
    result: CanonicalReview | None = None
    error: str = ""

    @field_validator("progress")
    @classmethod
    def validate_progress(cls, value: int) -> int:
        if not 0 <= value <= 100:
            raise ValueError("progress must be between 0 and 100")
        return value
