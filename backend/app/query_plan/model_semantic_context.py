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
    is_hidden: bool | None = False
    is_system_managed: bool | None = False
    is_key: bool | None = False
    expression: str | None = None
    sort_by_column: str | None = None
    evidence: tuple[str, ...] = ()


class RuntimeTable(MetadataRecord):
    name: str
    description: str | None = None
    display_name: str | None = None
    is_hidden: bool | None = False
    is_system_managed: bool | None = False


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


class ProviderEvidence(MetadataRecord):
    """Observed declaration only; never a canonical relationship or date role."""
    kind: str
    level: Literal["AUTHORITATIVE", "LINGUISTIC_HINT", "UNKNOWN"]
    source: str
    observation: Literal["PROVIDED", "NOT_PROVIDED", "NOT_OBSERVED"]
    declarations: tuple[tuple[str, str], ...] = ()


class SemanticModelCapabilityProfile(MetadataRecord):
    """Read-only evidence inventory. No selection, planning or execution methods."""
    schema_fingerprint: str
    scalar_measures: tuple[str, ...]
    grouping_fields: tuple[str, ...]
    temporal_candidates: tuple[str, ...]
    default_temporal_authority: Literal["PROVEN", "AMBIGUOUS", "UNKNOWN"]
    relationship_evidence: Literal["CANONICAL", "ENDPOINT_DECLARATIONS_ONLY", "UNKNOWN"]
    exact_member_search: Literal["PROVEN", "UNKNOWN"]
    template_compatibility: Literal["UNKNOWN"] = "UNKNOWN"


def capability_profile(context: "ModelSemanticContext") -> SemanticModelCapabilityProfile:
    topology = {item.object_id for item in context.temporal_candidates
                if item.kind == "active_relationship_key"}
    return SemanticModelCapabilityProfile(
        schema_fingerprint=context.schema_fingerprint,
        scalar_measures=tuple(item.object_id for item in context.measures),
        grouping_fields=tuple(item.object_id for item in context.columns),
        temporal_candidates=tuple(sorted({item.object_id for item in context.temporal_candidates})),
        default_temporal_authority="PROVEN" if len(topology) == 1 else "AMBIGUOUS" if topology else "UNKNOWN",
        relationship_evidence="CANONICAL" if context.relationships else
            "ENDPOINT_DECLARATIONS_ONLY" if any(e.kind == "relationship_endpoints" for e in context.provider_evidence) else "UNKNOWN",
        exact_member_search="PROVEN" if any(e.kind == "exact_member_search" and e.level == "AUTHORITATIVE"
            for e in context.provider_evidence) else "UNKNOWN")


class ModelSemanticContext(MetadataRecord):
    semantic_model_key: str
    runtime_identity: str
    resource_identity: str | None = None
    schema_fingerprint: str
    session_generation: int | None = None
    metadata_source: Literal["adapter", "local_mcp", "mock", "fabric_iq"]
    tables: tuple[RuntimeTable, ...]
    columns: tuple[RuntimeObject, ...]
    measures: tuple[RuntimeObject, ...]
    relationships: tuple[RuntimeRelationship, ...]
    hierarchies: tuple[RuntimeHierarchy, ...]
    temporal_candidates: tuple[TemporalEvidence, ...]
    provider_evidence: tuple[ProviderEvidence, ...] = ()
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
            if not rel.is_active or (rel.to_cardinality or "").casefold() != "one":
                continue
            if self._is_date(target) and target.is_key:
                temporal.append(TemporalEvidence(object_id=target.object_id, kind="active_relationship_key"))
                continue
            # Some date dimensions relate facts through an integer surrogate key.
            # The active many-to-one relationship still proves the date table, but
            # only a unique key-typed date column in that table can prove the
            # canonical date role.  Multiple or absent candidates remain unresolved.
            relationship_date_keys = tuple(
                item for item in columns
                if item.table_name == target.table_name and item.is_key and self._is_date(item)
            )
            if len(relationship_date_keys) == 1:
                temporal.append(TemporalEvidence(
                    object_id=relationship_date_keys[0].object_id,
                    kind="active_relationship_key",
                ))
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
            resource_identity=self._resource_identity(schema),
            provider_evidence=self._provider_evidence(schema),
            session_generation=schema.session_generation, metadata_source=schema.metadata_source,
            tables=tuple(tables), columns=tuple(columns), measures=tuple(measures),
            relationships=tuple(relationships), hierarchies=tuple(hierarchies),
            temporal_candidates=tuple(sorted(set(temporal), key=lambda item: item.model_dump_json())),
        )

    @staticmethod
    def _provider_evidence(schema: SemanticModelSchema) -> tuple[ProviderEvidence, ...]:
        metadata = schema.provider_metadata
        result = []
        for relation in metadata.get("active_relationships", []):
            result.append(ProviderEvidence(kind="relationship_endpoints",level="AUTHORITATIVE",
                source=schema.metadata_source + ":ActiveRelationships",observation="PROVIDED",
                declarations=tuple((key,str(relation[key])) for key in ("PK","FK") if key in relation)))
            if relation.get("UnidirectionalFilter"):
                result.append(ProviderEvidence(kind="relationship_direction_text",level="LINGUISTIC_HINT",
                    source=schema.metadata_source + ":ActiveRelationships",observation="PROVIDED",
                    declarations=(("text",relation["UnidirectionalFilter"]),)))
        for name, observation in metadata.get("metadata_observations", {}).items():
            result.append(ProviderEvidence(kind=name,level="LINGUISTIC_HINT" if observation == "PROVIDED" else "UNKNOWN",
                source=schema.metadata_source + ":schema",observation=observation))
        if metadata.get("exact_member_search") is True:
            result.append(ProviderEvidence(kind="exact_member_search",level="AUTHORITATIVE",
                source=schema.metadata_source + ":tools/list",observation="PROVIDED"))
        for hierarchy in metadata.get("hierarchy_declarations", []):
            result.append(ProviderEvidence(kind="hierarchy_declaration",level="LINGUISTIC_HINT",
                source=schema.metadata_source + ":schema",observation="PROVIDED",
                declarations=(("table",hierarchy["table"]),
                    ("declaration",json.dumps(hierarchy["declarations"],ensure_ascii=False,sort_keys=True)))))
        if metadata.get("report_model_evidence"):
            result.append(ProviderEvidence(kind="report_model_binding",level="AUTHORITATIVE",
                source=schema.metadata_source + ":GetReportMetadata+Resolve",observation="PROVIDED",
                declarations=tuple(sorted(metadata["report_model_evidence"].items()))))
        return tuple(result)

    @staticmethod
    def _resource_identity(schema: SemanticModelSchema) -> str | None:
        resource = schema.provider_metadata.get("resource_identity")
        if schema.metadata_source != "fabric_iq" or not isinstance(resource, dict):
            return None
        from uuid import UUID
        workspace, model = resource.get("workspace_id"), resource.get("model_id")
        if any(not isinstance(value, str) or str(UUID(value)) != value for value in (workspace, model)):
            raise ValueError("runtime_resource_identity_invalid")
        return f"fabric_iq:{workspace}:{model}"

    @staticmethod
    def _is_date(item: RuntimeObject) -> bool:
        return "date" in item.data_type.casefold() or "time" in item.data_type.casefold()
