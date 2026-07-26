from __future__ import annotations

import argparse
import asyncio

from aqa_ai_workflows_pe.adapters.artifacts import ArtifactStore
from aqa_ai_workflows_pe.adapters.persistence import AssessmentStore
from aqa_ai_workflows_pe.config import Settings
from aqa_ai_workflows_pe.domain.models import ProviderConfig, ProviderName, ReviewRequest
from aqa_ai_workflows_pe.service import AnalysisSecrets, AnalysisService


async def run(pull_request_url: str) -> None:
    settings = Settings.load()
    settings.paths.ensure()
    artifacts = ArtifactStore(settings.paths.artifacts)
    store = AssessmentStore(settings.paths.database)
    service = AnalysisService(settings, store, artifacts)
    request = ReviewRequest.model_validate(
        {
            "pull_request_url": pull_request_url,
            "provider": ProviderConfig(
                provider=ProviderName.FAKE,
                model="deterministic-demo-v1",
                credential_source="none",
                destination_class="local",
            ),
        }
    )
    summary = service.create(request)
    pack = await service.prepare(summary.id, AnalysisSecrets())
    review = await service.review(summary.id, AnalysisSecrets())
    if review is None:
        raise RuntimeError("The smoke review requested unexpected additional context.")
    print(f"assessment={summary.id}")
    print(f"repositories={len(pack.repositories)} evidence={len(pack.evidence)}")
    print(f"risks={len(review.risks)} scenarios={len(review.scenarios)}")
    print(f"artifacts={artifacts.assessment_dir(summary.id)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pull_request_url")
    arguments = parser.parse_args()
    asyncio.run(run(arguments.pull_request_url))


if __name__ == "__main__":
    main()
