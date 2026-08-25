"""Model-scoped business semantic catalog.

Runtime metadata defines which objects exist.  The glossary may add stable
business terms, but it cannot add, unhide, or change the type of an object.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.data_contracts import SemanticModelSchema


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


class CatalogObject(BaseModel):
    object_id: str
    canonical_name: str
    object_type: SemanticObjectType
    table_name: str
    data_type: str
    description: str | None = None
    display_name: str | None = None
    aliases: tuple[str, ...] = ()
    member_aliases: dict[str, str] = Field(default_factory=dict)
    source: SemanticObjectSource = SemanticObjectSource.RUNTIME

    model_config = ConfigDict(frozen=True)


class SemanticCatalog(BaseModel):
    semantic_model_key: str
    schema_fingerprint: str
    schema_drift: bool = False
    objects: tuple[CatalogObject, ...]
    alias_conflicts: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    def by_type(self, object_type: SemanticObjectType) -> tuple[CatalogObject, ...]:
        return tuple(obj for obj in self.objects if obj.object_type == object_type)

    def get(self, object_id: str) -> CatalogObject | None:
        return next((obj for obj in self.objects if obj.object_id == object_id), None)

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
    """Validate glossary data against one runtime schema and merge it."""

    def __init__(self, glossary_path: Path = DEFAULT_GLOSSARY_PATH):
        self._glossary_path = Path(glossary_path)

    def build(
        self,
        schema: SemanticModelSchema,
        *,
        glossary_scope_key: str | None = None,
    ) -> SemanticCatalog:
        glossary = self._load_glossary()
        return self.build_from_data(
            schema,
            glossary,
            glossary_scope_key=glossary_scope_key,
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
                display_name = metadata.get("display_name")
                if display_name is not None and (
                    not isinstance(display_name, str) or not display_name.strip()
                ):
                    raise GlossaryCatalogError("glossary_display_name_invalid")
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
                    "display_name": (
                        unicodedata.normalize("NFKC", display_name).strip()
                        if isinstance(display_name, str)
                        else None
                    ),
                    "source": SemanticObjectSource.RUNTIME_GLOSSARY,
                })

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
        if not isinstance(raw, dict) or raw.get("version") != 1:
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
