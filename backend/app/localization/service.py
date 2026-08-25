"""Resolve safe display labels for exact runtime semantic objects."""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from backend.app.llm.base import LLMProvider, LLMRequest, LLMTask
from backend.app.localization.models import (
    LocalizationRecord,
    LocalizationSource,
    ResolvedLocalization,
)
from backend.app.localization.registry import (
    LocalizationRegistry,
    LocalizationRegistryError,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
)
from backend.app.schemas.data_contracts import CanonicalQueryPlan, SemanticModelSchema


class DisplayTranslationItem(BaseModel):
    object_identity: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class DisplayTranslationBatch(BaseModel):
    translations: list[DisplayTranslationItem] = Field(default_factory=list, max_length=20)

    model_config = ConfigDict(extra="forbid")


class LocalizationService:
    """Priority: metadata → glossary → registry → bounded translation → fallback."""

    def __init__(
        self,
        registry: LocalizationRegistry,
        *,
        locale: str = "zh-CN",
        minimum_translation_confidence: float = 0.75,
    ):
        self._registry = registry
        self._locale = locale
        self._minimum_translation_confidence = minimum_translation_confidence

    async def resolve_for_plan(
        self,
        *,
        schema: SemanticModelSchema,
        catalog: SemanticCatalog,
        plan: CanonicalQueryPlan,
        translator: LLMProvider | None,
    ) -> dict[str, ResolvedLocalization]:
        objects = self._exact_plan_objects(catalog, plan)
        resolved: dict[str, ResolvedLocalization] = {}
        pending_translation: list[CatalogObject] = []

        for item in objects:
            metadata = self._schema_metadata(schema, item)
            display_name = metadata.get("display_name")
            if isinstance(display_name, str) and display_name.strip():
                resolved[item.object_id] = self._resolved(
                    catalog, item, display_name.strip(),
                    LocalizationSource.MODEL_METADATA, metadata,
                )
                continue
            if item.display_name:
                resolved[item.object_id] = self._resolved(
                    catalog, item, item.display_name,
                    LocalizationSource.GLOSSARY, metadata,
                )
                continue
            try:
                cached = self._registry.get(
                    semantic_model_key=catalog.semantic_model_key,
                    object_identity=item.object_id,
                    object_type=item.object_type.value,
                    canonical_name=item.canonical_name,
                    locale=self._locale,
                    schema_identity=catalog.schema_fingerprint,
                )
            except LocalizationRegistryError:
                cached = None
            if cached is not None:
                resolved[item.object_id] = self._resolved(
                    catalog, item, cached.display_name,
                    LocalizationSource.REGISTRY, metadata,
                )
                continue
            pending_translation.append(item)

        translations = await self._translate(
            pending_translation, translator, catalog.schema_fingerprint
        )
        for item in pending_translation:
            metadata = self._schema_metadata(schema, item)
            translated = translations.get(item.object_id)
            if translated is not None:
                display_name, confidence = translated
                if confidence >= self._minimum_translation_confidence:
                    record = LocalizationRecord(
                        semantic_model_key=catalog.semantic_model_key,
                        object_identity=item.object_id,
                        object_type=item.object_type.value,
                        canonical_name=item.canonical_name,
                        locale=self._locale,
                        display_name=display_name,
                        source=LocalizationSource.LLM_TRANSLATION,
                        schema_identity=catalog.schema_fingerprint,
                    )
                    try:
                        self._registry.put(record)
                    except (LocalizationRegistryError, OSError):
                        pass
                    resolved[item.object_id] = self._resolved(
                        catalog, item, display_name,
                        LocalizationSource.LLM_TRANSLATION, metadata,
                    )
                    continue
            fallback = self._humanize(item.canonical_name)
            source = (
                LocalizationSource.HUMANIZED_FALLBACK
                if fallback != item.canonical_name
                else LocalizationSource.CANONICAL_FALLBACK
            )
            resolved[item.object_id] = self._resolved(
                catalog, item, fallback, source, metadata,
            )

        aliases: dict[str, ResolvedLocalization] = {}
        for item in resolved.values():
            for alias in item.result_field_aliases():
                aliases[alias] = item
        return aliases

    @staticmethod
    def _exact_plan_objects(
        catalog: SemanticCatalog, plan: CanonicalQueryPlan
    ) -> tuple[CatalogObject, ...]:
        selected: list[CatalogObject] = []
        for measure in plan.measures:
            matches = tuple(
                item for item in catalog.by_type(SemanticObjectType.MEASURE)
                if item.canonical_name == measure
            )
            if len(matches) == 1:
                selected.append(matches[0])
        for field in plan.dimensions:
            owner = (plan.dimension_tables or {}).get(field)
            matches = tuple(
                item for item in catalog.by_type(SemanticObjectType.FIELD)
                if item.canonical_name == field
                and (owner is None or item.table_name == owner)
            )
            if len(matches) == 1:
                selected.append(matches[0])
        unique = {item.object_id: item for item in selected}
        return tuple(unique.values())

    @staticmethod
    def _schema_metadata(
        schema: SemanticModelSchema, item: CatalogObject
    ) -> dict[str, str | None]:
        table = next((table for table in schema.tables if table.name == item.table_name), None)
        if table is None:
            return {}
        collection = table.measures if item.object_type == SemanticObjectType.MEASURE else table.columns
        runtime = next((obj for obj in collection if obj.name == item.canonical_name), None)
        if runtime is None:
            return {}
        return {
            "display_name": runtime.display_name,
            "data_type": runtime.data_type,
            "format_string": runtime.format_string,
        }

    def _resolved(
        self,
        catalog: SemanticCatalog,
        item: CatalogObject,
        display_name: str,
        source: LocalizationSource,
        metadata: dict[str, str | None],
    ) -> ResolvedLocalization:
        return ResolvedLocalization(
            semantic_model_key=catalog.semantic_model_key,
            object_identity=item.object_id,
            object_type=item.object_type.value,
            canonical_name=item.canonical_name,
            locale=self._locale,
            display_name=display_name,
            source=source,
            schema_identity=catalog.schema_fingerprint,
            table_name=item.table_name,
            data_type=str(metadata.get("data_type") or item.data_type),
            format_string=metadata.get("format_string"),
        )

    async def _translate(
        self,
        objects: Iterable[CatalogObject],
        translator: LLMProvider | None,
        schema_identity: str,
    ) -> dict[str, tuple[str, float]]:
        pending = tuple(objects)
        if not pending or translator is None or translator.is_mock:
            return {}
        candidates = [
            {
                "object_identity": item.object_id,
                "canonical_name": item.canonical_name,
                "object_type": item.object_type.value,
                "description": item.description or "",
            }
            for item in pending
        ]
        request = LLMRequest(
            task=LLMTask.DISPLAY_TRANSLATION,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Translate only display labels for the supplied existing semantic "
                        "objects into concise zh-CN. Return only registered object_identity "
                        "values with display_name and confidence. Do not create objects, "
                        "facts, DAX, values, or explanations."
                    ),
                },
                {
                    "role": "user",
                    "content": f"schema_identity={schema_identity}; objects={candidates!r}",
                },
            ],
            metadata={"candidate_count": len(candidates)},
        )
        try:
            response = await translator.generate(request, DisplayTranslationBatch)
        except Exception:
            return {}
        if response.structured is None:
            return {}
        allowed = {item.object_id for item in pending}
        output: dict[str, tuple[str, float]] = {}
        for item in response.structured.translations:
            display_name = self._safe_display_name(item.display_name)
            if item.object_identity in allowed and display_name is not None:
                output[item.object_identity] = (display_name, item.confidence)
        return output

    @staticmethod
    def _safe_display_name(value: str) -> str | None:
        cleaned = value.strip()
        if (
            not cleaned
            or len(cleaned) > 40
            or any(char in cleaned for char in "\r\n\t<>[]{}")
        ):
            return None
        return cleaned

    @staticmethod
    def _humanize(value: str) -> str:
        normalized = re.sub(r"[_\-]+", " ", value).strip()
        normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", normalized)
        return re.sub(r"\s+", " ", normalized) or value
