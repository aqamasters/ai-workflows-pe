from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from ..config import Settings
from ..domain.errors import AuthenticationError, ExternalServiceError, InputError
from ..domain.models import ChangedFile, PullRequestMetadata, RelatedSourceInput
from ..version import __version__

OWNER_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
GIT_REF = re.compile(r"^[A-Za-z0-9._/-]{1,160}$")
PR_PATH = re.compile(r"^/([^/]+)/([^/]+)/pull/(\d+)/?$")
REPO_PATH = re.compile(r"^/([^/]+)/([^/]+)/?$")


@dataclass(frozen=True, slots=True)
class ParsedGitHubUrl:
    owner: str
    repository: str
    pull_number: int | None = None

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repository}"


def parse_github_url(value: str, *, require_pull_request: bool = False) -> ParsedGitHubUrl:
    try:
        parsed = urlsplit(value.strip())
    except ValueError as exc:
        raise InputError("Enter a valid GitHub HTTPS URL.") from exc
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise InputError("Only HTTPS github.com repository and pull-request links are supported.")
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise InputError(
            "GitHub links cannot include credentials, ports, query strings, or fragments."
        )
    match = PR_PATH.fullmatch(parsed.path)
    if match:
        owner, repository, number = match.groups()
        _validate_owner_repo(owner, repository)
        pull_number = int(number)
        if pull_number <= 0:
            raise InputError("Pull-request number must be a positive integer.")
        return ParsedGitHubUrl(owner, repository.removesuffix(".git"), pull_number)
    if not require_pull_request:
        match = REPO_PATH.fullmatch(parsed.path)
        if match:
            owner, repository = match.groups()
            _validate_owner_repo(owner, repository)
            return ParsedGitHubUrl(owner, repository.removesuffix(".git"), None)
    expected = "an open pull-request" if require_pull_request else "a repository or pull-request"
    raise InputError(f"Enter {expected} URL from github.com.")


def _validate_owner_repo(owner: str, repository: str) -> None:
    repository = repository.removesuffix(".git")
    if not OWNER_REPO.fullmatch(owner) or not OWNER_REPO.fullmatch(repository):
        raise InputError("The GitHub owner or repository name contains unsupported characters.")


class GitHubClient:
    def __init__(self, settings: Settings, token: str = "") -> None:
        self.settings = settings
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": settings.github_api_version,
            "User-Agent": f"aqa-ai-workflows-pe/{__version__}",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.AsyncClient(
            base_url=settings.github_api_base,
            headers=headers,
            timeout=settings.network_timeout_seconds,
            follow_redirects=False,
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.client.aclose()

    async def pull_request(self, value: str) -> PullRequestMetadata:
        parsed = parse_github_url(value, require_pull_request=True)
        assert parsed.pull_number is not None
        payload = await self._get(
            f"/repos/{parsed.owner}/{parsed.repository}/pulls/{parsed.pull_number}"
        )
        if payload.get("state") != "open" or payload.get("merged_at"):
            raise InputError("This pull request is closed or merged. Use an open pull request.")
        files = await self._pull_files(parsed)
        return PullRequestMetadata(
            owner=parsed.owner,
            repository=parsed.repository,
            number=parsed.pull_number,
            url=str(payload["html_url"]),
            title=str(payload.get("title") or "Untitled pull request"),
            body=str(payload.get("body") or ""),
            author=str((payload.get("user") or {}).get("login") or "unknown"),
            draft=bool(payload.get("draft")),
            state=str(payload.get("state")),
            base_sha=str(payload["base"]["sha"]),
            head_sha=str(payload["head"]["sha"]),
            base_ref=str(payload["base"]["ref"]),
            head_ref=str(payload["head"]["ref"]),
            clone_url=str(payload["base"]["repo"]["clone_url"]),
            changed_files=files,
        )

    async def related_pin(self, source: RelatedSourceInput) -> tuple[ParsedGitHubUrl, str, str]:
        parsed = parse_github_url(str(source.url))
        if parsed.pull_number is not None:
            payload = await self._get(
                f"/repos/{parsed.owner}/{parsed.repository}/pulls/{parsed.pull_number}"
            )
            if payload.get("state") != "open" or payload.get("merged_at"):
                raise InputError(f"Related PR {parsed.slug}#{parsed.pull_number} is not open.")
            return parsed, str(payload["head"]["sha"]), str(payload["base"]["repo"]["clone_url"])
        repository = await self._get(f"/repos/{parsed.owner}/{parsed.repository}")
        ref = source.ref or str(repository["default_branch"])
        if not GIT_REF.fullmatch(ref) or ref.startswith("/") or ".." in ref.split("/"):
            raise InputError("Related repository ref contains unsupported characters.")
        commit = await self._get(
            f"/repos/{parsed.owner}/{parsed.repository}/commits/{quote(ref, safe='')}"
        )
        return parsed, str(commit["sha"]), str(repository["clone_url"])

    async def current_head(self, metadata: PullRequestMetadata) -> str:
        payload = await self._get(
            f"/repos/{metadata.owner}/{metadata.repository}/pulls/{metadata.number}"
        )
        return str(payload["head"]["sha"])

    async def _pull_files(self, parsed: ParsedGitHubUrl) -> list[ChangedFile]:
        results: list[ChangedFile] = []
        for page in range(1, 101):
            payload = await self._get(
                f"/repos/{parsed.owner}/{parsed.repository}/pulls/{parsed.pull_number}/files",
                params={"per_page": "100", "page": str(page)},
            )
            if not isinstance(payload, list):
                raise ExternalServiceError("GitHub returned an unexpected pull-request file list.")
            for item in payload:
                results.append(
                    ChangedFile(
                        path=str(item["filename"]),
                        previous_path=str(item.get("previous_filename") or ""),
                        status=str(item.get("status") or "modified"),
                        additions=int(item.get("additions") or 0),
                        deletions=int(item.get("deletions") or 0),
                        patch=str(item.get("patch") or ""),
                    )
                )
            if len(payload) < 100:
                return results
        raise ExternalServiceError("The pull request exceeds GitHub's 3,000-file review limit.")

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            response = await self.client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"GitHub could not be reached: {exc}") from exc
        if response.status_code in {401, 403}:
            remaining = response.headers.get("x-ratelimit-remaining")
            if remaining == "0":
                raise AuthenticationError(
                    "GitHub's anonymous rate limit is exhausted. Add a read-only GitHub token."
                )
            raise AuthenticationError(
                "GitHub denied access. For private repositories, add a fine-grained read-only token "
                "with Contents and Pull requests access."
            )
        if response.status_code == 404:
            raise AuthenticationError(
                "GitHub could not find this resource. Check the link or provide access for a private repository."
            )
        if response.status_code >= 400:
            request_id = response.headers.get("x-github-request-id", "unknown")
            raise ExternalServiceError(
                f"GitHub returned HTTP {response.status_code} (request {request_id})."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ExternalServiceError("GitHub returned an invalid response.") from exc
