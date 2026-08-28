"""Immutable-profile LLM provider registry."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.llm.base import LLMConfigurationError, LLMProvider
from backend.app.llm.profiles import (
    LLMModelProfile,
    LLMProfileCatalogItem,
    LLMProfileCatalogResponse,
)


class LLMProfileUnavailableError(LLMConfigurationError):
    """A known public profile cannot be used with current configuration."""


class LLMProfileNotFoundError(KeyError):
    """The requested public profile key is not registered."""


@dataclass(frozen=True)
class LLMProviderSnapshot:
    """The immutable provider/profile pair selected for one turn."""

    profile: LLMModelProfile
    provider: LLMProvider


@dataclass(frozen=True)
class _RegistryEntry:
    profile: LLMModelProfile
    provider: LLMProvider | None
    unavailable_reason: str | None = None


class LLMProviderRegistry:
    """Explicit profile registry with no process-global mutable default."""

    def __init__(self) -> None:
        self._entries: dict[str, _RegistryEntry] = {}

    def register(
        self,
        profile: LLMModelProfile,
        provider: LLMProvider | None,
        *,
        unavailable_reason: str | None = None,
    ) -> None:
        key = profile.profile_key
        if key in self._entries:
            raise ValueError(f"LLM profile '{key}' already registered")
        if provider is None and not unavailable_reason:
            raise ValueError("unavailable profile requires a safe reason")
        self._entries[key] = _RegistryEntry(profile, provider, unavailable_reason)

    def get(self, profile_key: str) -> LLMProviderSnapshot:
        try:
            entry = self._entries[profile_key]
        except KeyError:
            raise LLMProfileNotFoundError(
                f"LLM profile '{profile_key}' not found. Available: {self.list_profiles()}"
            ) from None
        if entry.provider is None:
            raise LLMProfileUnavailableError(
                "Selected LLM profile is unavailable",
                provider=profile_key,
                retryable=False,
                error_code="profile_unavailable",
            )
        return LLMProviderSnapshot(profile=entry.profile, provider=entry.provider)

    def list_profiles(self) -> list[str]:
        return list(self._entries)

    def list_providers(self) -> list[str]:
        """Compatibility name; returns profile keys, not mutable defaults."""
        return self.list_profiles()

    def public_catalog(
        self,
        *,
        default_profile_key: str,
        include_keys: set[str] | None = None,
    ) -> LLMProfileCatalogResponse:
        items = []
        for key, entry in self._entries.items():
            if include_keys is not None and key not in include_keys:
                continue
            items.append(
                LLMProfileCatalogItem(
                    profile_key=key,
                    display_name=entry.profile.display_name,
                    provider_protocol=entry.profile.provider_protocol,
                    model=entry.profile.model,
                    available=entry.provider is not None,
                    default=key == default_profile_key,
                    unavailable_reason=entry.unavailable_reason,
                )
            )
        return LLMProfileCatalogResponse(items=items)

    async def aclose(self) -> None:
        closed: set[int] = set()
        for entry in self._entries.values():
            provider = entry.provider
            if provider is None or id(provider) in closed:
                continue
            closed.add(id(provider))
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()

    def __repr__(self) -> str:
        availability = {
            key: entry.provider is not None for key, entry in self._entries.items()
        }
        return f"LLMProviderRegistry(profiles={availability!r})"
