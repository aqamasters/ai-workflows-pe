from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field

from .adapters.ai import create_provider
from .adapters.artifacts import ArtifactStore
from .adapters.context import ContextEngine
from .adapters.git import GitCache
from .adapters.github import GitHubClient
from .adapters.persistence import AssessmentStore
from .adapters.reporting import ReportWriter
from .config import Settings
from .domain.errors import AQAReviewError, ProviderError
from .domain.models import (
    AssessmentStatus,
    AssessmentSummary,
    CanonicalReview,
    ContextPack,
    ProviderReview,
    RepositoryPin,
    ReviewMeta,
    ReviewRequest,
    ReviewRoundState,
    SourceKind,
    TransmissionManifest,
    utc_now,
)
from .domain.risk import rank_risks
from .version import (
    CONTEXT_SCHEMA_VERSION,
    METHOD_VERSION,
    REPORT_SCHEMA_VERSION,
    RISK_POLICY_VERSION,
)

DISCLAIMER = (
    "Analysis only. AQA AI Workflows Public Edition inspected source and repository context "
    "at the commits "
    "shown. It did not run the product or tests. Risks are hypotheses for human review, not "
    "verified defects or a release decision."
)


@dataclass(frozen=True, slots=True)
class AnalysisSecrets:
    github_token: str = field(default="", repr=False)
    provider_key: str = field(default="", repr=False)


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        store: AssessmentStore,
        artifacts: ArtifactStore,
    ) -> None:
        self.settings = settings
        self.store = store
        self.artifacts = artifacts
        self.reports = ReportWriter(artifacts)

    def create(self, request: ReviewRequest) -> AssessmentSummary:
        if len(request.related_sources) > self.settings.limits.related_repositories:
            raise ValueError("At most three related repositories are supported.")
        return self.store.create(str(uuid.uuid4()), request)

    async def prepare(self, assessment_id: str, secrets: AnalysisSecrets) -> ContextPack:
        summary = self._require(assessment_id)
        try:
            self._progress(assessment_id, AssessmentStatus.ACQUIRING, 8, "Reading the pull request")
            async with GitHubClient(self.settings, secrets.github_token) as github:
                pull_request = await github.pull_request(str(summary.request.pull_request_url))
                primary_pin = RepositoryPin(
                    alias="primary",
                    owner=pull_request.owner,
                    repository=pull_request.repository,
                    commit_sha=pull_request.head_sha,
                    source_kind=SourceKind.PRIMARY_REPOSITORY,
                    relationship="Primary pull-request repository",
                    clone_url=pull_request.clone_url,
                )
                related: list[tuple[RepositoryPin, int | None]] = []
                for index, source in enumerate(summary.request.related_sources, 1):
                    parsed, commit_sha, clone_url = await github.related_pin(source)
                    related.append(
                        (
                            RepositoryPin(
                                alias=f"related-{index}",
                                owner=parsed.owner,
                                repository=parsed.repository,
                                commit_sha=commit_sha,
                                source_kind=SourceKind.RELATED_REPOSITORY,
                                relationship=f"{source.label}: {source.relationship}",
                                clone_url=clone_url,
                            ),
                            parsed.pull_number,
                        )
                    )

            self._progress(
                assessment_id,
                AssessmentStatus.ACQUIRING,
                20,
                "Building safe local Git object caches",
            )
            cache = GitCache(self.settings, secrets.github_token)
            primary_repo = await asyncio.to_thread(
                cache.prepare, primary_pin, pull_number=pull_request.number
            )
            await asyncio.to_thread(primary_repo.fetch_commit, pull_request.base_sha)
            engine = ContextEngine(self.settings)
            await asyncio.to_thread(engine.register, primary_pin, primary_repo)
            for pin, pull_number in related:
                repository = await asyncio.to_thread(cache.prepare, pin, pull_number=pull_number)
                await asyncio.to_thread(engine.register, pin, repository)

            self._progress(
                assessment_id,
                AssessmentStatus.CONTEXT,
                35,
                "Selecting bounded, evidence-addressed repository context",
            )
            pack = await asyncio.to_thread(
                engine.build,
                assessment_id,
                pull_request,
                summary.request.product_notes,
            )
            await asyncio.to_thread(self.artifacts.write_context, pack)
            self._progress(
                assessment_id,
                AssessmentStatus.READY,
                45,
                "Context is ready for your transmission review",
            )
            return pack
        except Exception as exc:
            self._fail(assessment_id, exc)
            raise

    async def review(self, assessment_id: str, secrets: AnalysisSecrets) -> CanonicalReview | None:
        summary = self._require(assessment_id)
        if summary.status not in {AssessmentStatus.READY, AssessmentStatus.FAILED}:
            raise AQAReviewError("This assessment is not ready for AI review.")
        try:
            pack = self.artifacts.read_context(assessment_id)
            self._progress(
                assessment_id,
                AssessmentStatus.REVIEWING,
                52,
                f"Reviewing with {summary.request.provider.provider.value} / "
                f"{summary.request.provider.model}",
            )
            cache = GitCache(self.settings, secrets.github_token)
            engine = ContextEngine(self.settings)
            for pin in pack.repositories:
                repository = await asyncio.to_thread(cache.prepare, pin)
                await asyncio.to_thread(engine.register, pin, repository)

            provider = create_provider(
                self.settings,
                summary.request.provider,
                secrets.provider_key,
            )
            prior_state = self.artifacts.read_review_state(assessment_id)
            round_number = prior_state.next_round if prior_state else 0
            transmissions = list(prior_state.transmissions) if prior_state else []
            transmissions.append(_transmission(pack, summary.request, provider.destination))
            draft = await provider.review(pack, round_number)
            if draft.context_requests and round_number < self.settings.limits.extra_context_rounds:
                self._progress(
                    assessment_id,
                    AssessmentStatus.REVIEWING,
                    66,
                    "Resolving a bounded model context request locally",
                )
                expanded = await asyncio.to_thread(
                    engine.resolve_requests,
                    pack,
                    draft.context_requests,
                )
                if _has_new_evidence(pack, expanded):
                    await asyncio.to_thread(self.artifacts.write_context, expanded)
                    await asyncio.to_thread(
                        self.artifacts.write_review_state,
                        assessment_id,
                        ReviewRoundState(
                            next_round=round_number + 1,
                            transmissions=transmissions,
                        ),
                    )
                    self._progress(
                        assessment_id,
                        AssessmentStatus.READY,
                        72,
                        "Additional context is ready for your approval",
                    )
                    return None

            self._progress(
                assessment_id,
                AssessmentStatus.REPORTING,
                88,
                "Validating citations and applying the deterministic risk policy",
            )
            draft = _challenge(draft, pack)
            async with GitHubClient(self.settings, secrets.github_token) as github:
                current_head = await github.current_head(pack.pull_request)
            review = _canonical_review(
                assessment_id,
                summary.request,
                pack,
                draft,
                transmissions,
                stale=current_head != pack.pull_request.head_sha,
            )
            await asyncio.to_thread(self.reports.write_all, review)
            await asyncio.to_thread(self.artifacts.clear_review_state, assessment_id)
            self.store.update(
                assessment_id,
                AssessmentStatus.COMPLETE,
                100,
                "Review complete",
                result=review,
            )
            return review
        except Exception as exc:
            self._fail(assessment_id, exc)
            raise

    def delete(self, assessment_id: str) -> bool:
        deleted = self.store.delete(assessment_id)
        self.artifacts.delete(assessment_id)
        return deleted

    def _require(self, assessment_id: str) -> AssessmentSummary:
        summary = self.store.get(assessment_id)
        if summary is None:
            raise AQAReviewError("Assessment not found in local storage.")
        return summary

    def _progress(
        self,
        assessment_id: str,
        status: AssessmentStatus,
        progress: int,
        message: str,
    ) -> None:
        self.store.update(assessment_id, status, progress, message)

    def _fail(self, assessment_id: str, exc: Exception) -> None:
        message = (
            str(exc)
            if isinstance(exc, AQAReviewError)
            else "The local review stopped unexpectedly."
        )
        self.store.update(
            assessment_id,
            AssessmentStatus.FAILED,
            100,
            "Review stopped",
            error=message[:2_000],
        )


