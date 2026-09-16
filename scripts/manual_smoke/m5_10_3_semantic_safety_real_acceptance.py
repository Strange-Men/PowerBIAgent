"""Scoped M5.10.3 Real Local MCP acceptance without reading ``.env``.

The language provider is deterministic and acceptance-owned.  Runtime schema,
member validation, deterministic DAX, Power BI execution, result inspection and
VerifiedFactSet all use the production pipeline.  The script prints only safe
semantic/audit metadata; it never prints credentials, connection properties or
business rows.
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml
from httpx import ASGITransport, AsyncClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.acceptance_tempdir import owned_acceptance_tempdir

from backend.app.config.settings import (
    LLMMode,
    PersistenceBackend,
    PowerBIMode,
    Settings,
)
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
from backend.app.harness.tool_registry import SchemaInput
from backend.app.intent.models import IntentSpec, IntentType, TurnRelation
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.llm.profiles import LLMModelProfile, LLMProviderProtocol
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.memory.models import RuntimeDataMode
from backend.app.persistence.artifact_ownership import (
    ArtifactOwnershipRegistry,
    managed_test_run,
    probe_owned_sqlite_residuals,
)
from backend.app.persistence.database import create_engine
from backend.app.persistence.models import Base
from backend.app.presentation.localization import DisplayTranslationResponse
from backend.app.query_plan.grounding import CandidateSelection
from backend.app.query_plan.model_override import resolve_model_override
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.query_plan.semantic_catalog import (
    DEFAULT_GLOSSARY_PATH,
    SemanticCatalogBuilder,
)
from backend.app.schemas.data_contracts import (
    QueryPlan,
    QueryShape,
    StructuredFilter,
    UserContext,
)


RICH_MODEL = "PowerBIAgent_M3_Rich_Test"
LOGISTICS_MODEL = "PowerBIAgent_M5_8_5_Logistics_Test"


def check(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(label)


def _walk_dicts(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


class DeterministicSemanticSafetyProvider(LLMProvider):
    """Supply language drafts only; runtime metadata remains authoritative."""

    provider_name = "m5103-deterministic-language"
    is_mock = False

    def __init__(self) -> None:
        self.active = "p0_a"
        self.model_key = ""
        self.calls: list[LLMRequest] = []

    async def generate(self, request, output_type):
        self.calls.append(request)
        if request.task == LLMTask.SEMANTIC_SELECTION:
            structured = self._selection(request.messages[-1]["content"])
        elif request.task == LLMTask.INTENT_RECOGNITION:
            structured = self._intent()
        elif request.task == LLMTask.QUERY_PLAN:
            structured = self._plan()
        elif request.task == LLMTask.DISPLAY_TRANSLATION:
            structured = DisplayTranslationResponse()
        else:
            raise AssertionError(f"unexpected_llm_task:{request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="m5103-deterministic-language",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    def _selection(self, content: str) -> CandidateSelection:
        # Member selection has one JSON object as its complete user message.
        if content.lstrip().startswith("{"):
            data = json.loads(content)
            requested = str(data.get("requested_value", "")).strip()
            translated = (
                "South" if "华南" in requested
                else "North" if "华北" in requested
                else None
            )
            if translated is None:
                return CandidateSelection(outcome="UNRESOLVED")
            matches = [
                item for item in data.get("candidates", [])
                if str(item.get("value", "")).casefold() == translated.casefold()
            ]
            if len(matches) != 1:
                return CandidateSelection(outcome="UNRESOLVED")
            return CandidateSelection(
                outcome="RESOLVED", candidate_id=matches[0]["candidate_id"]
            )

        role_match = re.search(r"^角色：([^\r\n]+)", content, re.MULTILINE)
        phrase_match = re.search(r"^当前短语：([^\r\n]*)", content, re.MULTILINE)
        role = role_match.group(1).strip() if role_match else ""
        phrase = phrase_match.group(1).strip() if phrase_match else ""
        desired = {
            "measure": {
                "correct_measure": "Total Quantity",
                "logistics": "Total Shipments",
            }.get(self.active, "Total Sales"),
            "dimension": "Region" if self.active == "rank_region" else "Product",
            "ranking_dimension": (
                "Region" if self.active == "rank_region" else "Product"
            ),
            "filter_field": "Region",
        }.get(role)
        if desired is None:
            return CandidateSelection(outcome="UNRESOLVED")
        payload = content.split("候选：\n", 1)[-1]
        try:
            candidates = [
                item
                for item in _walk_dicts(json.loads(payload))
                if item.get("object_id") and item.get("canonical_name") == desired
            ]
        except json.JSONDecodeError:
            candidates = []
        if role in {"dimension", "ranking_dimension", "filter_field"}:
            dimension_side = [
                item for item in candidates if item.get("table_name") == desired
            ]
            if dimension_side:
                candidates = dimension_side
        if len(candidates) != 1:
            return CandidateSelection(outcome="UNRESOLVED")
        return CandidateSelection(
            outcome="RESOLVED",
            candidate_id=candidates[0]["object_id"],
            matched_phrase=phrase or None,
        )

    def _intent(self) -> IntentSpec:
        values: dict[str, Any] = {
            "intent": IntentType.DATA_QUESTION,
            "confidence": 0.99,
            "normalized_question": self.message,
        }
        if self.active == "p0_a":
            values.update(
                detected_measures=["最挣钱"],
                detected_dimensions=["哪三个产品"],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
        elif self.active == "south_seed":
            values.update(
                detected_measures=["销售额"],
                detected_filters=[
                    {"field": "区域", "operator": "eq", "value": "华南"}
                ],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
        elif self.active == "rank_region":
            values.update(
                detected_dimensions=["区域"],
                turn_relation=TurnRelation.FOLLOW_UP,
            )
        elif self.active == "rank_south_product":
            values.update(
                detected_measures=["销售额"],
                detected_dimensions=["产品"],
                detected_filters=[
                    {"field": "区域", "operator": "eq", "value": "South"}
                ],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
        elif self.active == "correct_measure":
            values.update(
                detected_measures=["销售数量"],
                turn_relation=TurnRelation.REPLACE,
            )
        elif self.active in {"correct_region", "unknown_region"}:
            values.update(
                detected_filters=[{
                    "field": "区域",
                    "operator": "eq",
                    "value": (
                        "North" if self.active == "correct_region" else "火星区"
                    ),
                }],
                turn_relation=TurnRelation.REPLACE,
            )
        elif self.active in {"normal_sales", "rich_isolation"}:
            values.update(
                detected_measures=["总销售额"],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
        elif self.active == "logistics":
            values.update(
                detected_measures=["Total Shipments"],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
        else:  # pragma: no cover - acceptance exhaustiveness
            raise AssertionError(f"unknown_case:{self.active}")
        return IntentSpec.model_validate(values)

    def _plan(self) -> QueryPlan:
        values: dict[str, Any] = {
            "normalized_question": self.message,
            "semantic_model_key": self.model_key,
        }
        if self.active == "p0_a":
            values.update(
                query_shape=QueryShape.RANKING,
                measures=["Total Sales"],
                dimensions=["Product"],
                sort="desc",
                top_n=3,
            )
        elif self.active == "south_seed":
            values.update(
                query_shape=QueryShape.SCALAR,
                measures=["Total Sales"],
                filters=[StructuredFilter(field="Region", value="华南")],
            )
        elif self.active == "rank_region":
            values.update(
                query_shape=QueryShape.RANKING,
                dimensions=["Region"],
                sort="desc",
                top_n=1,
            )
        elif self.active == "rank_south_product":
            values.update(
                query_shape=QueryShape.RANKING,
                measures=["Total Sales"],
                dimensions=["Product"],
                filters=[StructuredFilter(field="Region", value="South")],
                sort="desc",
                top_n=3,
            )
        elif self.active == "correct_measure":
            values["measures"] = ["Total Quantity"]
        elif self.active in {"correct_region", "unknown_region"}:
            values["filters"] = [StructuredFilter(
                field="Region",
                value="North" if self.active == "correct_region" else "火星区",
            )]
        elif self.active in {"normal_sales", "rich_isolation"}:
            values.update(
                query_shape=QueryShape.SCALAR,
                measures=["Total Sales"],
            )
        elif self.active == "logistics":
            values.update(
                query_shape=QueryShape.SCALAR,
                measures=["Total Shipments"],
            )
        else:  # pragma: no cover - acceptance exhaustiveness
            raise AssertionError(f"unknown_case:{self.active}")
        return QueryPlan.model_validate(values)

    @property
    def message(self) -> str:
        return {
            "p0_a": "哪三个产品最挣钱",
            "south_seed": "华南区域的销售额是多少？",
            "rank_region": "哪个区域卖得最好？",
            "rank_south_product": "华南销售额最高的前3个产品是什么？",
            "correct_measure": "不是销售额，是销售数量",
            "correct_region": "也不是华南，是华北",
            "unknown_region": "也不是华南，是火星区",
            "normal_sales": "总销售额是多少？",
            "rich_isolation": "总销售额是多少？",
            "logistics": "Total Shipments是多少？",
        }[self.active]


def _registry(provider: LLMProvider) -> LLMProviderRegistry:
    registry = LLMProviderRegistry()
    registry.register(
        LLMModelProfile(
            profile_key="deepseek",
            display_name="M5.10.3 deterministic language",
            provider_protocol=LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS,
            base_url="https://acceptance.invalid/v1",
            model="m5103-deterministic-language",
            timeout_seconds=120.0,
        ),
        provider,
    )
    return registry


async def _initialize_database(settings: Settings) -> None:
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def run(root: Path) -> dict[str, Any]:
    database = root / "acceptance.db"
    override_path = root / "validated_override.yaml"
    registry_data = yaml.safe_load(
        DEFAULT_GLOSSARY_PATH.read_text(encoding="utf-8")
    )
    override_path.write_text(
        yaml.safe_dump(registry_data, allow_unicode=True), encoding="utf-8"
    )
    placeholder_credential = "x"
    settings = Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        llm_default_profile="deepseek",
        deepseek_api_key=placeholder_credential,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(database),
        report_artifacts_path=str(root / "reports"),
        presentation_localization_registry_path=str(root / "display.json"),
        powerbi_semantic_override_path=str(override_path),
        powerbi_local_mcp_workers=1,
        request_timeout_seconds=120,
    )
    check(settings.is_local_real_configuration_complete, "configuration_incomplete")
    await _initialize_database(settings)

    provider = DeterministicSemanticSafetyProvider()
    registry = _registry(provider)
    import backend.app.llm.factory as llm_factory

    original_builder = llm_factory.build_llm_registry
    llm_factory.build_llm_registry = lambda _settings: registry
    previous_cwd = Path.cwd()
    os.chdir(root)
    service = None
    case_results: list[dict[str, Any]] = []
    owned_residual = -1
    try:
        # Importing main creates its compatibility app.  The temporary cwd and
        # explicit Settings ensure even that import cannot discover repository .env.
        import backend.app.main as main_module

        # Local MCP child processes must not inherit the owned temp directory as
        # their cwd, otherwise Windows can keep that directory undeletable.
        os.chdir(previous_cwd)

        app = main_module.create_app(settings=settings)
        owner_registry = ArtifactOwnershipRegistry(root / "ownership.json")
        run_id = "m5103-real-" + uuid.uuid4().hex
        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            check(service is not None, "turn_service_unavailable")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://m5103.local"
            ) as client:
                response = await client.get("/api/v1/semantic-models")
                check(response.status_code == 200, "discovery_http_failure")
                options = response.json().get("items", [])

                def exact_model(name: str) -> str:
                    matches = [
                        item for item in options
                        if item.get("selectable") and item.get("display_name") == name
                    ]
                    check(len(matches) == 1, f"model_not_uniquely_selectable:{name}")
                    return str(matches[0]["key"])

                rich_key = exact_model(RICH_MODEL)
                logistics_key = exact_model(LOGISTICS_MODEL)
                execution = ToolExecutionContext(
                    runtime_mode=RuntimeDataMode.REAL,
                    user=UserContext(allowed_semantic_models=[rich_key, logistics_key]),
                )
                rich_schema = await service.tool_gateway.execute(
                    "get_semantic_model_schema",
                    execution,
                    SchemaInput(semantic_model_key=rich_key),
                )
                logistics_schema = await service.tool_gateway.execute(
                    "get_semantic_model_schema",
                    execution,
                    SchemaInput(semantic_model_key=logistics_key),
                )
                rich_context = ModelSemanticContextBuilder().build(rich_schema)
                registry_data["overrides"] = [{
                    "semantic_model_key": rich_key,
                    "runtime_identity": rich_context.runtime_identity,
                    "schema_fingerprint": rich_context.schema_fingerprint,
                    "profile_keys": [
                        "desktop_sales_language",
                        "desktop_order_language",
                        "desktop_calendar_roles",
                        "desktop_region_language",
                    ],
                }]
                validated = resolve_model_override(rich_context, registry_data)
                SemanticCatalogBuilder().build_from_context(rich_context, validated)
                override_path.write_text(
                    yaml.safe_dump(registry_data, allow_unicode=True), encoding="utf-8"
                )
                check(
                    any(
                        measure.name == "Total Shipments"
                        for table in logistics_schema.tables
                        for measure in table.measures
                    ),
                    "logistics_measure_missing",
                )

                dax_tool = service.tool_gateway._tools["execute_dax"]
                original_dax_handler = dax_tool.handler
                dax_count = 0

                async def count_dax(request):
                    nonlocal dax_count
                    dax_count += 1
                    return await original_dax_handler(request)

                dax_tool.handler = count_dax

                async def delete_conversation(identity: str) -> None:
                    reply = await client.delete(
                        f"/api/v1/conversations/{identity}",
                        params={"runtime_mode": "real"},
                    )
                    check(
                        reply.status_code in {200, 404},
                        f"owned_conversation_cleanup_failed:{identity}",
                    )

                async def delete_report(_identity: str) -> None:
                    raise RuntimeError("unexpected_owned_report")

                async def residual_probe(owned):
                    return probe_owned_sqlite_residuals(database, owned)

                async with managed_test_run(
                    owner_registry,
                    test_run_id=run_id,
                    test_namespace=run_id,
                    runtime_mode="real",
                    source_mode="real",
                    delete_conversation=delete_conversation,
                    delete_report=delete_report,
                    residual_probe=residual_probe,
                ) as owner:
                    owner.add_sqlite_path(database)

                    async def post(
                        case: str,
                        active: str,
                        model_key: str,
                        conversation_id: str,
                    ) -> dict[str, Any]:
                        provider.active = active
                        provider.model_key = model_key
                        owner.add_conversation(conversation_id)
                        before = dax_count
                        reply = await client.post(
                            "/api/v1/chat",
                            json={
                                "message": provider.message,
                                "conversation_id": conversation_id,
                                "request_id": str(uuid.uuid4()),
                                "semantic_model_key": model_key,
                                "llm_profile_key": "deepseek",
                            },
                        )
                        body = reply.json()
                        audit = body.get("execution_audit") or {}
                        plan = audit.get("canonical_query_plan") or {}
                        request_memory = None
                        if body.get("terminal_state") != "completed":
                            request_memory = await service.pipeline.get_memory_by_request_id(
                                body["request_id"], RuntimeDataMode.REAL
                            )
                        summary = {
                            "case": case,
                            "http_status": reply.status_code,
                            "terminal_state": body.get("terminal_state"),
                            "error_type": body.get("error_type"),
                            "query_shape": (
                                plan.get("query_shape")
                                or (audit.get("grounded_delta") or {}).get("query_shape")
                            ),
                            "dax_delta": dax_count - before,
                            "dax_executed": bool(audit.get("dax_executed")),
                            "memory_commit": bool(body.get("memory_commit")),
                            "clarification_reason": audit.get("clarification_reason"),
                            "object_status": [
                                {
                                    key: item.get(key)
                                    for key in ("role", "status", "method")
                                }
                                for item in audit.get("object_grounding_status", [])
                            ],
                            "member_status": [
                                {
                                    key: item.get(key)
                                    for key in ("status", "method")
                                }
                                for item in audit.get("member_grounding_status", [])
                            ],
                        }
                        if request_memory is not None:
                            summary["failure_stage"] = request_memory.failure_stage
                            summary["failure_reason"] = request_memory.failure_reason
                        case_results.append(summary)
                        print(json.dumps(summary, ensure_ascii=False), flush=True)
                        check(reply.status_code == 200, f"{case}:http_failure")
                        return body

                    p0a_conversation = str(uuid.uuid4())
                    before = dax_count
                    p0a = await post("p0_a_ranking_paraphrase", "p0_a", rich_key, p0a_conversation)
                    p0a_audit = p0a.get("execution_audit") or {}
                    p0a_plan = p0a_audit.get("canonical_query_plan") or {}
                    if p0a.get("terminal_state") == "completed":
                        check(
                            p0a_plan.get("query_shape") == "ranking"
                            and p0a_plan.get("top_n") == 3
                            and dax_count == before + 1
                            and p0a.get("memory_commit") is True,
                            "p0_a_wrong_question_execution",
                        )
                    else:
                        check(
                            p0a.get("terminal_state") == "clarification_required"
                            and dax_count == before
                            and p0a.get("memory_commit") is False,
                            "p0_a_not_fail_closed",
                        )
                    check(
                        (p0a_audit.get("grounded_delta") or {}).get("query_shape")
                        == "ranking",
                        "p0_a_ranking_obligation_lost",
                    )

                    p0b_conversation = str(uuid.uuid4())
                    before = dax_count
                    seed = await post("p0_b_seed", "south_seed", rich_key, p0b_conversation)
                    ranked = await post("p0_b_same_field_ranking", "rank_region", rich_key, p0b_conversation)
                    seed_plan = seed["execution_audit"]["canonical_query_plan"]
                    rank_audit = ranked["execution_audit"]
                    rank_plan = rank_audit["canonical_query_plan"]
                    check(seed.get("terminal_state") == "completed", "p0_b_seed_failed")
                    check(
                        seed_plan["filters"][0]["field"] == "Region"
                        and seed_plan["filters"][0]["value"] == "South",
                        "p0_b_seed_scope_mismatch",
                    )
                    check(
                        ranked.get("terminal_state") == "completed"
                        and rank_plan["query_shape"] == "ranking"
                        and rank_plan["dimensions"] == ["Region"]
                        and rank_plan["filters"] == []
                        and rank_audit.get("removed_inherited_filter_fields") == ["Region"]
                        and dax_count == before + 2,
                        "p0_b_historical_filter_contamination",
                    )

                    p0c_conversation = str(uuid.uuid4())
                    before = dax_count
                    initial = await post("p0_c_seed", "rank_south_product", rich_key, p0c_conversation)
                    measure = await post("p0_c_measure_correction", "correct_measure", rich_key, p0c_conversation)
                    region = await post("p0_c_region_correction", "correct_region", rich_key, p0c_conversation)
                    final_plan = region["execution_audit"]["canonical_query_plan"]
                    check(
                        all(
                            item.get("terminal_state") == "completed"
                            for item in (initial, measure, region)
                        )
                        and final_plan["query_shape"] == "ranking"
                        and final_plan["measures"] == ["Total Quantity"]
                        and final_plan["dimensions"] == ["Product"]
                        and final_plan["filters"][0]["value"] == "North"
                        and final_plan["sort"] == "desc"
                        and final_plan["top_n"] == 3
                        and dax_count == before + 3,
                        "p0_c_correction_state_leakage",
                    )
                    p0c_memory = await service.pipeline.get_latest_committed_memory(
                        p0c_conversation, RuntimeDataMode.REAL
                    )
                    check(
                        p0c_memory is not None and p0c_memory.memory_version == 3,
                        "p0_c_memory_version_mismatch",
                    )

                    unknown_conversation = str(uuid.uuid4())
                    await post("unknown_seed", "rank_south_product", rich_key, unknown_conversation)
                    before_unknown = dax_count
                    memory_before = await service.pipeline.get_latest_committed_memory(
                        unknown_conversation, RuntimeDataMode.REAL
                    )
                    unknown = await post("unknown_member", "unknown_region", rich_key, unknown_conversation)
                    memory_after = await service.pipeline.get_latest_committed_memory(
                        unknown_conversation, RuntimeDataMode.REAL
                    )
                    check(
                        unknown.get("terminal_state") == "clarification_required"
                        and not unknown.get("memory_commit")
                        and dax_count == before_unknown
                        and memory_before is not None
                        and memory_after is not None
                        and memory_after.memory_version == memory_before.memory_version
                        and memory_after.filters == memory_before.filters,
                        "unknown_member_not_fail_closed",
                    )

                    normal_conversation = str(uuid.uuid4())
                    before = dax_count
                    normal = await post("normal_known_query", "normal_sales", rich_key, normal_conversation)
                    normal_plan = normal["execution_audit"]["canonical_query_plan"]
                    check(
                        normal.get("terminal_state") == "completed"
                        and normal_plan["query_shape"] == "scalar"
                        and normal_plan["measures"] == ["Total Sales"]
                        and dax_count == before + 1,
                        "normal_known_query_regression",
                    )

                    logistics_conversation = str(uuid.uuid4())
                    rich_conversation = str(uuid.uuid4())
                    before = dax_count
                    logistics = await post("isolation_logistics", "logistics", logistics_key, logistics_conversation)
                    rich = await post("isolation_rich", "rich_isolation", rich_key, rich_conversation)
                    logistics_memory = await service.pipeline.get_latest_committed_memory(
                        logistics_conversation, RuntimeDataMode.REAL
                    )
                    rich_memory = await service.pipeline.get_latest_committed_memory(
                        rich_conversation, RuntimeDataMode.REAL
                    )
                    check(
                        logistics.get("terminal_state") == "completed"
                        and rich.get("terminal_state") == "completed"
                        and logistics_memory is not None
                        and rich_memory is not None
                        and logistics_memory.semantic_model_key == logistics_key
                        and rich_memory.semantic_model_key == rich_key
                        and logistics_memory.measures == ["Total Shipments"]
                        and rich_memory.measures == ["Total Sales"]
                        and logistics_memory.memory_version == 1
                        and rich_memory.memory_version == 1
                        and dax_count == before + 2,
                        "conversation_model_isolation_regression",
                    )

                    for body in (seed, ranked, initial, measure, region, normal, logistics, rich):
                        audit = body.get("execution_audit") or {}
                        check(
                            audit.get("deterministic_dax")
                            and audit.get("layer3_pass")
                            and audit.get("factual_validation_pass")
                            and audit.get("llm_dax_call_count") == 0,
                            "factual_authority_regression",
                        )
                owned_residual = 0
                dax_tool.handler = original_dax_handler
        lifecycle = service.powerbi.runtime_lifecycle_snapshot()
        check(
            lifecycle is not None
            and lifecycle.get("session_residual") == 0
            and lifecycle.get("active_workers") == 0,
            "local_mcp_lifecycle_residual",
        )
        # The production engine deliberately uses WAL.  After its disposal,
        # return this private acceptance database to DELETE mode so Windows has
        # no WAL/SHM sidecars to retain during verified temp cleanup.
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA journal_mode = DELETE;").fetchone()
        # Give disposed aiosqlite worker threads one event-loop turn to release
        # Windows file handles before the owned tempdir performs its one-shot
        # verified cleanup.  This is test artifact lifecycle, not product retry.
        gc.collect()
        await asyncio.sleep(0.25)
        return {
            "passed": True,
            "language_provider": "deterministic_acceptance_only",
            "powerbi": "real_local_mcp",
            "models": [RICH_MODEL, LOGISTICS_MODEL],
            "case_count": len(case_results),
            "dax_count": sum(item["dax_delta"] for item in case_results),
            "owned_business_residual": owned_residual,
            "lifecycle": lifecycle,
        }
    finally:
        os.chdir(previous_cwd)
        llm_factory.build_llm_registry = original_builder


async def main() -> None:
    failed = False
    with owned_acceptance_tempdir(prefix="powerbiagent-context-real-") as root:
        try:
            summary = await run(root)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            # The run coroutine owns the disposed SQLAlchemy/aiosqlite graph.
            # Collect it before the context performs one-shot directory cleanup.
            gc.collect()
            await asyncio.sleep(1.0)
        except Exception as error:
            failed = True
            print(
                json.dumps(
                    {"passed": False, "error_type": type(error).__name__, "error": str(error)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
