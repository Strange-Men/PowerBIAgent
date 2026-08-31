"""Readonly runtime metadata capability/isolation audit; no secrets or rows."""

from __future__ import annotations

import asyncio
import argparse
import json
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.acceptance_tempdir import owned_acceptance_tempdir

from backend.app.application.semantic_model_discovery_service import SemanticModelDiscoveryService
from backend.app.config.settings import Settings, PowerBIMode
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
from backend.app.harness.tool_registry import SchemaInput, create_default_tool_gateway
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.persistence.artifact_ownership import ArtifactOwnershipRegistry
from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.query_plan.model_override import resolve_model_override
from backend.app.query_plan.grounding import GroundingStatus, MemberGrounder, ObjectGrounder, SemanticGroundingService
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder, SemanticObjectType
from backend.app.schemas.data_contracts import ColumnMembersRequest, UserContext


class MetadataAuditAdapter(LocalMCPPowerBIAdapter):
    field_presence: dict[str, list[str]] = {}

    @classmethod
    def _map_schema(cls, snapshot, semantic_model_key):
        # Record property names only; never runtime object names/values.
        for section in ("tables", "columns", "measures", "relationships", "hierarchies"):
            cls.field_presence[section] = sorted(set(cls.field_presence.get(section, [])) | {
                key for record in getattr(snapshot, section) for key in record
            })
        cls.field_presence["hierarchy_levels"] = sorted(set(cls.field_presence.get("hierarchy_levels", [])) | {
            key for record in snapshot.hierarchies for level in record.get("levels", []) for key in level
        })
        return super()._map_schema(snapshot, semantic_model_key)


async def read_members(gateway, execution, context, catalog):
    """Inspect every visible text field, without selecting a business meaning."""
    snapshots = {}
    verified = 0
    for column in context.columns:
        if column.data_type.casefold() not in {"string", "text"}:
            continue
        members = await gateway.execute("get_column_members", execution, ColumnMembersRequest(
            semantic_model_key=context.semantic_model_key, table_name=column.table_name,
            field_name=column.canonical_name, limit=200,
        ))
        assert (members.semantic_model_key, members.table_name, members.field_name, members.source_mode) == (
            context.semantic_model_key, column.table_name, column.canonical_name, "real",
        )
        field = catalog.get(column.object_id)
        for value in members.values:
            if isinstance(value, str):
                outcome = MemberGrounder.resolve(field, value, members)
                assert outcome.status == GroundingStatus.RESOLVED
                assert outcome.canonical_value == value
                verified += 1
        unknown = "absent-member-" + uuid.uuid4().hex
        assert unknown not in members.values
        assert MemberGrounder.resolve(field, unknown, members).status == GroundingStatus.UNRESOLVED
        # Keep values only in this process, never in logs or committed artifacts.
        snapshots[column.object_id] = members
    return snapshots, verified


def audit_overrides(saved):
    """One-object transient language supplements; no production config writes."""
    checked = 0
    for key, (context, _, _, _) in saved.items():
        for obj in context.measures:
            alias = "language-" + uuid.uuid4().hex
            registry = {"version": 2, "overrides": [{
                "semantic_model_key": key, "runtime_identity": context.runtime_identity,
                "schema_fingerprint": context.schema_fingerprint,
                "objects": {obj.object_id: {"aliases": [alias]}},
            }]}
            catalog = SemanticCatalogBuilder().build_from_context(context, resolve_model_override(context, registry))
            grounded = ObjectGrounder(catalog).resolve_phrase(alias, SemanticObjectType.MEASURE, "measure")
            assert grounded.canonical_object.object_id == obj.object_id
            for other_key, (other_context, _, _, _) in saved.items():
                if other_key == key:
                    continue
                assert resolve_model_override(other_context, registry) is None
                other = SemanticCatalogBuilder().build_from_context(other_context)
                assert not any(alias in item.aliases for item in other.objects)
            checked += 1
    return checked


