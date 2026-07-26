from __future__ import annotations

import json
import zlib
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from ...config import Settings
from ...domain.errors import InputError, ProviderError, ProviderRefusalError
from ...domain.models import (
    ContextPack,
    DraftRisk,
    ExploratoryCharter,
    ProductImpact,
    ProviderConfig,
    ProviderName,
    ProviderReview,
    ServiceImpact,
    TestScenario,
)
from ...version import __version__
from .prompts import SYSTEM_PROMPT, review_prompt
from .schema import provider_review_schema


class AIProvider(ABC):
    def __init__(self, settings: Settings, config: ProviderConfig, api_key: str) -> None:
        self.settings = settings
        self.config = config
        self.api_key = api_key

    @property
    @abstractmethod
    def destination(self) -> str: ...

    @abstractmethod
    async def review(self, pack: ContextPack, round_number: int) -> ProviderReview: ...

    async def test_connection(self) -> None:
        if self.config.provider == ProviderName.FAKE:
            return
        if self.config.provider != ProviderName.COMPATIBLE and not self.api_key:
            raise InputError("Add an API key to this model in your local Profile.")

    def _validate(self, payload: Any) -> ProviderReview:
        try:
            return ProviderReview.model_validate(payload)
        except ValidationError as exc:
            raise ProviderError(
                "The model returned data that did not match the review contract. "
                f"Try the same request again or choose a stronger model. Details: {exc.errors()[0]['msg']}"
            ) from exc


class OpenAIProvider(AIProvider):
    @property
    def destination(self) -> str:
        return "api.openai.com"

    async def review(self, pack: ContextPack, round_number: int) -> ProviderReview:
        await self.test_connection()
        payload = {
            "model": self.config.model,
            "store": False,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": review_prompt(pack, round_number)}],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "aqa_ai_workflows_pe",
                    "description": "Evidence-backed Product and QA change-impact review.",
                    "schema": provider_review_schema(),
                    "strict": True,
                }
            },
            "max_output_tokens": 16_000,
        }
        response = await _post_json(
            "https://api.openai.com/v1/responses",
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.settings.provider_timeout_seconds,
            max_response_bytes=self.settings.limits.provider_response_bytes,
        )
        if response.get("status") == "incomplete":
            raise ProviderError(
                "OpenAI stopped before the complete structured review was generated."
            )
        text = _openai_text(response)
        return self._validate(_parse_json(text))


class AnthropicProvider(AIProvider):
    @property
    def destination(self) -> str:
        return "api.anthropic.com"

    async def review(self, pack: ContextPack, round_number: int) -> ProviderReview:
        await self.test_connection()
        payload = {
            "model": self.config.model,
            "max_tokens": 16_000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": review_prompt(pack, round_number)}],
            "output_config": {
                "format": {"type": "json_schema", "schema": provider_review_schema()}
            },
        }
        response = await _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=self.settings.provider_timeout_seconds,
            max_response_bytes=self.settings.limits.provider_response_bytes,
        )
        stop_reason = response.get("stop_reason")
        if stop_reason == "refusal":
            raise ProviderRefusalError("Anthropic refused this review request.")
        if stop_reason == "max_tokens":
            raise ProviderError("Anthropic reached the output limit before completing the review.")
        blocks = response.get("content") or []
        text = "".join(
            str(block.get("text", "")) for block in blocks if block.get("type") == "text"
        )
        return self._validate(_parse_json(text))