def _transmission(
    pack: ContextPack,
    request: ReviewRequest,
    destination: str,
) -> TransmissionManifest:
    return TransmissionManifest(
        provider=request.provider.provider,
        model=request.provider.model,
        destination=destination,
        repository_pins=[f"{pin.slug}@{pin.commit_sha}" for pin in pack.repositories],
        evidence_ids=[item.id for item in pack.evidence],
        evidence_hashes=[item.sha256 for item in pack.evidence],
        content_bytes=sum(len(item.content.encode()) for item in pack.evidence),
        estimated_tokens=pack.estimated_tokens,
        prompt_version=METHOD_VERSION,
        sent_at=utc_now(),
    )


def _has_new_evidence(before: ContextPack, after: ContextPack) -> bool:
    approved = {
        (item.repository_alias, item.path, item.start_line, item.end_line, item.sha256)
        for item in before.evidence
    }
    return any(
        (item.repository_alias, item.path, item.start_line, item.end_line, item.sha256)
        not in approved
        for item in after.evidence
    )


def _challenge(draft: ProviderReview, pack: ContextPack) -> ProviderReview:
    valid_ids = {item.id for item in pack.evidence}
    seen_risks: set[str] = set()
    risks = []
    for risk in draft.risks:
        key = re.sub(r"\W+", " ", risk.title.casefold()).strip()
        evidence_ids = [item for item in risk.evidence_ids if item in valid_ids]
        if not evidence_ids or key in seen_risks:
            continue
        seen_risks.add(key)
        risks.append(
            risk.model_copy(
                update={
                    "title": _safe_claim(risk.title),
                    "hypothesis": _safe_claim(risk.hypothesis),
                    "evidence_ids": evidence_ids,
                }
            )
        )
    if not risks:
        raise ProviderError(
            "The model did not produce any unique risk hypothesis with a valid evidence citation."
        )

    scenarios = []
    for item in draft.scenarios[:50]:
        evidence_ids = [value for value in item.evidence_ids if value in valid_ids]
        if not evidence_ids:
            continue
        scenarios.append(
            item.model_copy(
                update={
                    "id": f"T{len(scenarios) + 1:02d}",
                    "title": _safe_claim(item.title),
                    "objective": _safe_claim(item.objective),
                    "evidence_ids": evidence_ids,
                }
            )
        )
    product = draft.product_impact.model_copy(
        update={
            "evidence_ids": [
                value for value in draft.product_impact.evidence_ids if value in valid_ids
            ]
        }
    )
    charters = [
        item.model_copy(
            update={"evidence_ids": [value for value in item.evidence_ids if value in valid_ids]}
        )
        for item in draft.exploratory_charters
        if any(value in valid_ids for value in item.evidence_ids)
    ]
    impacts = [
        item.model_copy(
            update={"evidence_ids": [value for value in item.evidence_ids if value in valid_ids]}
        )
        for item in draft.service_impacts
        if any(value in valid_ids for value in item.evidence_ids)
    ]
    unresolved_context = [
        (
            f"Confirm missing context in {item.repository_alias}: {item.reason} "
            f"(requested {item.kind}: {item.query})."
        )
        for item in draft.context_requests
    ]
    context_limitations = (
        ["The model requested context that was not added or exceeded the approved round limit."]
        if unresolved_context
        else []
    )
    limitations = list(
        dict.fromkeys(
            [
                *draft.limitations,
                *context_limitations,
                "Repository context is bounded and may not capture runtime, deployment, or stakeholder knowledge.",
                "The application did not execute source code, builds, tests, services, or product flows.",
            ]
        )
    )
    return draft.model_copy(
        update={
            "change_summary": _safe_claim(draft.change_summary),
            "intended_outcome": _safe_claim(draft.intended_outcome),
            "product_impact": product,
            "gaps_and_questions": list(
                dict.fromkeys([*draft.gaps_and_questions, *unresolved_context])
            ),
            "risks": risks[:20],
            "scenarios": scenarios,
            "exploratory_charters": charters,
            "service_impacts": impacts,
            "limitations": limitations,
            "context_requests": [],
        }
    )


