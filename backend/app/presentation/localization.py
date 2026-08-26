"""Model/object/schema-scoped display localization.

Canonical runtime identities are inputs, never outputs of this module.  A
bounded translator can only label candidate objects already present in the
runtime semantic catalog.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from enum import Enum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTask,
)

from backend.app.presentation.formatter import (
    PresentationFormatKind,
    PresentationFormatter,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectSource,
    SemanticObjectType,
)


_FIELD_REFERENCE = re.compile(
    r"^(?:(?P<table>.+?))?\[(?P<name>[^\[\]]+)\]$"
)
_REGISTRY_LOCK = threading.RLock()


class DisplayLocalizationSource(str, Enum):
    POWERBI_METADATA = "powerbi_metadata"
    MODEL_GLOSSARY = "model_glossary"
    REGISTRY = "registry"
    BOUNDED_TRANSLATION = "bounded_translation"
    FALLBACK = "fallback"


class DisplayLocalization(BaseModel):
    semantic_model_key: str = Field(min_length=1)
    object_identity: str = Field(min_length=1)
    object_type: SemanticObjectType
    canonical_name: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=96)
    source: DisplayLocalizationSource
    schema_identity: str = Field(min_length=64, max_length=64)
    data_type: str = "string"
    format_kind: PresentationFormatKind = PresentationFormatKind.TEXT

    model_config = ConfigDict(extra="forbid", frozen=True)


class DisplayTranslationCandidate(BaseModel):
    object_identity: str = Field(min_length=1)
    object_type: SemanticObjectType
    canonical_name: str = Field(min_length=1)
    table_name: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class DisplayTranslationChoice(BaseModel):
    object_identity: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=96)

    model_config = ConfigDict(extra="forbid", frozen=True)


class DisplayTranslationResponse(BaseModel):
    translations: list[DisplayTranslationChoice] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_unique_identities(self) -> "DisplayTranslationResponse":
        identities = [item.object_identity for item in self.translations]
        if len(identities) != len(set(identities)):
            raise ValueError("display_translation_identity_duplicate")
        return self


class DisplayTranslator(Protocol):
    async def translate(
        self,
        candidates: tuple[DisplayTranslationCandidate, ...],
        locale: str,
    ) -> dict[str, str]:
        ...


class BoundedLLMDisplayTranslator:
    """Translate labels only for code-owned runtime object identities."""

    def __init__(self, provider: LLMProvider):
        self._provider = provider

    async def translate(
        self,
        candidates: tuple[DisplayTranslationCandidate, ...],
        locale: str,
    ) -> dict[str, str]:
        if not candidates:
            return {}
        candidate_lines = "\n".join(
            f"- object_identity={item.object_identity}; "
            f"object_type={item.object_type.value}; "
            f"canonical_name={item.canonical_name}; table_name={item.table_name}"
            for item in candidates
        )
        request = LLMRequest(
            task=LLMTask.DISPLAY_TRANSLATION,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你只负责把给定 runtime 对象的显示标签翻译为目标 locale。"
                        "不得创建、删除、合并或重命名 object_identity，不得输出 DAX、"
                        "QueryPlan、事实或资源操作。只输出 JSON："
                        '{"translations":[{"object_identity":"候选ID",'
                        '"display_name":"简短标签"}]}。'
                    ),
                },
                {
                    "role": "user",
                    "content": f"目标 locale：{locale}\n候选：\n{candidate_lines}",
                },
            ],
        )
        try:
            response = await self._provider.generate(
                request, DisplayTranslationResponse
            )
        except LLMProviderError:
            return {}
        structured = response.structured
        if not isinstance(structured, DisplayTranslationResponse):
            return {}
        allowed = {item.object_identity for item in candidates}
        if any(item.object_identity not in allowed for item in structured.translations):
            return {}
        return {
            item.object_identity: item.display_name.strip()
            for item in structured.translations
            if item.display_name.strip()
        }


class DisplayLocalizationError(ValueError):
    pass


class JsonDisplayLocalizationRegistry:
    """Small process-safe persisted registry keyed by full display identity."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def get(
        self,
        *,
        semantic_model_key: str,
        schema_identity: str,
        object_identity: str,
        locale: str,
    ) -> DisplayLocalization | None:
        key = self._key(
            semantic_model_key,
            schema_identity,
            object_identity,
            locale,
        )
        with _REGISTRY_LOCK:
            data = self._read()
        raw = data.get("items", {}).get(key)
        if raw is None:
            return None
        try:
            binding = DisplayLocalization.model_validate(raw)
        except ValueError as exc:
            raise DisplayLocalizationError("display_registry_invalid") from exc
        coherent = (
            binding.semantic_model_key == semantic_model_key
            and binding.schema_identity == schema_identity
            and binding.object_identity == object_identity
            and binding.locale == locale
        )
        if not coherent:
            raise DisplayLocalizationError("display_registry_identity_mismatch")
        return binding.model_copy(update={"source": DisplayLocalizationSource.REGISTRY})

    def put(self, binding: DisplayLocalization) -> None:
        key = self._key(
            binding.semantic_model_key,
            binding.schema_identity,
            binding.object_identity,
            binding.locale,
        )
        with _REGISTRY_LOCK:
            data = self._read()
            items = data.setdefault("items", {})
            items[key] = binding.model_dump(mode="json")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"version": 1, "items": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DisplayLocalizationError("display_registry_invalid") from exc
        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or not isinstance(data.get("items"), dict)
        ):
            raise DisplayLocalizationError("display_registry_invalid")
        return data

    @staticmethod
    def _key(
        semantic_model_key: str,
        schema_identity: str,
        object_identity: str,
        locale: str,
    ) -> str:
        return "|".join(
            (semantic_model_key, schema_identity, object_identity, locale)
        )