class GoogleProvider(AIProvider):
    @property
    def destination(self) -> str:
        return "generativelanguage.googleapis.com"

    async def review(self, pack: ContextPack, round_number: int) -> ProviderReview:
        await self.test_connection()
        model = self.config.model.strip()
        if not model or "/" in model:
            raise InputError("Enter a Gemini model ID such as gemini-3.5-flash.")
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": review_prompt(pack, round_number)}]}],
            "generationConfig": {
                "responseFormat": {
                    "text": {
                        "mimeType": "application/json",
                        "schema": provider_review_schema(),
                    }
                },
                "maxOutputTokens": 16_000,
            },
        }
        response = await _post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            payload,
            headers={"x-goog-api-key": self.api_key},
            timeout=self.settings.provider_timeout_seconds,
            max_response_bytes=self.settings.limits.provider_response_bytes,
        )
        candidates = response.get("candidates") or []
        if not candidates:
            raise ProviderError("Gemini returned no review candidate.")
        finish = candidates[0].get("finishReason")
        if finish not in {None, "STOP"}:
            raise ProviderError(f"Gemini stopped before completing the review ({finish}).")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(str(part.get("text", "")) for part in parts)
        return self._validate(_parse_json(text))


class CompatibleProvider(AIProvider):
    def __init__(self, settings: Settings, config: ProviderConfig, api_key: str) -> None:
        super().__init__(settings, config, api_key)
        self.base_url = _validate_compatible_url(config.base_url)

    @property
    def destination(self) -> str:
        parsed = urlsplit(self.base_url)
        return parsed.netloc

    async def review(self, pack: ContextPack, round_number: int) -> ProviderReview:
        if not self.config.model:
            raise InputError("Enter the model ID exposed by the compatible endpoint.")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": review_prompt(pack, round_number)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "aqa_ai_workflows_pe",
                    "strict": True,
                    "schema": provider_review_schema(),
                },
            },
        }
        response = await _post_json(
            f"{self.base_url}/chat/completions",
            payload,
            headers=headers,
            timeout=self.settings.provider_timeout_seconds,
            max_response_bytes=self.settings.limits.provider_response_bytes,
        )
        choices = response.get("choices") or []
        if not choices:
            raise ProviderError("The compatible endpoint returned no completion choice.")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list):
            text = "".join(str(item.get("text", "")) for item in content)
        else:
            text = str(content or "")
        return self._validate(_parse_json(text))


class FakeProvider(AIProvider):
    @property
    def destination(self) -> str:
        return "local deterministic demo"

    async def review(self, pack: ContextPack, round_number: int) -> ProviderReview:
        citation = pack.evidence[0].id
        changed = [item for item in pack.evidence if item.source_kind.value == "pull_request"]
        change_citation = changed[1].id if len(changed) > 1 else citation
        paths = [item.path for item in pack.pull_request.changed_files]
        path_summary = ", ".join(paths[:4]) or "the changed path"
        return ProviderReview(
            change_summary=f"The pull request changes {path_summary}.",
            intended_outcome=pack.pull_request.title,
            product_impact=ProductImpact(
                outcome="Validate the intended change without overstating runtime behavior.",
                affected_users=["Users of the changed product flow"],
                affected_journeys=["The journey connected to the changed files"],
                business_rules=["Confirm the acceptance rule described by the pull request"],
                data_and_interfaces=["Check changed inputs, outputs, and compatibility boundaries"],
                operations_and_rollout=["Check rollout, monitoring, and rollback expectations"],
                assumptions=["The repository evidence does not contain live production behavior"],
                evidence_ids=[citation, change_citation],
            ),
            gaps_and_questions=[
                "What measurable business or user outcome defines success for this change?",
                "Which downstream consumers and rollback conditions are release-critical?",
            ],
            risks=[
                DraftRisk(
                    title="Changed behavior may diverge from an unstated product rule",
                    hypothesis=(
                        "If the acceptance rule is incomplete, valid edge states may behave differently "
                        "from Product expectations."
                    ),
                    impact_reason="The changed journey could produce a user-visible mismatch.",
                    likelihood_reason="The PR evidence cannot confirm every business rule.",
                    regression_reason="Changed interfaces can affect callers beyond the edited file.",
                    detectability_reason="A focused exploratory pass is needed to observe the behavior.",
                    evidence_strength_reason="The change is cited, while the business outcome is inferred.",
                    impact=4,
                    likelihood=3,
                    regression_reach=3,
                    detectability=3,
                    evidence_strength=2,
                    evidence_ids=[citation, change_citation],
                )
            ],
            scenarios=[
                TestScenario(
                    id="",
                    title="Validate the intended change through the primary customer journey",
                    priority="P1",
                    objective="Confirm the expected outcome and protect the unchanged baseline.",
                    preconditions=["Use representative data and a supported environment"],
                    steps=[
                        "Exercise the expected changed path",
                        "Repeat with boundary and invalid input",
                        "Verify the previous supported path remains intact",
                    ],
                    expected_signals=[
                        "The documented outcome is visible",
                        "Errors are actionable and no unrelated state changes occur",
                    ],
                    risk_titles=["Changed behavior may diverge from an unstated product rule"],
                    evidence_ids=[citation, change_citation],
                    test_layer="manual",
                )
            ],
            exploratory_charters=[
                ExploratoryCharter(
                    title="Changed-flow boundaries and recovery",
                    mission="Explore transitions, interruptions, retries, permissions, and recovery.",
                    focus_areas=[
                        "boundaries",
                        "state transitions",
                        "failure recovery",
                        "observability",
                    ],
                    stop_conditions=[
                        "Major ambiguity is recorded",
                        "High-impact paths have evidence",
                    ],
                    evidence_ids=[change_citation],
                )
            ],
            service_impacts=[
                ServiceImpact(
                    service=repository.alias,
                    relationship=repository.relationship,
                    possible_impact="Review matching contracts and consumer expectations.",
                    confidence="inferred",
                    evidence_ids=[change_citation],
                )
                for repository in pack.repositories[1:]
            ],
            context_requests=[],
            limitations=[
                "Demo mode is deterministic and does not call an AI model.",
                "Source and tests were inspected but not executed.",
            ],
        )