def _safe_claim(value: str) -> str:
    replacements = (
        (r"(?i)\b(?:all )?tests? (?:have )?passed\b", "test execution would need to confirm this"),
        (r"(?i)\b(?:a )?defect (?:was |has been )?found\b", "a potential defect hypothesis exists"),
        (r"(?i)\bsafe to ship\b", "ready for a human release decision"),
        (r"(?i)\brelease is safe\b", "release still requires human judgment"),
    )
    result = value
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result)
    return result


def _canonical_review(
    assessment_id: str,
    request: ReviewRequest,
    pack: ContextPack,
    draft: ProviderReview,
    transmissions: list[TransmissionManifest],
    *,
    stale: bool,
) -> CanonicalReview:
    return CanonicalReview(
        meta=ReviewMeta(
            assessment_id=assessment_id,
            generated_at=utc_now(),
            provider=request.provider.provider,
            model=request.provider.model,
            method_version=METHOD_VERSION,
            context_schema_version=CONTEXT_SCHEMA_VERSION,
            report_schema_version=REPORT_SCHEMA_VERSION,
            risk_policy_version=RISK_POLICY_VERSION,
            base_sha=pack.pull_request.base_sha,
            head_sha=pack.pull_request.head_sha,
            stale=stale,
        ),
        change_summary=draft.change_summary,
        intended_outcome=draft.intended_outcome,
        product_impact=draft.product_impact,
        gaps_and_questions=draft.gaps_and_questions,
        risks=rank_risks(draft.risks),
        scenarios=draft.scenarios,
        exploratory_charters=draft.exploratory_charters,
        service_impacts=draft.service_impacts,
        limitations=draft.limitations,
        evidence=pack.evidence,
        transmission=transmissions,
        disclaimer=DISCLAIMER,
    )
