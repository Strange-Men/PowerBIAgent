"""Real HTTP acceptance with explicit model binding and owned resource cleanup.

Run from the project root. Settings alone loads runtime credentials; this
harness never reads environment files or prints prompts, rows, or secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.acceptance_tempdir import owned_acceptance_tempdir

import httpx
import uvicorn
import yaml

from backend.app.config.settings import Settings, LLMMode, PowerBIMode, PersistenceBackend
from backend.app.main import create_app
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
from backend.app.harness.tool_registry import SchemaInput
from backend.app.memory.models import RuntimeDataMode
from backend.app.persistence.artifact_ownership import ArtifactOwnershipRegistry, managed_test_run, probe_owned_sqlite_residuals
from backend.app.persistence.database import create_engine
from backend.app.persistence.models import Base
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.query_plan.model_override import resolve_model_override
from backend.app.query_plan.semantic_catalog import DEFAULT_GLOSSARY_PATH, SemanticCatalogBuilder
from backend.app.schemas.data_contracts import UserContext
from backend.app.schemas.data_contracts import CanonicalQueryPlan, ColumnMembersRequest
from backend.app.facts.verified import VerifiedFactSetBuilder


async def extended_acceptance(post, service, rich_key, other_key, registry_data, *, only_zero=False, only_temporal=False, only_members=False):
    """Real committed Memory, model switch, fact provenance, and warm/4-way."""
    captured = {}
    dax_tool = service.tool_gateway._tools["execute_dax"]
    original_handler = dax_tool.handler

    async def observe(request):
        result = await original_handler(request)
        captured[result.result_id] = result
        return result

    dax_tool.handler = observe
    checked_facts = 0

    async def completed(label, message, *, key=rich_key, conversation=None):
        nonlocal checked_facts
        body, audit, raw_plan = await post(label, message, key=key, conversation=conversation)
        check(body.get("terminal_state") == "completed" and body.get("memory_commit"), label + ":not_completed")
        plan = CanonicalQueryPlan.model_validate(raw_plan)
        result = captured[audit["result_id"]]
        facts = VerifiedFactSetBuilder().build(plan, result)
        check(plan.semantic_model_key == result.semantic_model_key == key, label + ":model_leak")
        check(facts.fact_set_id == audit["verified_fact_set_id"] and len(facts.facts) == audit["verified_fact_count"], label + ":fact_projection_mismatch")
        check(audit.get("llm_dax_call_count") == 0 and audit.get("layer3_pass"), label + ":factual_authority_changed")
        memory = await service.pipeline.get_latest_committed_memory(body["conversation_id"], RuntimeDataMode.REAL)
        check(memory is not None and memory.semantic_model_key == key and memory.last_query_result_id == result.result_id, label + ":memory_result_mismatch")
        check(memory.measures == plan.measures and memory.dimensions == plan.dimensions, label + ":memory_slots_mismatch")
        checked_facts += 1
        return body, audit, plan, memory

    async def zero_config():
        for label, message, shape, dimension in ((
            ("zero_config_entities", "有哪些Sales[Product]", "entity_list", "Product"),
            ("zero_config_scalar", "Total Sales是多少", "scalar", None),
            ("zero_config_grouped", "按Sales[Category]统计Total Sales", "grouped", "Category"),
            ("zero_config_ranking", "Total Sales最高的是哪个Sales[Product]", "ranking", "Product"),
        ) if not only_temporal else ()):
            _, _, plan, _ = await completed(label, message, key=other_key)
            check(plan.query_shape.value == shape, label + ":shape_mismatch")
            check(plan.dimensions == ([dimension] if dimension else []), label + ":dimension_mismatch")
            if dimension:
                check(plan.dimension_tables[dimension] == "Sales", label + ":ownership_mismatch")
        body, audit, _ = await post("zero_config_missing_temporal", "每月Total Sales趋势", key=other_key)
        check(body.get("terminal_state") == "clarification_required" and not audit.get("dax_executed") and not body.get("memory_commit"), "missing_temporal_not_closed")
        print(json.dumps({"real_unregistered_model_shapes": 0 if only_temporal else 4, "missing_temporal_zero_dax": True, "real_facts_rebuilt_equal": checked_facts}), flush=True)

    async def member_switch():
        members = {}
        for key in (rich_key, other_key):
            execution = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,
                user=UserContext(allowed_semantic_models=[key]))
            values = await service.tool_gateway.execute("get_column_members", execution,
                ColumnMembersRequest(semantic_model_key=key, table_name="Sales", field_name="Product", limit=200))
            check(values.semantic_model_key == key and not values.truncated, "member_snapshot_not_exact")
            members[key] = {value for value in values.values if isinstance(value, str)}
        a_only = members[rich_key] - members[other_key]
        b_only = members[other_key] - members[rich_key]
        check(a_only and b_only, "models_need_different_product_members")
        # Choose test inputs from verified differences, never infer bindings.
        a_value, b_value = min(a_only), min(b_only)
        conversation = str(uuid.uuid4())
        a_question = f"Sales[Product]等于{json.dumps(a_value, ensure_ascii=False)}时，Total Quantity是多少"
        b_question = f"Sales[Product]等于{json.dumps(b_value, ensure_ascii=False)}时，Total Sales是多少"
        _, _, a_plan, a_memory = await completed("member_switch_a", a_question, conversation=conversation)
        _, _, b_plan, b_memory = await completed("member_switch_b", b_question, key=other_key, conversation=conversation)
        check(len(a_plan.filters) == len(b_plan.filters) == 1, "member_filter_missing")
        check(a_plan.filters[0].value == a_value and b_plan.filters[0].value == b_value, "member_value_crossed_model")
        body, audit, _ = await post("member_a_value_rejected_by_b", a_question, key=other_key, conversation=conversation)
        check(body.get("terminal_state") == "clarification_required" and not audit.get("dax_executed") and not body.get("memory_commit"), "foreign_member_was_accepted")
        latest = await service.pipeline.get_latest_committed_memory(conversation, RuntimeDataMode.REAL)
        check(latest.model_dump(mode="json") == b_memory.model_dump(mode="json"), "foreign_member_changed_memory")
        _, _, again, final_memory = await completed("member_switch_back_a", a_question, conversation=conversation)
        check(again.filters == a_plan.filters and final_memory.memory_version == a_memory.memory_version + 2, "member_return_a_mismatch")
        print(json.dumps({"real_member_chat_a_b_a": True, "foreign_member_zero_dax": True, "fact_checks": checked_facts}), flush=True)

    try:
        if only_members:
            await member_switch()
            return
        if only_zero or only_temporal:
            await zero_config()
            return
        conversation = str(uuid.uuid4())
        _, _, first, first_memory = await completed("memory_initial", "2025年5月华南区销售额", conversation=conversation)
        _, _, second, second_memory = await completed("memory_group_followup", "改成按产品看", conversation=conversation)
        check(first.filters and second.filters == first.filters and second.time_range == first.time_range, "followup_lost_filter_or_time")
        check(second_memory.memory_version == first_memory.memory_version + 1, "followup_version")
        _, _, third, third_memory = await completed("memory_measure_replace", "那销量呢", conversation=conversation)
        check(third.measures != second.measures and third.dimensions == second.dimensions and third.filters == second.filters, "replace_slot_leak")
        before = third_memory.model_dump(mode="json")
        body, audit, _ = await post("unknown_member_zero_dax", "火星区销售额", conversation=conversation)
        check(body.get("terminal_state") == "clarification_required" and not audit.get("dax_executed") and not body.get("memory_commit"), "unknown_member_not_closed")
        after = await service.pipeline.get_latest_committed_memory(conversation, RuntimeDataMode.REAL)
        check(after.model_dump(mode="json") == before, "failed_turn_mutated_committed_memory")

        # B is explicitly chosen by display name and has no registry entry.
        check(all(entry["semantic_model_key"] != other_key for entry in registry_data["overrides"]), "other_model_override_leak")
        _, _, b_plan, b_memory = await completed("switch_to_b", "Total Quantity是多少", key=other_key, conversation=conversation)
        check(not b_plan.filters and not b_plan.dimensions and b_plan.time_range is None, "a_slots_leaked_into_b")
        body, audit, _ = await post("b_missing_a_measure", "平均订单金额是多少", key=other_key, conversation=conversation)
        check(body.get("terminal_state") == "clarification_required" and not audit.get("dax_executed") and not body.get("memory_commit"), "a_alias_leaked_into_b")
        _, _, a_plan, a_memory = await completed("return_to_a", "总订单数是多少", conversation=conversation)
        check(a_memory.memory_version > b_memory.memory_version and not a_plan.filters and not a_plan.dimensions and a_plan.time_range is None, "b_slots_leaked_into_a")
        print(json.dumps({"real_chat_memory_switch_a_b_a": True, "failed_turn_memory_unchanged": True}), flush=True)

        await zero_config()

        sequence = ("总销售额是多少？", "2025年5月销售额", "华南区销售额", "每个月销售额趋势")
        warm = []
        for index, message in enumerate(sequence):
            _, audit, _, _ = await completed(f"warm_{index}", message)
            warm.append(audit.get("performance"))
        started = time.perf_counter()
        concurrent = await asyncio.gather(*(completed(f"concurrent_{index}", message) for index, message in enumerate(sequence)))
        print(json.dumps({"warm_performance": warm, "concurrent_4_wall_ms": round((time.perf_counter()-started)*1000, 3),
            "concurrent_4_performance": [item[1].get("performance") for item in concurrent], "fact_checks": checked_facts}), flush=True)
    finally:
        dax_tool.handler = original_handler


def check(condition, label):
    if not condition:
        raise RuntimeError(label)


async def run(args, root):
    database = root / "acceptance.db"
    override_path = root / "validated_override.yaml"
    registry_data = yaml.safe_load(DEFAULT_GLOSSARY_PATH.read_text(encoding="utf-8"))
    override_path.write_text(yaml.safe_dump(registry_data, allow_unicode=True), encoding="utf-8")
    settings = Settings(
        llm_mode=LLMMode.OPENAI_COMPATIBLE, powerbi_mode=PowerBIMode.LOCAL_MCP,
        llm_default_profile=args.profile, persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(database), report_artifacts_path=str(root / "reports"),
        presentation_localization_registry_path=str(root / "display.json"),
        powerbi_semantic_override_path=str(override_path),
    )
    check(settings.is_real_ready, "real_configuration_not_ready")
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False))
    server_task = asyncio.create_task(server.serve())
    owner_registry = ArtifactOwnershipRegistry(root / "ownership.json")
    run_id = "semantic-real-" + uuid.uuid4().hex
    results = []
    try:
        for _ in range(200):
            if server.started:
                break
            if server_task.done():
                await server_task
                raise RuntimeError("real_server_failed_to_start")
            await asyncio.sleep(.05)
        check(server.started, "real_server_start_timeout")
        print(json.dumps({"real_http_backend_started": True, "port": args.port}), flush=True)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{args.port}", timeout=180) as client:
            response = await client.get("/health")
            check(response.status_code == 200, "real_health_failed")
            response = await client.get("/api/v1/semantic-models")
            check(response.status_code == 200, "discovery_failed")
            options = response.json().get("items", [])
            matches = [o for o in options if o.get("selectable") and o.get("display_name") == args.rich_model]
            check(len(matches) == 1, "rich_model_not_exact_unique")
            rich_key = matches[0]["key"]
            service = app.state.turn_service
            original_execute = service.execute

            async def observe_exception(*call_args, **call_kwargs):
                try:
                    return await original_execute(*call_args, **call_kwargs)
                except Exception as error:
                    print(json.dumps({"service_error_type":type(error).__name__, "frames":[
                        {"file":Path(frame.filename).name,"line":frame.lineno,"function":frame.name}
                        for frame in traceback.extract_tb(error.__traceback__)
                    ]}), flush=True)
                    raise

            service.execute = observe_exception
            execution = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,
                user=UserContext(allowed_semantic_models=[rich_key]))
            schema = await service.tool_gateway.execute("get_semantic_model_schema", execution, SchemaInput(semantic_model_key=rich_key))
            context = ModelSemanticContextBuilder().build(schema)
            # This manually invoked acceptance explicitly selects the named
            # model and existing profiles. Never persist an automatic binding.
            registry_data["overrides"] = [{
                "semantic_model_key": rich_key, "runtime_identity": context.runtime_identity,
                "schema_fingerprint": context.schema_fingerprint,
                "profile_keys": ["desktop_sales_language", "desktop_order_language", "desktop_calendar_roles", "desktop_region_language"],
            }]
            validated = resolve_model_override(context, registry_data)
            SemanticCatalogBuilder().build_from_context(context, validated)
            override_path.write_text(yaml.safe_dump(registry_data, allow_unicode=True), encoding="utf-8")
            print(json.dumps({"exact_rich_override_validated": True, "selectable_models": sum(bool(o.get("selectable")) for o in options)}), flush=True)

            async def delete_conversation(identity):
                reply = await client.delete(f"/api/v1/conversations/{identity}", params={"runtime_mode": "real"})
                check(reply.status_code in (200, 404), "owned_conversation_cleanup_failed")

            async def delete_report(identity):
                raise RuntimeError("unexpected_owned_report")

            async def residual_probe(owned):
                return probe_owned_sqlite_residuals(database, owned)

            async with managed_test_run(owner_registry, test_run_id=run_id, test_namespace=run_id,
                runtime_mode="real", source_mode="real", delete_conversation=delete_conversation,
                delete_report=delete_report, residual_probe=residual_probe) as owner:
                owner.add_sqlite_path(database)

                async def post(label, message, *, key=rich_key, conversation=None):
                    conversation = conversation or str(uuid.uuid4())
                    owner.add_conversation(conversation)
                    started = time.perf_counter()
                    reply = await client.post("/api/v1/chat", json={"message": message,
                        "conversation_id": conversation, "request_id": str(uuid.uuid4()),
                        "semantic_model_key": key, "llm_profile_key": args.profile})
                    body = reply.json()
                    audit = body.get("execution_audit") or {}
                    plan = audit.get("canonical_query_plan") or {}
                    summary = {"case": label, "http_status": reply.status_code,
                        "terminal_state": body.get("terminal_state"), "error_type": body.get("error_type"),
                        "query_shape": plan.get("query_shape") or audit.get("query_shape"),
                        "dax_executed": bool(audit.get("dax_executed")), "memory_commit": body.get("memory_commit"),
                        "latency_ms": round((time.perf_counter()-started)*1000, 3)}
                    results.append(summary)
                    print(json.dumps(summary), flush=True)
                    if body.get("terminal_state") == "clarification_required":
                        print(json.dumps({"case":label,"missing_slots":audit.get("missing_slots"),
                            "object_status":[{k:v for k,v in item.items() if k in {"role", "status", "method"}} for item in audit.get("object_grounding_status", [])],
                            "member_status":[{k:v for k,v in item.items() if k in {"status", "method"}} for item in audit.get("member_grounding_status", [])]}), flush=True)
                    check(reply.status_code == 200, label + ":http_failure")
                    return body, audit, plan

                # Identical questions and assertions to the frozen 15-case
                # M5.8.2 manual smoke; no expected numbers enter this harness.
                for label, message, shape in ((
                    ("average_order_value", "平均订单金额是多少", "scalar"),
                    ("total_orders", "总订单数是多少", "scalar"),
                    ("product_list", "我们销售了哪些产品？", "entity_list"),
                    ("top_one_product", "销量最高的是哪款产品？", "ranking"),
                    ("bounded_trend_a", "2025年8月到2026年1月销售额月趋势", "bounded_trend"),
                    ("bounded_trend_b", "从2025年8月至2026年1月按月看销售额", "bounded_trend"),
                ) if args.phase == "rich" else ()):
                    body, audit, plan = await post(label, message)
                    check(body.get("terminal_state") == "completed", label + ":not_completed")
                    check(plan.get("query_shape") == shape, label + ":shape_mismatch")
                    check(audit.get("dax_executed") and body.get("memory_commit"), label + ":execution_missing")
                    check(shape != "entity_list" or not plan.get("measures"), "entity_list_measure_leak")
                    check(shape != "ranking" or plan.get("top_n") == 1, "top_one_mismatch")
                if args.phase == "rich":
                    body, audit, _ = await post("ambiguous_best", "哪些产品卖得最好？")
                    check(body.get("terminal_state") == "clarification_required" and body.get("clarification_question") == "请明确用于判断排名的业务指标。" and not audit.get("dax_executed"), "minimal_ranking_clarification_failed")
                for label, message, shape in ((
                    ("member_set", "手机和笔记本的销量分别是多少？", "member_set"),
                    ("filtered_aggregation", "手机和电脑加起来销量是多少", "filtered_aggregation"),
                ) if args.phase == "rich" else ()):
                    body, audit, plan = await post(label, message)
                    if body.get("terminal_state") == "completed":
                        filters = plan.get("filters") or []
                        check(plan.get("query_shape") == shape and len(filters) == 1 and filters[0].get("operator") == "in", label + ":set_mismatch")
                    else:
                        check(body.get("terminal_state") == "clarification_required" and not audit.get("dax_executed") and not body.get("memory_commit"), label + ":not_fail_closed")
                for label, message, route in ((
                    ("product_help_a", "你支持回答哪些问题？", "product_help"),
                    ("product_help_b", "数据分析支持的范围在哪", "product_help"),
                    ("system_info", "你是什么模型", "system_info"),
                    ("identity", "我是谁", "unsupported_general"),
                    ("calculator_add", "1+1等于几", "deterministic_calc"),
                    ("calculator_multiply", "50乘50是几", "deterministic_calc"),
                ) if args.phase == "rich" else ()):
                    body, audit, _ = await post(label, message)
                    check((audit.get("question_route") or audit.get("capability_decision")) == route and not audit.get("schema_read") and not audit.get("dax_executed") and not body.get("memory_commit") and not body.get("tool_sequence"), label + ":non_business_isolation_failed")
                if args.phase == "rich":
                    check(len(results) == 15, "rich_case_count")
                    print(json.dumps({"rich_15_passed": True}), flush=True)
                else:
                    other = [o for o in options if o.get("selectable") and o.get("display_name") == args.other_model]
                    check(len(other) == 1 and other[0]["key"] != rich_key, "other_model_not_exact_unique")
                    await extended_acceptance(post, service, rich_key, other[0]["key"], registry_data,
                        only_zero=args.phase == "zero", only_temporal=args.phase == "temporal", only_members=args.phase == "members")
            print(json.dumps({"owned_business_residual": 0}), flush=True)
    finally:
        server.should_exit = True
        await server_task


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rich-model", required=True)
    parser.add_argument("--profile", default="deepseek")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--phase", choices=("rich", "extended", "zero", "temporal", "members"), default="rich")
    parser.add_argument("--other-model")
    args = parser.parse_args()
    failed = False
    with owned_acceptance_tempdir(prefix="powerbiagent-context-real-") as root:
        try:
            await run(args, root)
        except Exception as exc:
            failed = True
            print(json.dumps({"gate_failed": type(exc).__name__,
                "check": str(exc) if type(exc) is RuntimeError else "runtime_failure"}), flush=True)
        finally:
            print(json.dumps({"real_server_stopped": True}), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
