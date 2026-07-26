from aqa_ai_workflows_pe.adapters.credentials import GitHubCredentialCache
from aqa_ai_workflows_pe.service import AnalysisSecrets


def test_secret_containers_do_not_expose_values_in_repr() -> None:
    github = GitHubCredentialCache()
    github.set("github", "github-test-secret")
    analysis = AnalysisSecrets(
        github_token="github-test-secret",
        provider_key="provider-test-secret",
    )

    assert "github-test-secret" not in repr(github)
    assert "github-test-secret" not in repr(analysis)
    assert "provider-test-secret" not in repr(analysis)