def create_provider(settings: Settings, config: ProviderConfig, api_key: str) -> AIProvider:
    providers = {
        ProviderName.OPENAI: OpenAIProvider,
        ProviderName.ANTHROPIC: AnthropicProvider,
        ProviderName.GOOGLE: GoogleProvider,
        ProviderName.COMPATIBLE: CompatibleProvider,
        ProviderName.FAKE: FakeProvider,
    }
    return providers[config.provider](settings, config, api_key)


async def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: float,
    max_response_bytes: int,
) -> dict[str, Any]:
    request_headers = {
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "User-Agent": f"aqa-ai-workflows-pe/{__version__}",
    }
    request_headers.update(headers)
    try:
        async with (
            httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client,
            client.stream("POST", url, json=payload, headers=request_headers) as streamed,
        ):
            raw_body = bytearray()
            async for chunk in streamed.aiter_raw():
                raw_body.extend(chunk)
                if len(raw_body) > max_response_bytes:
                    raise _provider_response_limit_error()
            body = _decode_provider_body(
                bytes(raw_body),
                streamed.headers.get("content-encoding", ""),
                max_response_bytes=max_response_bytes,
            )
            response_headers = httpx.Headers(streamed.headers)
            response_headers.pop("content-encoding", None)
            response_headers.pop("content-length", None)
            response = httpx.Response(
                streamed.status_code,
                headers=response_headers,
                content=body,
                request=streamed.request,
            )
    except httpx.HTTPError as exc:
        raise ProviderError(f"The selected AI provider could not be reached: {exc}") from exc
    if response.status_code in {401, 403}:
        raise ProviderError("The selected AI provider rejected the credential or model access.")
    if response.status_code == 429:
        raise ProviderError("The selected AI provider is rate-limited. Wait briefly and retry.")
    if response.status_code >= 400:
        request_id = response.headers.get("x-request-id", "unknown")
        detail = {
            400: "The provider rejected the request or model configuration.",
            404: "The configured model or endpoint was not found.",
            413: "The approved Context Pack exceeds the provider request limit.",
        }.get(response.status_code)
        if detail is None and response.status_code >= 500:
            detail = "The selected AI provider is temporarily unavailable."
        detail = detail or "The selected AI provider rejected the request."
        raise ProviderError(
            f"The selected AI provider returned HTTP {response.status_code} "
            f"(request {request_id}): {detail}"
        )
    try:
        result = response.json()
    except ValueError as exc:
        raise ProviderError("The selected AI provider returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise ProviderError("The selected AI provider returned an unexpected response shape.")
    return result


def _decode_provider_body(
    body: bytes,
    content_encoding: str,
    *,
    max_response_bytes: int,
) -> bytes:
    encodings = [
        value.strip().casefold()
        for value in content_encoding.split(",")
        if value.strip() and value.strip().casefold() != "identity"
    ]
    if not encodings or _looks_like_json(body):
        return body

    decoded = body
    for encoding in reversed(encodings):
        if encoding in {"gzip", "x-gzip"}:
            try:
                decoded = _bounded_zlib_decompress(
                    decoded,
                    zlib.MAX_WBITS | 16,
                    max_response_bytes=max_response_bytes,
                )
            except zlib.error as exc:
                raise ProviderError(
                    "The selected AI provider returned an unreadable compressed response. "
                    "Retry the review or check any local proxy or VPN."
                ) from exc
        elif encoding == "deflate":
            decoded = _decode_deflate(decoded, max_response_bytes=max_response_bytes)
        else:
            raise ProviderError(
                "The selected AI provider returned an unsupported compressed response. "
                "Retry the review or check any local proxy or VPN."
            )
    if len(decoded) > max_response_bytes:
        raise _provider_response_limit_error()
    return decoded


def _decode_deflate(body: bytes, *, max_response_bytes: int) -> bytes:
    errors: list[zlib.error] = []
    for window_bits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            return _bounded_zlib_decompress(
                body,
                window_bits,
                max_response_bytes=max_response_bytes,
            )
        except zlib.error as exc:
            errors.append(exc)
    raise ProviderError(
        "The selected AI provider returned an unreadable compressed response. "
        "Retry the review or check any local proxy or VPN."
    ) from errors[-1]


def _bounded_zlib_decompress(
    body: bytes,
    window_bits: int,
    *,
    max_response_bytes: int,
) -> bytes:
    decompressor = zlib.decompressobj(window_bits)
    decoded = decompressor.decompress(body, max_response_bytes + 1)
    if len(decoded) > max_response_bytes or decompressor.unconsumed_tail:
        raise _provider_response_limit_error()
    decoded += decompressor.flush(max_response_bytes + 1 - len(decoded))
    if len(decoded) > max_response_bytes:
        raise _provider_response_limit_error()
    if not decompressor.eof:
        raise zlib.error("incomplete compressed response")
    return decoded


def _looks_like_json(body: bytes) -> bool:
    return body.lstrip().startswith((b"{", b"["))


def _provider_response_limit_error() -> ProviderError:
    return ProviderError(
        "The selected AI provider returned a response above the local 8 MB safety limit."
    )


def _parse_json(value: str) -> Any:
    if not value.strip():
        raise ProviderError("The selected AI provider returned an empty review.")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            "The selected AI provider returned malformed structured output."
        ) from exc


def _openai_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "refusal":
                raise ProviderRefusalError(
                    str(content.get("refusal") or "OpenAI refused the request.")
                )
            if content.get("type") == "output_text":
                texts.append(str(content.get("text") or ""))
    return "".join(texts)


def _validate_compatible_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url:
        url = "http://127.0.0.1:11434/v1"
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise InputError(
            "Compatible endpoint URLs cannot contain credentials, queries, or fragments."
        )
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if parsed.hostname in local_hosts:
        if parsed.scheme != "http":
            raise InputError("Local compatible endpoints must use loopback HTTP.")
    elif parsed.scheme != "https":
        raise InputError("Non-local compatible endpoints must use HTTPS.")
    if not parsed.hostname:
        raise InputError("Enter a valid OpenAI-compatible base URL ending in /v1.")
    return url