class DisplayLocalizationService:
    """Resolve display bindings without granting canonical identity authority."""

    def __init__(
        self,
        catalog: SemanticCatalog,
        *,
        registry: JsonDisplayLocalizationRegistry | None = None,
        translator: DisplayTranslator | None = None,
    ) -> None:
        self.catalog = catalog
        self.registry = registry
        self.translator = translator
        self.schema_identity = compute_display_schema_identity(catalog)

    async def resolve_fields(
        self,
        fields: list[str],
        *,
        locale: str,
        table_hints: dict[str, str] | None = None,
    ) -> tuple[DisplayLocalization, ...]:
        objects = tuple(
            self._resolve_runtime_object(field, table_hints=table_hints)
            for field in fields
        )
        resolved: dict[str, DisplayLocalization] = {}
        unresolved: list[CatalogObject] = []
        for item in objects:
            binding = self._deterministic_binding(item, locale)
            if binding is None:
                unresolved.append(item)
            else:
                resolved[item.object_id] = binding

        if unresolved and self.translator is not None:
            candidates = tuple(
                DisplayTranslationCandidate(
                    object_identity=item.object_id,
                    object_type=item.object_type,
                    canonical_name=item.canonical_name,
                    table_name=item.table_name,
                )
                for item in unresolved
            )
            translations = await self.translator.translate(candidates, locale)
            allowed = {item.object_identity for item in candidates}
            if not isinstance(translations, dict) or any(
                key not in allowed
                or not isinstance(value, str)
                or not value.strip()
                or len(value.strip()) > 96
                for key, value in translations.items()
            ):
                raise DisplayLocalizationError("display_translation_unbounded")
            for item in unresolved:
                display_name = translations.get(item.object_id)
                if display_name is None:
                    continue
                binding = self._binding(
                    item,
                    locale,
                    display_name.strip(),
                    DisplayLocalizationSource.BOUNDED_TRANSLATION,
                )
                resolved[item.object_id] = binding
                if self.registry is not None:
                    self.registry.put(binding)

        for item in unresolved:
            if item.object_id not in resolved:
                resolved[item.object_id] = self._binding(
                    item,
                    locale,
                    _humanize(item.canonical_name),
                    DisplayLocalizationSource.FALLBACK,
                )
        return tuple(resolved[item.object_id] for item in objects)

    def binding_for_registry(
        self,
        *,
        object_identity: str,
        locale: str,
        display_name: str,
    ) -> DisplayLocalization:
        item = self.catalog.get(object_identity)
        if item is None:
            raise DisplayLocalizationError("display_object_unknown")
        return self._binding(
            item,
            locale,
            display_name.strip(),
            DisplayLocalizationSource.BOUNDED_TRANSLATION,
        )

    def _deterministic_binding(
        self,
        item: CatalogObject,
        locale: str,
    ) -> DisplayLocalization | None:
        if item.display_name and item.display_name.strip():
            return self._binding(
                item,
                locale,
                item.display_name.strip(),
                DisplayLocalizationSource.POWERBI_METADATA,
            )
        alias = _localized_alias(item, locale)
        if alias is not None:
            return self._binding(
                item,
                locale,
                alias,
                DisplayLocalizationSource.MODEL_GLOSSARY,
            )
        if self.registry is not None:
            return self.registry.get(
                semantic_model_key=self.catalog.semantic_model_key,
                schema_identity=self.schema_identity,
                object_identity=item.object_id,
                locale=locale,
            )
        return None

    def _binding(
        self,
        item: CatalogObject,
        locale: str,
        display_name: str,
        source: DisplayLocalizationSource,
    ) -> DisplayLocalization:
        if not display_name:
            raise DisplayLocalizationError("display_name_empty")
        return DisplayLocalization(
            semantic_model_key=self.catalog.semantic_model_key,
            object_identity=item.object_id,
            object_type=item.object_type,
            canonical_name=item.canonical_name,
            locale=locale,
            display_name=display_name,
            source=source,
            schema_identity=self.schema_identity,
            data_type=item.data_type,
            format_kind=PresentationFormatter.kind_for_metadata(
                item.data_type,
                item.format_string,
            ),
        )

    def _resolve_runtime_object(
        self,
        field: str,
        *,
        table_hints: dict[str, str] | None = None,
    ) -> CatalogObject:
        match = _FIELD_REFERENCE.fullmatch(field.strip())
        table_name: str | None = None
        canonical_name = field.strip()
        if match is not None:
            raw_table = match.group("table")
            if raw_table:
                table_name = raw_table.strip().strip("'")
            canonical_name = match.group("name").strip()
        if table_name is None and table_hints is not None:
            table_name = table_hints.get(canonical_name)
        matches = [
            item
            for item in self.catalog.objects
            if item.canonical_name == canonical_name
            and (table_name is None or item.table_name == table_name)
        ]
        if len(matches) != 1:
            raise DisplayLocalizationError("display_object_unknown")
        return matches[0]


def compute_display_schema_identity(catalog: SemanticCatalog) -> str:
    payload = {
        "semantic_model_key": catalog.semantic_model_key,
        "objects": [
            {
                "object_identity": item.object_id,
                "object_type": item.object_type.value,
                "canonical_name": item.canonical_name,
                "table_name": item.table_name,
                "data_type": item.data_type,
                "display_name": item.display_name,
                "format_string": item.format_string,
                "aliases": list(item.aliases),
                "source": item.source.value,
            }
            for item in sorted(catalog.objects, key=lambda value: value.object_id)
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _localized_alias(item: CatalogObject, locale: str) -> str | None:
    if item.source not in {
        SemanticObjectSource.GLOSSARY,
        SemanticObjectSource.RUNTIME_GLOSSARY,
    }:
        return None
    aliases = tuple(alias.strip() for alias in item.aliases if alias.strip())
    if locale.casefold().startswith("zh"):
        return next((alias for alias in aliases if _contains_cjk(alias)), None)
    return next((alias for alias in aliases if not _contains_cjk(alias)), None)


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def _humanize(value: str) -> str:
    normalized = value.replace("_", " ").replace("-", " ").strip()
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized or value
