"""Typed display metadata that cannot alter canonical semantic identity."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class LocalizationSource(str, Enum):
    MODEL_METADATA = "model_metadata"
    GLOSSARY = "glossary"
    REGISTRY = "registry"
    LLM_TRANSLATION = "llm_translation"
    HUMANIZED_FALLBACK = "humanized_fallback"
    CANONICAL_FALLBACK = "canonical_fallback"


class LocalizationRecord(BaseModel):
    semantic_model_key: str = Field(min_length=1)
    object_identity: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    locale: str = Field(default="zh-CN", min_length=2)
    display_name: str = Field(min_length=1, max_length=80)
    source: LocalizationSource
    schema_identity: str = Field(min_length=64, max_length=64)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ResolvedLocalization(LocalizationRecord):
    """Request-local display profile; formatting hints stay non-authoritative."""

    table_name: str = Field(min_length=1)
    data_type: str = ""
    format_string: str | None = None

    def result_field_aliases(self) -> tuple[str, ...]:
        if self.object_type == "measure":
            return (self.canonical_name, f"[{self.canonical_name}]")
        return (
            self.canonical_name,
            f"{self.table_name}[{self.canonical_name}]",
        )