async def main(*, verify_members=False):
    settings = Settings(_env_file=None, powerbi_mode=PowerBIMode.LOCAL_MCP)
    adapter = MetadataAuditAdapter(
        executable=settings.powerbi_local_mcp_executable,
        package=settings.powerbi_local_mcp_package, readonly=True,
        timeout=120, max_retries=0,
    )
    summaries = []
    with owned_acceptance_tempdir(prefix="powerbiagent-context-audit-") as root:
        registry = ArtifactOwnershipRegistry(root / "ownership.json")
        run_id = "context-audit-" + uuid.uuid4().hex
        registry.register_run(test_run_id=run_id, test_namespace=run_id, runtime_mode="isolated", source_mode="real")
        try:
            discovery = await SemanticModelDiscoveryService(adapter, settings).discover()
            options = [item for item in discovery.items if item.selectable]
            if not options:
                raise RuntimeError("no_selectable_runtime_model")
            if verify_members and len(options) < 2:
                raise RuntimeError("member_isolation_requires_multiple_runtime_models")
            async def no_renderer(*_):
                raise AssertionError("no renderer in metadata audit")
            gateway = create_default_tool_gateway(adapter, SimpleNamespace(render=no_renderer), HarnessConfig.from_settings(settings))
            saved = {}
            for option in options:
                execution = ToolExecutionContext(
                    intent=IntentType.DATA_QUESTION, runtime_mode=RuntimeDataMode.REAL,
                    user=UserContext(allowed_semantic_models=[option.key], allowed_tools=["get_semantic_model_schema", "get_column_members"]),
                )
                start = time.perf_counter()
                schema = await gateway.execute("get_semantic_model_schema", execution, SchemaInput(semantic_model_key=option.key))
                fetch_ms = (time.perf_counter() - start) * 1000
                start = time.perf_counter()
                context = ModelSemanticContextBuilder().build(schema)
                build_ms = (time.perf_counter() - start) * 1000
                start = time.perf_counter()
                catalog = SemanticCatalogBuilder().build_from_context(context)
                catalog_ms = (time.perf_counter() - start) * 1000
                members, verified = await read_members(gateway, execution, context, catalog) if verify_members else ({}, 0)
                role = SemanticGroundingService(catalog)._resolve_date_field("今年").model_dump(mode="json")
                saved[option.key] = (context, execution, members, role)
                summaries.append({
                    "tables": len(context.tables), "columns": len(context.columns), "measures": len(context.measures),
                    "hierarchies": len(context.hierarchies), "relationships": len(context.relationships),
                    "descriptions": sum(bool(obj.description) for obj in (*context.columns, *context.measures)),
                    "display_names": sum(bool(obj.display_name) for obj in (*context.columns, *context.measures)),
                    "temporal_evidence": dict(Counter(e.kind for e in context.temporal_candidates)),
                    "runtime_only": all(not obj.aliases for obj in catalog.objects),
                    "schema_fetch_ms": round(fetch_ms, 3), "context_build_ms": round(build_ms, 3), "catalog_build_ms": round(catalog_ms, 3),
                    "member_fields_checked": len(members), "canonical_members_verified": verified,
                })
            # Revalidate every discovered exact key after switching through all
            # other models. No first-instance selection or fallback.
            for key, (prior, execution, prior_members, prior_role) in saved.items():
                schema = await gateway.execute("get_semantic_model_schema", execution, SchemaInput(semantic_model_key=key))
                current = ModelSemanticContextBuilder().build(schema)
                assert current == prior
                current_catalog = SemanticCatalogBuilder().build_from_context(current)
                if verify_members:
                    current_members, _ = await read_members(gateway, execution, current, current_catalog)
                    assert current_members == prior_members
                assert SemanticGroundingService(current_catalog)._resolve_date_field("今年").model_dump(mode="json") == prior_role
            override_checks = audit_overrides(saved)
            differing_fields = sum(
                left[field].values != right[field].values
                for left_key, (_, _, left, _) in saved.items()
                for right_key, (_, _, right, _) in saved.items() if left_key < right_key
                for field in left.keys() & right.keys()
            )
            registry.complete_run(run_id)
        finally:
            await adapter.aclose()
        print(json.dumps({"metadata_fields": adapter.field_presence, "models": summaries,
            "isolation_revalidation": True, "member_isolation_checked": verify_members,
            "same_named_fields_with_different_members": differing_fields,
            "single_object_override_checks": override_checks,
            "temporal_role_revalidation": True, "business_resources_created": 0,
            "full_chat_memory_acceptance": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--members", action="store_true", help="Also validate real member and transient language isolation; never prints values")
    args = parser.parse_args()
    asyncio.run(main(verify_members=args.members))
