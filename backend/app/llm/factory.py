"""Build the application-scoped immutable-profile LLM registry."""

from __future__ import annotations

import httpx

from backend.app.config.settings import LLMMode, Settings
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.llm.profiles import (
    LLMCapabilityFlags,
    LLMModelProfile,
    LLMProviderProtocol,
    LLMPricingMetadata,
    mock_profile,
)
from backend.app.llm.registry import LLMProviderRegistry


def _pricing(input_price: float | None, output_price: float | None) -> LLMPricingMetadata | None:
    if input_price is None and output_price is None:
        return None
    return LLMPricingMetadata(
        input_cost_per_million_tokens=input_price,
        output_cost_per_million_tokens=output_price,
    )


def _openai_profile(
    *,
    key: str,
    display_name: str,
    base_url: str,
    model: str,
    settings: Settings,
    input_price: float | None,
    output_price: float | None,
) -> LLMModelProfile:
    return LLMModelProfile(
        profile_key=key,
        display_name=display_name,
        provider_protocol=LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        base_url=base_url,
        model=model,
        timeout_seconds=float(settings.request_timeout_seconds),
        capabilities=LLMCapabilityFlags(
            json_object_response=True,
            deterministic_temperature=True,
        ),
        pricing=_pricing(input_price, output_price),
    )


def build_llm_registry(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> LLMProviderRegistry:
    registry = LLMProviderRegistry()
    registry.register(mock_profile(), MockLLMProvider())

    if settings.llm_mode == LLMMode.MOCK:
        return registry

    deepseek_profile = _openai_profile(
        key="deepseek",
        display_name="DeepSeek",
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        settings=settings,
        input_price=settings.deepseek_input_cost_per_million_tokens,
        output_price=settings.deepseek_output_cost_per_million_tokens,
    )
    registry.register(
        deepseek_profile,
        OpenAICompatibleLLMProvider(
            profile=deepseek_profile,
            api_key=settings.deepseek_api_key,  # type: ignore[arg-type]
            client=client,
        ) if settings.is_deepseek_configured else None,
        unavailable_reason=None if settings.is_deepseek_configured else "api_key_missing",
    )

    kimi_profile = _openai_profile(
        key="kimi-k2.6",
        display_name="Kimi K2.6",
        base_url=settings.kimi_base_url,
        model=settings.kimi_model,
        settings=settings,
        input_price=settings.kimi_input_cost_per_million_tokens,
        output_price=settings.kimi_output_cost_per_million_tokens,
    )
    registry.register(
        kimi_profile,
        OpenAICompatibleLLMProvider(
            profile=kimi_profile,
            api_key=settings.kimi_api_key,  # type: ignore[arg-type]
            client=client,
        ) if settings.is_kimi_configured else None,
        unavailable_reason=None if settings.is_kimi_configured else "configuration_missing",
    )

    return registry
