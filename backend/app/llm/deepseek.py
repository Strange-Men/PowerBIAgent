"""Backward-compatible DeepSeek profile wrapper over the shared provider."""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from backend.app.llm.openai_compatible import (
    OpenAICompatibleLLMProvider,
    classify_openai_compatible_http_error,
)
from backend.app.llm.profiles import (
    LLMCapabilityFlags,
    LLMModelProfile,
    LLMProviderProtocol,
)


def _classify_http_error(status_code: int, provider: str = "deepseek"):
    """Compatibility shim for the historical unit-test/API surface."""
    del provider
    return classify_openai_compatible_http_error(status_code)


class DeepSeekLLMProvider(OpenAICompatibleLLMProvider):
    """Compatibility constructor; all protocol logic lives in the shared class."""

    PROVIDER_NAME = "deepseek"

    def __init__(
        self,
        api_key: SecretStr | str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not model or not model.strip():
            from backend.app.llm.base import LLMConfigurationError

            raise LLMConfigurationError(
                "DeepSeek Model 为空",
                provider=self.PROVIDER_NAME,
                error_code="invalid_model",
            )
        super().__init__(
            profile=LLMModelProfile(
                profile_key=self.PROVIDER_NAME,
                display_name="DeepSeek",
                provider_protocol=LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
                capabilities=LLMCapabilityFlags(
                    json_object_response=True,
                    deterministic_temperature=True,
                ),
            ),
            api_key=api_key,
            client=client,
        )
