"""Model-scoped business semantic catalog.

Runtime metadata defines which objects exist.  The glossary may add stable
business terms, but it cannot add, unhide, or change the type of an object.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.data_contracts import SemanticModelSchema
from backend.app.query_plan.model_semantic_context import ModelSemanticContext, ModelSemanticContextBuilder


DEFAULT_GLOSSARY_PATH = Path(__file__).with_name("business_glossary.yaml")


def normalize_semantic_text(value: str) -> str:
    """Apply only language-agnostic identity normalization."""

    return unicodedata.normalize("NFKC", value).strip().casefold()


class SemanticObjectType(str, Enum):
    MEASURE = "measure"
    FIELD = "field"


class SemanticObjectSource(str, Enum):
    RUNTIME = "runtime"
    GLOSSARY = "glossary"
    RUNTIME_GLOSSARY = "runtime+glossary"


class TemporalGroupingBinding(BaseModel):
    """Model-scoped binding from a grouping grain to runtime-owned fields."""

    grain: Literal["month", "year"]
    date_field: str
    date_table_name: str

    model_config = ConfigDict(frozen=True)


class CatalogObject(BaseModel):
    object_id: str
    canonical_name: str
    object_type: SemanticObjectType
    table_name: str
    data_type: str
    description: str | None = None
    display_name: str | None = None
    format_string: str | None = None
    aliases: tuple[str, ...] = ()
    member_aliases: dict[str, str] = Field(default_factory=dict)
    member_suffixes: tuple[str, ...] = ()
    temporal_role: Literal["default"] | None = None
    temporal_grouping: TemporalGroupingBinding | None = None
    source: SemanticObjectSource = SemanticObjectSource.RUNTIME

    model_config = ConfigDict(frozen=True)

    @property
    def language_terms(self) -> tuple[str, ...]:
        return tuple(term for term in (
            self.canonical_name, f"{self.table_name}[{self.canonical_name}]",
            f"'{self.table_name}'[{self.canonical_name}]",
            self.display_name, self.description, *self.aliases,
        ) if term)


class SemanticCatalog(BaseModel):
    semantic_model_key: str
    schema_fingerprint: str
    schema_drift: bool = False
    objects: tuple[CatalogObject, ...]
    alias_conflicts: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    context: ModelSemanticContext | None = None

    model_config = ConfigDict(frozen=True)

    def by_type(self, object_type: SemanticObjectType) -> tuple[CatalogObject, ...]:
        return tuple(obj for obj in self.objects if obj.object_type == object_type)

    def get(self, object_id: str) -> CatalogObject | None:
        return next((obj for obj in self.objects if obj.object_id == object_id), None)

    def selection_candidates(
        self, object_type: SemanticObjectType, role: str,
    ) -> tuple[CatalogObject, ...]:
        """Role eligibility is structural; language overlap is not eligibility."""
        candidates = self.by_type(object_type)
        if role == "date_field":
            candidates = tuple(obj for obj in candidates if (
                "date" in obj.data_type.casefold() or "time" in obj.data_type.casefold()
            ) and obj.temporal_grouping is None)
        elif object_type == SemanticObjectType.FIELD and role in {
            "dimension", "ranking_dimension", "filter_field",
        }:
            candidates = self._without_shadowed_technical_keys(candidates)
        return tuple(sorted(candidates, key=lambda obj: obj.object_id))

    @classmethod
    def _without_shadowed_technical_keys(
        cls, candidates: tuple[CatalogObject, ...],
    ) -> tuple[CatalogObject, ...]:
        """Keep IDs selectable only when runtime metadata has no unique label peer."""
        result = []
        for item in candidates:
            stem, suffix = cls._entity_field_parts(item.canonical_name)
            if suffix not in {"id", "key", "code"}:
                result.append(item)
                continue
            label_peers = [
                candidate for candidate in candidates
                if candidate.table_name == item.table_name
                and candidate.object_id != item.object_id
                and cls._entity_field_parts(candidate.canonical_name)[0] == stem
                and cls._entity_field_parts(candidate.canonical_name)[1]
                in {"", "name", "label", "title", "description"}
            ]
            if len(label_peers) != 1:
                result.append(item)
        return tuple(result)

    @staticmethod
    def _entity_field_parts(name: str) -> tuple[str, str]:
        normalized = re.sub(r"[^0-9a-z]+", "", name.casefold())
        for suffix in ("description", "title", "label", "name", "code", "key", "id"):
            if normalized.endswith(suffix) and len(normalized) > len(suffix):
                return normalized[:-len(suffix)], suffix
        return normalized, ""

    def selection_evidence(self, candidates: tuple[CatalogObject, ...]) -> dict[str, Any]:
        """A bounded selector view of this catalog, never another semantic model.

        No members, display registry or previous model data enter the view.
        Existing measure definitions are evidence, never executable LLM output.
        """
        context = self.context
        tables = {table.name: table for table in context.tables} if context else {}
        measures = {item.object_id: item for item in context.measures} if context else {}
        records = []
        for obj in candidates:
            table = tables.get(obj.table_name)
            record = obj.model_dump(mode="json", include={
                "object_id", "canonical_name", "object_type", "table_name", "data_type",
                "description", "display_name", "format_string", "aliases", "temporal_role",
            })
            if table:
                record["table_context"] = table.model_dump(mode="json", include={"name", "description", "display_name"})
            if obj.object_id in measures:
                record["runtime_definition"] = measures[obj.object_id].expression
            if context:
                record["relationship_roles"] = [{
                    "is_active": rel.is_active, "cardinality": cardinality,
                    "related_object_id": related_id, "related_cardinality": related_cardinality,
                } for rel in context.relationships
                    for endpoint, cardinality, related_id, related_cardinality in (
                        (rel.from_object_id, rel.from_cardinality, rel.to_object_id, rel.to_cardinality),
                        (rel.to_object_id, rel.to_cardinality, rel.from_object_id, rel.from_cardinality),
                    ) if endpoint == obj.object_id]
                record["relationships"] = [rel.model_dump(mode="json") for rel in context.relationships
                    if any(endpoint.startswith(f"field:{obj.table_name}:") for endpoint in (rel.from_object_id, rel.to_object_id))]
                record["hierarchies"] = [hierarchy.model_dump(mode="json") for hierarchy in context.hierarchies
                    if obj.object_id in hierarchy.level_object_ids]
                record["temporal_evidence"] = [entry.model_dump(mode="json") for entry in context.temporal_candidates
                    if obj.object_id == entry.object_id]
            records.append(record)
        return {
            "semantic_model_key": self.semantic_model_key,
            "schema_fingerprint": self.schema_fingerprint,
            "session_generation": context.session_generation if context else None,
            "candidates": records,
            # Existing expression operands give measurement units/type context,
            # but these fields are not selectable measure candidates.
            "definition_fields": [field.model_dump(mode="json", include={
                "object_id", "canonical_name", "table_name", "data_type", "description", "format_string",
            }) for field in context.columns if any(obj.object_type == SemanticObjectType.MEASURE
                and obj.table_name == field.table_name for obj in candidates)] if context else [],
        }

    def field_owners(self, canonical_name: str) -> tuple[str, ...]:
        return tuple(
            obj.table_name
            for obj in self.by_type(SemanticObjectType.FIELD)
            if obj.canonical_name == canonical_name
        )

    @property
    def alias_count(self) -> int:
        return sum(len(obj.aliases) for obj in self.objects)


class GlossaryCatalogError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SemanticCatalogBuilder:
    """Adapt runtime-owned candidates and an optional exact-model override."""

    def __init__(self, glossary_path: Path | str | None = None):
        self._glossary_path = Path(glossary_path) if glossary_path is not None else DEFAULT_GLOSSARY_PATH

    def build(
        self,
        schema: SemanticModelSchema,
        *,
        glossary_scope_key: str | None = None,
    ) -> SemanticCatalog:
        # Friendly scope cannot authorize another Desktop's business bindings.
        try:
            context = ModelSemanticContextBuilder().build(schema)
        except ValueError as exc:
            raise GlossaryCatalogError("runtime_semantic_context_invalid") from exc
        from backend.app.query_plan.model_override import resolve_model_override

        override = resolve_model_override(context, self._load_glossary())
        return self.build_from_context(context, override)

    def build_from_context(
        self, context: ModelSemanticContext, override: dict[str, Any] | None = None,
    ) -> SemanticCatalog:
        """Runtime-owned candidates plus an explicitly bound language layer."""
        from backend.app.query_plan.model_override import apply_model_override

        objects = {
            item.object_id: CatalogObject(**item.model_dump(include={
                "object_id", "canonical_name", "object_type", "table_name", "data_type",
                "description", "display_name", "format_string",
            }))
            for item in (*context.measures, *context.columns)
        }
        month_sources: dict[str, set[str]] = {}
        for evidence in context.temporal_candidates:
            if evidence.kind == "month_projection" and evidence.date_object_id:
                month_sources.setdefault(evidence.object_id, set()).add(evidence.date_object_id)
        for evidence in context.temporal_candidates:
            if evidence.kind != "month_projection":
                continue
            if len(month_sources.get(evidence.object_id, ())) != 1:
                # Multiple metadata proofs are ambiguity, never list-order authority.
                continue
            item = objects[evidence.object_id]
            target = objects.get(evidence.date_object_id or "")
            if target is not None:
                objects[item.object_id] = item.model_copy(update={"temporal_grouping": TemporalGroupingBinding(
                    grain="month", date_field=target.canonical_name, date_table_name=target.table_name,
                )})
        if override is not None:
            objects = apply_model_override(context, objects, override)
        alias_targets: dict[str, set[str]] = {}
        for item in objects.values():
            for alias in item.aliases:
                alias_targets.setdefault(normalize_semantic_text(alias), set()).add(item.object_id)
        return SemanticCatalog(
            semantic_model_key=context.semantic_model_key, schema_fingerprint=context.schema_fingerprint,
            objects=tuple(sorted(objects.values(), key=lambda item: item.object_id)), context=context,
            alias_conflicts={alias: tuple(sorted(ids)) for alias, ids in alias_targets.items() if len(ids) > 1},
        )

    def build_from_data(
        self,
        schema: SemanticModelSchema,
        glossary: dict[str, Any],
        *,
        glossary_scope_key: str | None = None,
    ) -> SemanticCatalog:
        """Validate supplied glossary data; used by focused offline tests."""
        if glossary.get("version") != 1:
            raise GlossaryCatalogError("glossary_version_invalid")
        effective_scope_key = glossary_scope_key or schema.key
        if glossary.get("semantic_model_key") != effective_scope_key:
            raise GlossaryCatalogError("glossary_semantic_model_key_mismatch")
        expected_fingerprint = glossary.get("schema_fingerprint")
        if not isinstance(expected_fingerprint, str) or len(expected_fingerprint) != 64:
            raise GlossaryCatalogError("glossary_schema_fingerprint_invalid")
        runtime_fingerprint = compute_schema_fingerprint(schema)
        schema_drift = expected_fingerprint != runtime_fingerprint

        objects: dict[tuple[SemanticObjectType, str, str], CatalogObject] = {}
        hidden: set[tuple[SemanticObjectType, str, str]] = set()
        all_table_names = {table.name for table in schema.tables}
        hidden_table_names = {
            table.name
            for table in schema.tables
            if table.is_hidden or table.is_system_managed
        }
        for table in schema.tables:
            table_hidden = table.is_hidden or table.is_system_managed
            for measure in table.measures:
                key = (SemanticObjectType.MEASURE, table.name, measure.name)
                if table_hidden or measure.is_hidden:
                    hidden.add(key)
                    continue
                objects[key] = CatalogObject(
                    object_id=self._object_id(*key),
                    canonical_name=measure.name,
                    object_type=SemanticObjectType.MEASURE,
                    table_name=table.name,
                    data_type=measure.data_type,
                    description=measure.description,
                    display_name=measure.display_name,
                    format_string=measure.format_string,
                )
            for column in table.columns:
                key = (SemanticObjectType.FIELD, table.name, column.name)
                if table_hidden or column.is_hidden:
                    hidden.add(key)
                    continue
                objects[key] = CatalogObject(
                    object_id=self._object_id(*key),
                    canonical_name=column.name,
                    object_type=SemanticObjectType.FIELD,
                    table_name=table.name,
                    data_type=column.data_type,
                    description=column.description,
                    display_name=column.display_name,
                    format_string=column.format_string,
                )

        alias_targets: dict[str, set[str]] = {}
        for section, object_type in (
            ("measures", SemanticObjectType.MEASURE),
            ("fields", SemanticObjectType.FIELD),
        ):
            entries = glossary.get(section, {})
            if not isinstance(entries, dict):
                raise GlossaryCatalogError("glossary_section_invalid")
            for canonical_ref, metadata in entries.items():
                if not isinstance(metadata, dict):
                    raise GlossaryCatalogError("glossary_object_invalid")
                required = metadata.get("required", True)
                if not isinstance(required, bool):
                    raise GlossaryCatalogError("glossary_required_flag_invalid")
                table_name, canonical_name = self._parse_reference(
                    canonical_ref, metadata, object_type
                )
                aliases = metadata.get("aliases", [])
                if not isinstance(aliases, list) or any(
                    not isinstance(alias, str) or not alias.strip() for alias in aliases
                ):
                    raise GlossaryCatalogError("glossary_alias_invalid")
                raw_member_aliases = metadata.get("member_aliases", {})
                if not isinstance(raw_member_aliases, dict) or any(
                    not isinstance(alias, str)
                    or not alias.strip()
                    or not isinstance(target, str)
                    or not target.strip()
                    for alias, target in raw_member_aliases.items()
                ):
                    raise GlossaryCatalogError("glossary_member_alias_invalid")
                member_aliases: dict[str, str] = {}
                for alias, target in raw_member_aliases.items():
                    normalized_alias = normalize_semantic_text(alias)
                    clean_target = unicodedata.normalize("NFKC", target).strip()
                    previous_target = member_aliases.get(normalized_alias)
                    if previous_target is not None and previous_target != clean_target:
                        raise GlossaryCatalogError("glossary_member_alias_conflict")
                    member_aliases[normalized_alias] = clean_target
                raw_member_suffixes = metadata.get("member_suffixes", [])
                if not isinstance(raw_member_suffixes, list) or any(
                    not isinstance(suffix, str) or not suffix.strip()
                    for suffix in raw_member_suffixes
                ):
                    raise GlossaryCatalogError("glossary_member_suffix_invalid")
                if raw_member_suffixes and object_type != SemanticObjectType.FIELD:
                    raise GlossaryCatalogError("glossary_member_suffix_object_invalid")
                member_suffixes = tuple(dict.fromkeys(
                    unicodedata.normalize("NFKC", suffix).strip()
                    for suffix in raw_member_suffixes
                ))
                if table_name not in all_table_names:
                    if not required:
                        continue
                    raise GlossaryCatalogError("glossary_table_missing")
                key = (object_type, table_name, canonical_name)
                if table_name in hidden_table_names or key in hidden:
                    if not required:
                        continue
                    raise GlossaryCatalogError("glossary_hidden_object")
                runtime_object = objects.get(key)
                if runtime_object is None:
                    opposite_type = (
                        SemanticObjectType.FIELD
                        if object_type == SemanticObjectType.MEASURE
                        else SemanticObjectType.MEASURE
                    )
                    opposite_key = (opposite_type, table_name, canonical_name)
                    if opposite_key in objects or opposite_key in hidden:
                        raise GlossaryCatalogError("glossary_object_type_mismatch")
                    if not required:
                        continue
                    raise GlossaryCatalogError("glossary_unknown_object")
                raw_temporal = metadata.get("temporal_grouping")
                temporal_grouping: TemporalGroupingBinding | None = None
                if raw_temporal is not None:
                    if object_type != SemanticObjectType.FIELD:
                        raise GlossaryCatalogError(
                            "glossary_temporal_grouping_object_invalid"
                        )
                    try:
                        temporal_grouping = TemporalGroupingBinding.model_validate(
                            raw_temporal
                        )
                    except (TypeError, ValueError) as exc:
                        raise GlossaryCatalogError(
                            "glossary_temporal_grouping_invalid"
                        ) from exc
                    date_key = (
                        SemanticObjectType.FIELD,
                        temporal_grouping.date_table_name,
                        temporal_grouping.date_field,
                    )
                    date_object = objects.get(date_key)
                    if date_object is None:
                        raise GlossaryCatalogError(
                            "glossary_temporal_grouping_date_field_missing"
                        )
                    date_type = date_object.data_type.casefold()
                    if "date" not in date_type and "time" not in date_type:
                        raise GlossaryCatalogError(
                            "glossary_temporal_grouping_date_field_invalid"
                        )
                raw_temporal_role = metadata.get("temporal_role")
                temporal_role: Literal["default"] | None = None
                if raw_temporal_role is not None:
                    if object_type != SemanticObjectType.FIELD:
                        raise GlossaryCatalogError(
                            "glossary_temporal_role_object_invalid"
                        )
                    if raw_temporal_role != "default":
                        raise GlossaryCatalogError(
                            "glossary_temporal_role_invalid"
                        )
                    runtime_type = runtime_object.data_type.casefold()
                    if "date" not in runtime_type and "time" not in runtime_type:
                        raise GlossaryCatalogError(
                            "glossary_temporal_role_type_invalid"
                        )
                    temporal_role = "default"
                normalized_seen: set[str] = set()
                clean_aliases: list[str] = []
                for alias in aliases:
                    clean = unicodedata.normalize("NFKC", alias).strip()
                    normalized = normalize_semantic_text(clean)
                    if normalized in normalized_seen:
                        continue
                    normalized_seen.add(normalized)
                    clean_aliases.append(clean)
                    alias_targets.setdefault(normalized, set()).add(
                        runtime_object.object_id
                    )
                objects[key] = runtime_object.model_copy(update={
                    "aliases": tuple(clean_aliases),
                    "member_aliases": member_aliases,
                    "member_suffixes": member_suffixes,
                    "temporal_role": temporal_role,
                    "temporal_grouping": temporal_grouping,
                    "source": SemanticObjectSource.RUNTIME_GLOSSARY,
                })

        default_temporal_roles = [
            obj for obj in objects.values() if obj.temporal_role == "default"
        ]
        if len(default_temporal_roles) > 1:
            raise GlossaryCatalogError("glossary_default_temporal_role_conflict")

        conflicts = {
            alias: tuple(sorted(targets))
            for alias, targets in alias_targets.items()
            if len(targets) > 1
        }
        return SemanticCatalog(
            semantic_model_key=schema.key,
            schema_fingerprint=runtime_fingerprint,
            schema_drift=schema_drift,
            objects=tuple(objects.values()),
            alias_conflicts=conflicts,
        )

    def _load_glossary(self) -> dict[str, Any]:
        try:
            raw = yaml.safe_load(self._glossary_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise GlossaryCatalogError("glossary_load_failed") from exc
        if not isinstance(raw, dict) or raw.get("version") != 2:
            raise GlossaryCatalogError("glossary_version_invalid")
        return raw

    @staticmethod
    def _parse_reference(
        canonical_ref: Any,
        metadata: dict[str, Any],
        expected_type: SemanticObjectType,
    ) -> tuple[str, str]:
        if not isinstance(canonical_ref, str) or not canonical_ref.strip():
            raise GlossaryCatalogError("glossary_canonical_name_invalid")
        table_name = metadata.get("table_name")
        if not isinstance(table_name, str) or not table_name.strip():
            raise GlossaryCatalogError("glossary_table_name_missing")
        declared_type = metadata.get("object_type")
        if declared_type is not None and declared_type != expected_type.value:
            raise GlossaryCatalogError("glossary_object_type_invalid")
        return table_name.strip(), canonical_ref.strip()

    @staticmethod
    def _object_id(
        object_type: SemanticObjectType, table_name: str, canonical_name: str
    ) -> str:
        return f"{object_type.value}:{table_name}:{canonical_name}"


def compute_schema_fingerprint(schema: SemanticModelSchema) -> str:
    """Return a stable identity hash for authoritative visible model metadata.

    Descriptions are intentionally excluded: they are useful language metadata,
    but display-only edits must not detach a glossary from an otherwise identical
    runtime model. Runtime connection/session details and business rows never
    enter the serialization.
    """

    visible_tables = {
        table.name: table
        for table in schema.tables
        if not table.is_hidden and not table.is_system_managed
    }
    visible_columns = {
        (table.name, column.name)
        for table in visible_tables.values()
        for column in table.columns
        if not column.is_hidden
    }
    payload = {
        "tables": [
            {
                "name": table.name,
                "columns": sorted(
                    (
                        {"name": column.name, "data_type": column.data_type}
                        for column in table.columns
                        if not column.is_hidden
                    ),
                    key=lambda item: (item["name"], item["data_type"]),
                ),
                "measures": sorted(
                    (
                        {
                            "name": measure.name,
                            "data_type": measure.data_type,
                            "expression": measure.expression,
                        }
                        for measure in table.measures
                        if not measure.is_hidden
                    ),
                    key=lambda item: (
                        item["name"], item["data_type"], item["expression"]
                    ),
                ),
            }
            for table in sorted(visible_tables.values(), key=lambda item: item.name)
        ],
        "active_relationships": sorted(
            (
                {
                    "from_table": relationship.from_table,
                    "from_column": relationship.from_column,
                    "to_table": relationship.to_table,
                    "to_column": relationship.to_column,
                }
                for relationship in schema.relationships
                if relationship.is_active
                and (relationship.from_table, relationship.from_column)
                in visible_columns
                and (relationship.to_table, relationship.to_column) in visible_columns
            ),
            key=lambda item: (
                item["from_table"], item["from_column"],
                item["to_table"], item["to_column"],
            ),
        ),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
