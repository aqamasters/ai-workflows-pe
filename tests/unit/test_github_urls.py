import pytest

from aqa_ai_workflows_pe.adapters.github import parse_github_url
from aqa_ai_workflows_pe.domain.errors import InputError


def test_parses_strict_pull_request() -> None:
    parsed = parse_github_url("https://github.com/acme/shop/pull/42", require_pull_request=True)
    assert parsed.slug == "acme/shop"
    assert parsed.pull_number == 42


@pytest.mark.parametrize(
    "value",
    [
        "http://github.com/acme/shop/pull/42",
        "https://evil.example/acme/shop/pull/42",
        "https://token@github.com/acme/shop/pull/42",
        "https://github.com:8443/acme/shop/pull/42",
        "https://github.com/acme/shop/pull/42?diff=1",
        "https://github.com/acme/shop/pull/0",
        "https://github.com/acme/shop/issues/42",
    ],
)
def test_rejects_unsafe_primary_urls(value: str) -> None:
    with pytest.raises(InputError):
        parse_github_url(value, require_pull_request=True)


def test_related_repository_url_is_allowed() -> None:
    parsed = parse_github_url("https://github.com/acme/payments.git")
    assert parsed.repository == "payments"
    assert parsed.pull_number is None
