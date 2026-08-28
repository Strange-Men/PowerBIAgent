"""M5.8 multi-LLM profile and OpenAI-compatible provider contracts."""

from __future__ import annotations

import json
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from backend.app.llm.base import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    LLMValidationError,
)
from backend.app.llm.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.llm.profiles import (
    LLMCapabilityFlags,
    LLMModelProfile,
    LLMProviderProtocol,
    LLMPricingMetadata,
)
from backend.app.llm.registry import (
    LLMProfileUnavailableError,
    LLMProviderRegistry,
)
from backend.app.application.deepseek_turn_service import DeepSeekTurnService
from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.memory.request_fingerprint import RequestFingerprint
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer
from backend.app.harness.observability.llm_observer import (
    LLMCallCollector,
    ObservedLLMProvider,
)


class _StructuredResult(BaseModel):
    status: str
    value: int


def _profile(key: str, model: str) -> LLMModelProfile:
    return LLMModelProfile(
        profile_key=key,
        display_name="DeepSeek" if key == "deepseek" else "Kimi K2.6",
        provider_protocol=LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        base_url=(
            "https://api.deepseek.com/v1"
            if key == "deepseek"
            else "https://gateway.example.test/v1"
        ),
        model=model,
        timeout_seconds=17.0,
        capabilities=LLMCapabilityFlags(
            json_object_response=True,
            deterministic_temperature=True,
        ),
        pricing=LLMPricingMetadata(
            input_cost_per_million_tokens=1.0,
            output_cost_per_million_tokens=2.0,
        ),
    )


def _response(content: object, *, model: str) -> httpx.Response:
    raw = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [
                {
                    "message": {"role": "assistant", "content": raw},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
    )


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": "Return one JSON object."}]
    )


@pytest.mark.parametrize(
    ("profile_key", "model"),
    [("deepseek", "deepseek-chat"), ("kimi-k2.6", "azure/Kimi-K2.6")],
)
@pytest.mark.asyncio
async def test_profiles_share_one_openai_compatible_wire_contract(
    profile_key: str,
    model: str,
) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["payload"] = json.loads(request.content)
        return _response({"status": "ok", "value": 42}, model=model)

    provider = OpenAICompatibleLLMProvider(
        profile=_profile(profile_key, model),
        api_key=SecretStr("unit-secret-must-not-leak"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await provider.generate(_request(), _StructuredResult)

    assert result.structured == _StructuredResult(status="ok", value=42)
    assert seen["url"] == f"{provider.profile.base_url}/chat/completions"
    assert seen["authorization"] == "Bearer unit-secret-must-not-leak"
    assert seen["payload"] == {
        "model": model,
        "messages": _request().messages,
        "stream": False,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    assert result.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }


@pytest.mark.asyncio
async def test_safe_markdown_fence_normalization_does_not_invent_fields() -> None:
    provider = OpenAICompatibleLLMProvider(
        profile=_profile("kimi-k2.6", "azure/Kimi-K2.6"),
        api_key="unit-secret",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: _response(
                    '```json\n{"status":"ok","value":7}\n```',
                    model="azure/Kimi-K2.6",
                )
            )
        ),
    )
    result = await provider.generate(_request(), _StructuredResult)
    assert result.structured == _StructuredResult(status="ok", value=7)

    invalid = OpenAICompatibleLLMProvider(
        profile=_profile("kimi-k2.6", "azure/Kimi-K2.6"),
        api_key="unit-secret",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: _response(
                    '```json\n{"status":"ok"}\n```',
                    model="azure/Kimi-K2.6",
                )
            )
        ),
    )
    with pytest.raises(LLMValidationError):
        await invalid.generate(_request(), _StructuredResult)


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, LLMAuthenticationError),
        (403, LLMAuthenticationError),
        (429, LLMRateLimitError),
        (500, LLMServiceError),
        (502, LLMServiceError),
        (503, LLMServiceError),
    ],
)
@pytest.mark.asyncio
async def test_provider_independent_http_error_taxonomy(
    status_code: int,
    error_type: type[Exception],
) -> None:
    provider = OpenAICompatibleLLMProvider(
        profile=_profile("kimi-k2.6", "azure/Kimi-K2.6"),
        api_key="unit-secret",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status_code, json={"error": {}})
            )
        ),
    )
    with pytest.raises(error_type) as exc:
        await provider.generate(_request(), _StructuredResult)
    assert exc.value.provider == "kimi-k2.6"


@pytest.mark.asyncio
async def test_timeout_and_invalid_response_fail_closed() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    timeout_provider = OpenAICompatibleLLMProvider(
        profile=_profile("deepseek", "deepseek-chat"),
        api_key="unit-secret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)),
    )
    with pytest.raises(LLMTimeoutError):
        await timeout_provider.generate(_request(), _StructuredResult)

    malformed = OpenAICompatibleLLMProvider(
        profile=_profile("deepseek", "deepseek-chat"),
        api_key="unit-secret",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"not-json")
            )
        ),
    )
    with pytest.raises(LLMResponseError):
        await malformed.generate(_request(), _StructuredResult)


