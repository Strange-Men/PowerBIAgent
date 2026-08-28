"""LLM Provider 层"""

from backend.app.llm.base import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMErrorCategory,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMRequestError,
    LLMResponse,
    LLMResponseError,
    LLMScenarioNotFoundError,
    LLMServiceError,
    LLMTask,
    LLMTimeoutError,
    LLMValidationError,
)
from backend.app.llm.deepseek import DeepSeekLLMProvider
from backend.app.llm.factory import build_llm_registry
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.llm.profiles import (
    LLMCapabilityFlags,
    LLMModelProfile,
    LLMProfileCatalogItem,
    LLMProfileCatalogResponse,
    LLMProviderProtocol,
    LLMPricingMetadata,
)
from backend.app.llm.registry import (
    LLMProfileUnavailableError,
    LLMProfileNotFoundError,
    LLMProviderRegistry,
    LLMProviderSnapshot,
)

__all__ = [
    "build_llm_registry",
    "DeepSeekLLMProvider",
    "LLMAuthenticationError",
    "LLMConfigurationError",
    "LLMConnectionError",
    "LLMErrorCategory",
    "LLMCapabilityFlags",
    "LLMModelProfile",
    "LLMProfileCatalogItem",
    "LLMProfileCatalogResponse",
    "LLMPricingMetadata",
    "LLMProviderProtocol",
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderRegistry",
    "LLMProviderSnapshot",
    "LLMProfileUnavailableError",
    "LLMProfileNotFoundError",
    "LLMRateLimitError",
    "LLMRequest",
    "LLMRequestError",
    "LLMResponse",
    "LLMResponseError",
    "LLMScenarioNotFoundError",
    "LLMServiceError",
    "LLMTask",
    "LLMTimeoutError",
    "LLMValidationError",
    "MockLLMProvider",
    "OpenAICompatibleLLMProvider",
]
