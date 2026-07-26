from __future__ import annotations

import json
import zlib
from dataclasses import replace

import httpx
import pytest
import respx

from aqa_ai_workflows_pe.adapters.ai.providers import _decode_provider_body, create_provider
from aqa_ai_workflows_pe.domain.errors import ProviderError
from aqa_ai_workflows_pe.domain.models import ProviderConfig, ProviderName


@pytest.mark.asyncio
@respx.mock
async def test_provider_error_body_is_not_exposed(settings, context_pack) -> None:
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            400,
            headers={"x-request-id": "request-test"},
            json={"error": {"message": "echoed test-provider-secret"}},
        )
    )
    provider = create_provider(
        settings,
        ProviderConfig(provider="openai", model="gpt-test"),
        "test-provider-secret",
    )

    with pytest.raises(ProviderError) as error:
        await provider.review(context_pack, 0)

    assert "request-test" in str(error.value)
    assert "test-provider-secret" not in str(error.value)


@pytest.mark.asyncio
@respx.mock
async def test_provider_response_is_bounded(settings, context_pack) -> None:
    bounded = replace(
        settings,
        limits=replace(settings.limits, provider_response_bytes=32),
    )
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(200, content=b"x" * 33)
    )
    provider = create_provider(
        bounded,
        ProviderConfig(provider="openai", model="gpt-test"),
        "test-provider-secret",
    )

    with pytest.raises(ProviderError, match="safety limit"):
        await provider.review(context_pack, 0)


def test_provider_tolerates_plain_json_with_incorrect_compression_header() -> None:
    body = b'{"status":"completed"}'

    assert _decode_provider_body(body, "deflate", max_response_bytes=64) == body


def test_provider_decodes_bounded_deflate_response() -> None:
    body = b'{"status":"completed"}'

    assert _decode_provider_body(zlib.compress(body), "deflate", max_response_bytes=64) == body


def test_compressed_provider_response_is_bounded_after_decompression() -> None:
    compressed = zlib.compress(json.dumps({"padding": "x" * 512}).encode())
    assert len(compressed) < 64

    with pytest.raises(ProviderError, match="safety limit"):
        _decode_provider_body(compressed, "deflate", max_response_bytes=64)


@pytest.mark.asyncio
@respx.mock
async def test_openai_responses_shape(settings, context_pack, provider_review) -> None:
    route = respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": provider_review.model_dump_json(),
                            }
                        ],
                    }
                ],
            },
        )
    )
    provider = create_provider(
        settings,
        ProviderConfig(provider="openai", model="gpt-test"),
        "secret",
    )
    result = await provider.review(context_pack, 0)
    assert result.risks[0].title.startswith("A third retry")
    request = json.loads(route.calls[0].request.content)
    assert request["store"] is False
    assert request["text"]["format"]["strict"] is True
    assert route.calls[0].request.headers["authorization"] == "Bearer secret"
    assert route.calls[0].request.headers["accept-encoding"] == "identity"


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_messages_shape(settings, context_pack, provider_review) -> None:
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": provider_review.model_dump_json()}],
            },
        )
    )
    provider = create_provider(
        settings,
        ProviderConfig(provider="anthropic", model="claude-test"),
        "secret",
    )
    await provider.review(context_pack, 0)
    request = json.loads(route.calls[0].request.content)
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert route.calls[0].request.headers["anthropic-version"] == "2023-06-01"


@pytest.mark.asyncio
@respx.mock
async def test_google_structured_output_shape(settings, context_pack, provider_review) -> None:
    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": provider_review.model_dump_json()}]},
                    }
                ]
            },
        )
    )
    provider = create_provider(
        settings,
        ProviderConfig(provider="google", model="gemini-test"),
        "secret",
    )
    await provider.review(context_pack, 0)
    request = json.loads(route.calls[0].request.content)
    response_format = request["generationConfig"]["responseFormat"]["text"]
    assert response_format["mimeType"] == "application/json"
    assert "schema" in response_format
    assert "responseJsonSchema" not in request["generationConfig"]


@pytest.mark.asyncio
@respx.mock
async def test_compatible_endpoint_is_explicit(settings, context_pack, provider_review) -> None:
    route = respx.post("http://127.0.0.1:11434/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": provider_review.model_dump_json()}}]},
        )
    )
    provider = create_provider(
        settings,
        ProviderConfig(
            provider="compatible",
            model="local-model",
            base_url="http://127.0.0.1:11434/v1",
            credential_source="none",
            destination_class="local",
        ),
        "",
    )
    await provider.review(context_pack, 0)
    request = json.loads(route.calls[0].request.content)
    assert request["response_format"]["type"] == "json_schema"
    assert "authorization" not in route.calls[0].request.headers


@pytest.mark.asyncio
async def test_fake_provider_has_no_network(settings, context_pack) -> None:
    provider = create_provider(
        settings,
        ProviderConfig(
            provider=ProviderName.FAKE,
            model="deterministic-demo-v1",
            credential_source="none",
            destination_class="local",
        ),
        "",
    )
    result = await provider.review(context_pack, 0)
    assert result.context_requests == []
    assert "Demo mode" in result.limitations[0]