def test_registry_requires_explicit_key_and_has_no_mutable_default() -> None:
    registry = LLMProviderRegistry()
    profile = _profile("deepseek", "deepseek-chat")
    provider = OpenAICompatibleLLMProvider(profile=profile, api_key="unit-secret")
    registry.register(profile, provider)

    snapshot = registry.get("deepseek")
    assert snapshot.profile is profile
    assert snapshot.provider is provider
    assert not hasattr(registry, "set_default")
    with pytest.raises(TypeError):
        registry.get()  # type: ignore[call-arg]
    with pytest.raises(KeyError):
        registry.get("unknown")


def test_registry_rejects_known_but_unavailable_profile() -> None:
    registry = LLMProviderRegistry()
    profile = _profile("kimi-k2.6", "azure/Kimi-K2.6")
    registry.register(profile, None, unavailable_reason="api_key_missing")

    with pytest.raises(LLMProfileUnavailableError) as exc:
        registry.get("kimi-k2.6")
    assert exc.value.error_code == "profile_unavailable"
    assert "unit-secret" not in repr(registry)


def test_profile_and_provider_repr_do_not_leak_secret_or_base_url_query() -> None:
    secret = "secret-value-must-not-appear"
    profile = _profile("kimi-k2.6", "azure/Kimi-K2.6")
    provider = OpenAICompatibleLLMProvider(profile=profile, api_key=secret)
    combined = f"{profile!r} {provider!r}"
    assert secret not in combined
    assert "Authorization" not in combined


@pytest.mark.asyncio
async def test_concurrent_turns_receive_distinct_immutable_profile_snapshots() -> None:
    registry = LLMProviderRegistry()
    deepseek = OpenAICompatibleLLMProvider(
        profile=_profile("deepseek", "deepseek-chat"), api_key="deep-secret"
    )
    kimi = OpenAICompatibleLLMProvider(
        profile=_profile("kimi-k2.6", "azure/Kimi-K2.6"), api_key="kimi-secret"
    )
    registry.register(deepseek.profile, deepseek)
    registry.register(kimi.profile, kimi)
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.OPENAI_COMPATIBLE,
        powerbi_mode=PowerBIMode.MOCK,
        llm_default_profile="deepseek",
    )
    service = DeepSeekTurnService(
        memory_repo=InMemoryMemoryRepository(),
        llm_provider=None,
        llm_registry=registry,
        powerbi_adapter=MockPowerBIAdapter(),
        report_renderer=MockReportRenderer(),
        settings=settings,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    snapshots = {}

    async def capture(**kwargs):
        snapshots[kwargs["conversation_id"]] = kwargs["llm_snapshot"]
        if len(snapshots) == 2:
            entered.set()
        await release.wait()
        return {"llm_profile_key": kwargs["llm_profile_key"]}

    service.pipeline.execute = AsyncMock(side_effect=capture)
    deepseek_turn = asyncio.create_task(
        service.execute(conversation_id="conv-a", llm_profile_key="deepseek", message="A")
    )
    kimi_turn = asyncio.create_task(
        service.execute(conversation_id="conv-b", llm_profile_key="kimi-k2.6", message="B")
    )
    await entered.wait()
    assert snapshots["conv-a"].provider is deepseek
    assert snapshots["conv-b"].provider is kimi
    release.set()
    await asyncio.gather(deepseek_turn, kimi_turn)


def test_profile_identity_changes_idempotency_fingerprint() -> None:
    common = {
        "message": "总销售额是多少？",
        "client_conversation_id": "conv-profile-fingerprint",
        "semantic_model_key": "local_desktop_model",
    }
    deepseek_hash = RequestFingerprint.compute_hash(
        **common, llm_profile_key="deepseek", llm_model="deepseek-chat"
    )
    kimi_hash = RequestFingerprint.compute_hash(
        **common, llm_profile_key="kimi-k2.6", llm_model="azure/Kimi-K2.6"
    )
    assert deepseek_hash != kimi_hash


@pytest.mark.asyncio
async def test_observation_uses_public_profile_and_error_taxonomy_without_secrets() -> None:
    profile = _profile("kimi-k2.6", "azure/Kimi-K2.6")
    secret = "unit-secret-must-not-leak"
    provider = OpenAICompatibleLLMProvider(
        profile=profile,
        api_key=secret,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, json={"error": {}})
            )
        ),
    )
    collector = LLMCallCollector()
    observed = ObservedLLMProvider(provider, collector, profile=profile)

    with pytest.raises(LLMRateLimitError):
        await observed.generate(_request(), _StructuredResult)

    summary = collector.summary()
    call = summary.calls[0]
    assert call["profile_key"] == "kimi-k2.6"
    assert call["provider_protocol"] == "openai_chat_completions"
    assert call["model"] == "azure/Kimi-K2.6"
    assert call["task"] == "intent_recognition"
    assert call["error_category"] == "rate_limit"
    assert secret not in json.dumps(call)
    public_usage = summary.to_dict()
    assert public_usage["per_task"] == {"intent_recognition": 1}
    assert public_usage["calls"] == [call]
    assert secret not in json.dumps(public_usage)
