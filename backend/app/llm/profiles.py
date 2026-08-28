"""Immutable public LLM model profiles for M5.8."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMProviderProtocol(str, Enum):
    MOCK = "mock"
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"


class LLMCapabilityFlags(BaseModel):
    model_config = ConfigDict(frozen=True)

    json_object_response: bool = True
    deterministic_temperature: bool = True


class LLMPricingMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_cost_per_million_tokens: float | None = Field(default=None, ge=0)
    output_cost_per_million_tokens: float | None = Field(default=None, ge=0)


class LLMModelProfile(BaseModel):
    """Immutable protocol/model configuration without credentials."""

    model_config = ConfigDict(frozen=True)

    profile_key: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    display_name: str = Field(min_length=1)
    provider_protocol: LLMProviderProtocol
    base_url: str = Field(default="", repr=False)
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(gt=0)
    capabilities: LLMCapabilityFlags = Field(default_factory=LLMCapabilityFlags)
    pricing: LLMPricingMetadata | None = None

    @field_validator("profile_key", "display_name", "model")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("base_url")
    @classmethod
    def _strip_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")


class LLMProfileCatalogItem(BaseModel):
    profile_key: str
    display_name: str
    provider_protocol: LLMProviderProtocol
    model: str
    available: bool
    default: bool = False
    unavailable_reason: str | None = None


class LLMProfileCatalogResponse(BaseModel):
    items: list[LLMProfileCatalogItem]


def mock_profile() -> LLMModelProfile:
    return LLMModelProfile(
        profile_key="mock",
        display_name="Mock",
        provider_protocol=LLMProviderProtocol.MOCK,
        base_url="",
        model="mock-llm",
        timeout_seconds=1.0,
        capabilities=LLMCapabilityFlags(
            json_object_response=False,
            deterministic_temperature=False,
        ),
    )
