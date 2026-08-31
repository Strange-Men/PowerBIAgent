"""Immutable adaptation of one validated runtime schema; no query authority."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.core.performance import measure_performance
from backend.app.schemas.data_contracts import SemanticModelSchema


class MetadataRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RuntimeObject(MetadataRecord):
    object_id: str
    canonical_name: str
    object_type: Literal["measure", "field"]
    table_name: str
    data_type: str
    description: str | None = None
    display_name: str | None = None
    format_string: str | None = None
    is_hidden: bool = False
    is_system_managed: bool = False
    is_key: bool = False
    expression: str | None = None
    sort_by_column: str | None = None
    evidence: tuple[str, ...] = ()


class RuntimeTable(MetadataRecord):
    name: str
    description: str | None = None
    display_name: str | None = None
    is_hidden: bool = False
    is_system_managed: bool = False


class RuntimeRelationship(MetadataRecord):
    name: str | None = None
    from_object_id: str
    to_object_id: str
    is_active: bool
    from_cardinality: str | None = None
    to_cardinality: str | None = None
    cross_filtering_behavior: str | None = None
    security_filtering_behavior: str | None = None
    join_on_date_behavior: str | None = None


class RuntimeHierarchy(MetadataRecord):
    name: str
    table_name: str
    levels: tuple[str, ...]
    level_object_ids: tuple[str, ...]
    description: str | None = None
    display_name: str | None = None


class TemporalEvidence(MetadataRecord):
    object_id: str
    kind: Literal["typed_date", "active_relationship_key", "month_projection"]
    date_object_id: str | None = None


class ModelSemanticContext(MetadataRecord):
    semantic_model_key: str
    runtime_identity: str
    schema_fingerprint: str
    session_generation: int | None = None
    metadata_source: Literal["adapter", "local_mcp", "mock"]
    tables: tuple[RuntimeTable, ...]
    columns: tuple[RuntimeObject, ...]
    measures: tuple[RuntimeObject, ...]
    relationships: tuple[RuntimeRelationship, ...]
    hierarchies: tuple[RuntimeHierarchy, ...]
    temporal_candidates: tuple[TemporalEvidence, ...]
    ai_instructions: None = None
    synonyms: tuple[()] = ()
    linguistic_schema: None = None
    ai_data_schema: None = None
    annotations: tuple[()] = ()


class ModelSemanticContextBuilder:
    def build(self, schema: SemanticModelSchema) -> ModelSemanticContext:
        with measure_performance("model_semantic_context_build"):
            return self._build(schema)

    def _build(self, schema: SemanticModelSchema) -> ModelSemanticContext:
        identity = schema.runtime_identity or schema.key
        if identity != schema.key:
            raise ValueError("runtime_schema_identity_mismatch")
        tables = []
        columns = []
        measures = []
        hierarchies = []
        seen_tables: set[str] = set()
        seen_objects: set[str] = set()
        for table in sorted(schema.tables, key=lambda item: item.name):
            if table.name in seen_tables:
                raise ValueError("runtime_duplicate_table_identity")
            seen_tables.add(table.name)
            if table.is_hidden or table.is_system_managed:
                continue
            tables.append(RuntimeTable(**table.model_dump(include={
                "name", "description", "display_name", "is_hidden", "is_system_managed",
            })))
            for kind, items, target in (("field", table.columns, columns), ("measure", table.measures, measures)):
                for item in sorted(items, key=lambda value: value.name):
                    if item.is_hidden or item.is_system_managed:
                        continue
                    object_id = f"{kind}:{table.name}:{item.name}"
                    if object_id in seen_objects:
                        raise ValueError("runtime_duplicate_object_identity")
                    seen_objects.add(object_id)
                    target.append(RuntimeObject(
                        object_id=object_id, canonical_name=item.name, object_type=kind,
                        table_name=table.name,
                        evidence=(schema.metadata_source,),
                        **item.model_dump(exclude={"name"}),
                    ))
            for hierarchy in sorted(table.hierarchies, key=lambda item: item.name):
                if hierarchy.is_hidden or hierarchy.is_system_managed:
                    continue
                refs = tuple(f"field:{table.name}:{name}" for name in hierarchy.level_columns)
                if refs and (len(refs) != len(hierarchy.levels) or any(ref not in seen_objects for ref in refs)):
                    continue
                hierarchies.append(RuntimeHierarchy(
                    name=hierarchy.name, table_name=table.name, levels=tuple(hierarchy.levels),
                    level_object_ids=refs, description=hierarchy.description, display_name=hierarchy.display_name,
                ))
        column_map = {item.object_id: item for item in columns}
        relationships = []
        for rel in schema.relationships:
            start = f"field:{rel.from_table}:{rel.from_column}"
            end = f"field:{rel.to_table}:{rel.to_column}"
            if start in column_map and end in column_map:
                relationships.append(RuntimeRelationship(
                    from_object_id=start, to_object_id=end,
                    **rel.model_dump(exclude={"from_table", "from_column", "to_table", "to_column"}),
                ))
        relationships.sort(key=lambda item: item.model_dump_json())
        temporal = [TemporalEvidence(object_id=item.object_id, kind="typed_date")
                    for item in columns if self._is_date(item)]
        for rel in relationships:
            target = column_map[rel.to_object_id]
            if rel.is_active and self._is_date(target) and target.is_key and (rel.to_cardinality or "").casefold() == "one":
                temporal.append(TemporalEvidence(object_id=target.object_id, kind="active_relationship_key"))
        for item in columns:
            if not self._is_date(item) or not item.expression:
                continue
            # Prove the existing calculated column is a month-start projection.
            # A display format alone cannot prove the values' grouping grain.
            expression = item.expression.strip()
            for source in columns:
                if not self._is_date(source) or source.object_id == item.object_id:
                    continue
                table_ref = source.table_name.replace("'", "''")
                column_ref = source.canonical_name.replace("]", "]]")
                refs = [f"'{table_ref}'[{column_ref}]", f"{source.table_name}[{column_ref}]"]
                if source.table_name == item.table_name:
                    refs.append(f"[{column_ref}]")
                if any(re.fullmatch(
                    r"DATE\s*\(\s*YEAR\s*\(\s*" + re.escape(ref)
                    + r"\s*\)\s*,\s*MONTH\s*\(\s*" + re.escape(ref)
                    + r"\s*\)\s*,\s*1\s*\)", expression, re.IGNORECASE,
                ) for ref in refs):
                    temporal.append(TemporalEvidence(object_id=item.object_id, kind="month_projection", date_object_id=source.object_id))
        # Fingerprint every semantic input, including hidden flags and language
        # metadata, but exclude connection/session identity and business rows.
        payload = schema.model_dump(exclude={"name", "key", "runtime_identity", "session_generation", "metadata_source"})
        payload["tables"].sort(key=lambda item: item["name"])
        for table in payload["tables"]:
            for section in ("columns", "measures", "hierarchies"):
                table[section].sort(key=lambda item: item["name"])
        payload["relationships"].sort(key=lambda item: json.dumps(item, sort_keys=True))
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ModelSemanticContext(
            semantic_model_key=schema.key, runtime_identity=identity, schema_fingerprint=fingerprint,
            session_generation=schema.session_generation, metadata_source=schema.metadata_source,
            tables=tuple(tables), columns=tuple(columns), measures=tuple(measures),
            relationships=tuple(relationships), hierarchies=tuple(hierarchies),
            temporal_candidates=tuple(sorted(set(temporal), key=lambda item: item.model_dump_json())),
        )

    @staticmethod
    def _is_date(item: RuntimeObject) -> bool:
        return "date" in item.data_type.casefold() or "time" in item.data_type.casefold()
