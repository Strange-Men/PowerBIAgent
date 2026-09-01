"""Manual HTTP/real-provider/real-PBIX gate with zero language overrides.

Settings loads credentials normally from the project root. No secret/raw LLM
response is inspected. Full execution witnesses remain in memory; output is
restricted to questions, canonical metadata, status, counts and hashes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx
import uvicorn
from pydantic import ValidationError

from backend.app.config.settings import Settings, LLMMode, PowerBIMode, PersistenceBackend
from backend.app.main import create_app
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
from backend.app.harness.tool_registry import SchemaInput
from backend.app.memory.models import RuntimeDataMode
from backend.app.persistence.artifact_ownership import ArtifactOwnershipRegistry, managed_test_run, probe_owned_sqlite_residuals
from backend.app.persistence.database import create_engine
from backend.app.persistence.models import Base
from backend.app.query_plan.grounding import BoundedLLMObjectSelector
from backend.app.llm.base import LLMProviderError
from backend.app.llm.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.schemas.data_contracts import CanonicalQueryPlan, UserContext, ColumnMembersRequest
from backend.app.facts.verified import VerifiedFactSetBuilder
from scripts.acceptance_tempdir import owned_acceptance_tempdir

ACCEPTANCE_REQUEST = ContextVar("cross_language_acceptance_request", default=None)


@contextmanager
def observe_provider_failures(failures, *, provider_type=OpenAICompatibleLLMProvider):
    """Observe safe categories before weak-draft services handle exceptions."""
    original = provider_type.generate

    async def generate(self, request, output_type):
        try:
            response = await original(self, request, output_type)
            if request.task.value in {"intent_recognition", "query_plan"}:
                for failure in failures.get(ACCEPTANCE_REQUEST.get(), []):
                    if failure["task"] == request.task.value and failure["category"] == "response_validation":
                        failure["repaired"] = True
            return response
        except LLMProviderError as error:
            failure = {"task": request.task.value, "category": error.error_category.value}
            if error.error_code in {"invalid_content_json", "output_schema_invalid", "empty_content",
                    "connect_timeout", "read_timeout", "pool_timeout", "write_timeout",
                    "connect_error", "read_error", "write_error", "connection_error",
                    "remote_protocol_error", "invalid_choices", "invalid_http_json"}:
                failure["code"] = error.error_code
            if isinstance(error.__cause__, ValidationError):
                # Only declared top-level field names and Pydantic type codes;
                # never raw input, validator context, messages or custom keys.
                fields = getattr(output_type, "model_fields", {})
                failure["schema_errors"] = [{"field": item["loc"][0] if item["loc"]
                    and item["loc"][0] in fields else "<root>", "type": item["type"]}
                    for item in error.__cause__.errors(include_input=False, include_context=False,
                        include_url=False)[:12]]
            failures.setdefault(ACCEPTANCE_REQUEST.get(), []).append(failure)
            raise

    provider_type.generate = generate
    try:
        yield
    finally:
        provider_type.generate = original


def negative_outcome_verified(audit, provider_failures, label):
    if any(not failure.get("repaired", False) for failure in provider_failures) or audit.get("dax_executed"):
        return False
    objects = audit.get("object_grounding_status") or []
    members = audit.get("member_grounding_status") or []
    if any("unavailable" in item.get("method", "") for item in [*objects, *members]):
        return False
    if label in {"unknown", "mixed_unknown", "compound_region", "unproved_place", "unknown_follow", "foreign_member"}:
        return (any(item.get("status") in {"UNRESOLVED", "AMBIGUOUS"} for item in members)
            or any(item.get("method") == "current_incomplete_member_conjunction"
                and item.get("status") == "UNRESOLVED" for item in objects))
    return True


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


@asynccontextmanager
async def tracked_acceptance_turns(service, owner, root, *, browser=False, drain_seconds=30):
    """Drain/cancel owned requests before resource teardown, even after HTTP failure."""
    original = service.execute
    active = set()

    async def execute(*positional, **keywords):
        identity = keywords.get("conversation_id")
        if not identity:
            raise RuntimeError("acceptance_requires_client_uuid")
        owner.add_conversation(identity)
        task = asyncio.current_task()
        active.add(task)
        token = ACCEPTANCE_REQUEST.set(keywords.get("request_id"))
        try:
            result = await original(*positional, **keywords)
            report = result.get("report") or {}
            if report.get("report_id"):
                owner.add_report(report["report_id"], html_path=root / "reports" / (report["report_id"] + ".html"))
            if browser:
                print(json.dumps({"browser_turn": keywords.get("message"),
                    "terminal": result.get("terminal_state"), "response_type": result.get("response_type"),
                    "canonical": (result.get("execution_audit") or {}).get("canonical_query_plan")}, ensure_ascii=False), flush=True)
            return result
        finally:
            ACCEPTANCE_REQUEST.reset(token)
            active.discard(task)

    service.execute = execute
    try:
        yield
    finally:
        if active:
            _, pending = await asyncio.wait(tuple(active), timeout=drain_seconds)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        service.execute = original


async def run(args, root, provider_failures):
    bootstrap_started = time.perf_counter()
    database = root / "acceptance.db"
    override = root / "empty_override.yaml"
    override.write_text("version: 2\nprofiles: {}\noverrides: []\n", encoding="utf-8")
    settings = Settings(llm_mode=LLMMode.OPENAI_COMPATIBLE, powerbi_mode=PowerBIMode.LOCAL_MCP,
        llm_default_profile=args.profile, persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(database), report_artifacts_path=str(root / "reports"),
        presentation_localization_registry_path=str(root / "display.json"),
        powerbi_semantic_override_path=str(override))
    if not settings.is_real_ready:
        raise RuntimeError("real_configuration_not_ready")
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    app = create_app(settings)
    if args.phase == "browser":
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="acceptance-ui")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="critical", access_log=False,
        timeout_graceful_shutdown=10))
    server_task = asyncio.create_task(server.serve())
    witnesses, selections, summaries = {}, {}, []
    original_select = BoundedLLMObjectSelector.select
    original_member_select = BoundedLLMObjectSelector.select_member
    member_selections = []

    async def observe_selection(self, phrase, user_input, candidates, committed_context="", **kwargs):
        result = await original_select(self, phrase, user_input, candidates, committed_context, **kwargs)
        selections.setdefault(ACCEPTANCE_REQUEST.get(), []).append({"role": kwargs.get("role"), "phrase": phrase,
            "candidate_evidence": kwargs.get("evidence"), "status": result.status.value,
            "selected_id": result.canonical_object.object_id if result.canonical_object else None})
        return result

    BoundedLLMObjectSelector.select = observe_selection
    async def observe_member(self, requested_value, field, members, **kwargs):
        result = await original_member_select(self, requested_value, field, members, **kwargs)
        member_selections.append({"request_id": ACCEPTANCE_REQUEST.get(), "user_input": kwargs.get("user_input"), "requested": requested_value,
            "field_id": field.object_id, "candidate_values": members.values,
            "truncated": members.truncated, "status": result.status.value, "method": result.method})
        return result
    BoundedLLMObjectSelector.select_member = observe_member
    try:
        for _ in range(200):
            if server.started:
                break
            if server_task.done():
                await server_task
                raise RuntimeError("server_not_started")
            await asyncio.sleep(.05)
        if not server.started:
            raise RuntimeError("server_start_timeout")
        # Local acceptance traffic must not take the machine's external proxy.
        # The longer observer deadline lets production's own LLM timeouts finish;
        # it does not change provider timeouts or retry failed semantic choices.
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{args.port}", timeout=600, trust_env=False) as client:
            reply = await client.get("/api/v1/semantic-models")
            options = [item for item in reply.json()["items"] if item.get("selectable")]
            service = app.state.turn_service
            schemas = {}
            for item in options:
                execution = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL, user=UserContext(allowed_semantic_models=[item["key"]]))
                runtime = await service.tool_gateway.execute("get_semantic_model_schema", execution, SchemaInput(semantic_model_key=item["key"]))
                schemas[item["key"]] = runtime
                if args.phase == "inspect":
                    context = ModelSemanticContextBuilder().build(runtime)
                    print(json.dumps({"model": item["display_name"], "context": context.model_dump(mode="json")}, ensure_ascii=False), flush=True)
            if args.phase == "inspect":
                return
            bootstrap_ms = round((time.perf_counter() - bootstrap_started) * 1000, 2)
            matches = [item for item in options if item["display_name"] == args.model]
            if len(matches) != 1:
                raise RuntimeError("explicit_model_not_unique")
            key = matches[0]["key"]
            dax_tool = service.tool_gateway._tools["execute_dax"]
            original_handler = dax_tool.handler

            async def observe_dax(request):
                result = await original_handler(request)
                witnesses[result.result_id] = {"dax": request.dax, "result": result}
                return result

            dax_tool.handler = observe_dax
            registry = ArtifactOwnershipRegistry(root / "ownership.json")
            run_id = "cross-language-real-" + uuid.uuid4().hex
            async def delete_conversation(identity):
                response = await client.delete(f"/api/v1/conversations/{identity}", params={"runtime_mode": "real"})
                assert response.status_code in (200, 404)
            async def delete_report(identity):
                response = await client.delete(f"/api/v1/reports/{identity}", params={"source_mode": "real"})
                assert response.status_code in (200, 404)
            async def residual(owned):
                return probe_owned_sqlite_residuals(database, owned)
            async with managed_test_run(registry, test_run_id=run_id, test_namespace=run_id,
                    runtime_mode="real", source_mode="real", delete_conversation=delete_conversation,
                    delete_report=delete_report, residual_probe=residual) as owner, \
                    tracked_acceptance_turns(service, owner, root, browser=args.phase == "browser"):
                owner.add_sqlite_path(database)
                owner.add_report_root(root / "reports")

                if args.phase == "browser":
                    print(json.dumps({"browser_ready": True, "finish_marker": str(root / "browser-finished")}), flush=True)
                    deadline = time.monotonic() + 1800
                    while not (root / "browser-finished").exists():
                        if time.monotonic() > deadline:
                            raise RuntimeError("browser_acceptance_timeout")
                        await asyncio.sleep(.2)
                    return

                async def post(label, text, shape=None, *, conversation=None, model_key=key, profile=args.profile, template=None, blocked=False):
                    conversation = conversation or str(uuid.uuid4())
                    request_id = str(uuid.uuid4())
                    owner.add_conversation(conversation)
                    witness_count_before = len(witnesses)
                    started = time.perf_counter()
                    response = await client.post("/api/v1/chat", json={"message": text,
                        "semantic_model_key": model_key, "conversation_id": conversation,
                        "request_id": request_id, "llm_profile_key": profile,
                        "report_template_key": template})
                    body = response.json()
                    audit = body.get("execution_audit") or {}
                    plan = audit.get("canonical_query_plan") or {}
                    report = body.get("report") or {}
                    if report.get("report_id"):
                        owner.add_report(report["report_id"], html_path=root / "reports" / (report["report_id"] + ".html"))
                    success = response.status_code == 200 and body.get("terminal_state") == ("clarification_required" if blocked else "completed")
                    if blocked:
                        success &= not audit.get("dax_executed") and not body.get("memory_commit")
                        success &= negative_outcome_verified(audit, provider_failures.get(request_id, []), label)
                    elif shape:
                        success &= plan.get("query_shape") == shape and bool(body.get("memory_commit"))
                        case = label.removeprefix("first_").removeprefix("cold_").removeprefix("warm_").removeprefix("concurrent_")
                        expected_measure = {"sales": "Total Sales", "orders": "Total Orders",
                            "grouped": "Total Sales", "top1": "Total Quantity", "top3": "Total Sales",
                            "trend": "Total Sales", "bounded": "Total Sales", "south": "Total Sales",
                            "synonym": "Total Sales", "english": "Total Sales",
                            "quantity": "Total Quantity",
                            "category": "Total Sales", "a_orders": "Total Orders", "back_a_orders": "Total Orders",
                            "b_quantity": "Total Quantity", "a_member": "Total Quantity", "back_a_member": "Total Quantity", "b_member": "Total Sales",
                            "member_set": "Total Sales", "combined": "Total Sales"}.get(case)
                        if expected_measure:
                            success &= plan.get("measures") == [expected_measure]
                        expected_dimension = {"entities": "Product", "grouped": "Region", "top1": "Product",
                            "top3": "Product", "trend": "YearMonth", "bounded": "YearMonth",
                            "member_set": "Region"}.get(case)
                        if expected_dimension:
                            success &= plan.get("dimensions") == [expected_dimension]
                            success &= (plan.get("dimension_tables") or {}).get(expected_dimension) == ("Date" if expected_dimension == "YearMonth" else expected_dimension)
                        if case in {"top1", "top3"}:
                            success &= plan.get("top_n") == (1 if case == "top1" else 3) and plan.get("sort") == "desc"
                        if case == "south":
                            success &= plan.get("filters") == [{"field": "Region", "operator": "eq", "value": "South"}]
                        if case == "bounded":
                            success &= (plan.get("time_range") or {}).get("start_date") == "2025-08-01"
                            success &= (plan.get("time_range") or {}).get("end_date") == "2026-01-31"
                        if case in {"member_set", "combined"}:
                            success &= plan.get("filters") == [{"field": "Region", "operator": "in", "value": ["South", "North"]}]
                            success &= (plan.get("dimension_tables") or {}).get("Region") == "Region"
                            if case == "combined":
                                success &= plan.get("dimensions") == []
                        if case == "category":
                            success &= plan.get("dimensions") == ["Category"]
                            success &= (plan.get("dimension_tables") or {}).get("Category") == "Product"
                        if case in {"initial", "keep", "replace"}:
                            success &= plan.get("measures") == ["Total Quantity" if case == "replace" else "Total Sales"]
                            success &= plan.get("dimensions") == ([] if case == "initial" else ["Product"])
                            success &= plan.get("filters") == [{"field": "Region", "operator": "eq", "value": "South"}]
                            success &= plan.get("time_range") == {"date_field": "Date", "start_date": "2025-05-01",
                                "end_date": "2025-05-31", "mode": "explicit_range", "grain": "month"}
                            owners = plan.get("dimension_tables") or {}
                            success &= owners.get("Date") == "Date" and owners.get("Region") == "Region"
                            if case != "initial":
                                success &= owners.get("Product") == "Product"
                        if case == "report_to_data":
                            success &= plan.get("measures") == ["Total Orders"] and plan.get("dimensions") == []
                            success &= plan.get("filters") == [] and plan.get("time_range") is None and not report
                        success &= plan.get("requested_template") is None
                    if label in {"report", "data_to_report"}:
                        success &= (body.get("intent") == "report_generation" and body.get("response_type") == "report"
                            and bool(body.get("memory_commit")) and bool(report.get("report_id"))
                            and report.get("template_key") == "sales_report" and bool(report.get("html"))
                            and audit.get("source_mode") == "real" and len(witnesses) > witness_count_before
                            and report.get("content_hash") == hashlib.sha256(report["html"].encode("utf-8")).hexdigest())
                    if label == "data_to_report_missing":
                        success &= not report and body.get("tool_sequence") == [] and len(witnesses) == witness_count_before
                    witness = witnesses.get(audit.get("result_id"))
                    if shape and not blocked:
                        success &= bool(plan and witness)
                    if plan and witness:
                        canonical = CanonicalQueryPlan.model_validate(plan)
                        facts = VerifiedFactSetBuilder().build(canonical, witness["result"])
                        witness.update(user_text=text, candidate_evidence=selections.get(request_id, []), canonical_plan=plan, facts=facts)
                        success &= facts.fact_set_id == audit.get("verified_fact_set_id")
                        success &= canonical.semantic_model_key == witness["result"].semantic_model_key == model_key
                        success &= audit.get("llm_dax_call_count") == 0 and bool(audit.get("layer3_pass"))
                        memory = await service.pipeline.get_latest_committed_memory(conversation, RuntimeDataMode.REAL)
                        success &= memory is not None and memory.semantic_model_key == model_key
                        success &= memory is not None and memory.measures == canonical.measures and memory.dimensions == canonical.dimensions
                        success &= memory is not None and memory.last_query_result_id == witness["result"].result_id
                    summary = {"case": label, "user_text": text, "profile": profile, "pass": bool(success),
                        "provider_failures": provider_failures.get(request_id, []),
                        "http": response.status_code, "terminal": body.get("terminal_state"), "error": body.get("error_type"),
                        "plan": plan, "clarification": body.get("clarification_question"),
                        "objects": audit.get("object_grounding_status"), "selections": [{"role": x["role"], "phrase": x["phrase"], "status": x["status"], "selected_id": x["selected_id"]} for x in selections.get(request_id, [])],
                        "members": audit.get("member_grounding_status"),
                        "member_evidence": [entry for entry in member_selections if entry["request_id"] == request_id],
                        "latency_ms": round((time.perf_counter()-started)*1000, 2), "performance": {
                            "total_turn_ms": (audit.get("performance") or {}).get("total_turn_ms"),
                            "session_reuse_rate": (audit.get("performance") or {}).get("session_reuse_rate"),
                            "stages": {name: sum(op["duration_ms"] for op in (audit.get("performance") or {}).get("operations", []) if op["operation"] == name)
                                for name in ("intent_llm", "query_plan", "grounding", "schema_read", "model_semantic_context_build", "semantic_catalog_build", "dax_execution")}}}
                    if witness and "facts" in witness:
                        summary.update(dax_hash=digest(witness["dax"]), result_hash=digest(witness["result"].rows),
                            fact_count=len(witness["facts"].facts), verified_facts_match=True)
                    summaries.append(summary)
                    if args.candidate_evidence:
                        summary["candidate_evidence"] = selections.get(request_id, [])
                    if args.witness_evidence and witness and "facts" in witness:
                        summary["execution_witness"] = {"dax": witness["dax"],
                            "query_result": witness["result"].model_dump(mode="json", include={
                                "semantic_model_key", "columns", "rows", "row_count", "source_mode",
                                "result_id", "request_id"}),
                            "verified_fact_set": witness["facts"].model_dump(mode="json")}
                    print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)
                    return body, plan

                cases = [
                    ("sales", "总销售额是多少", "scalar"), ("orders", "总订单数是多少", "scalar"),
                    ("entities", "我们销售了哪些产品？", "entity_list"), ("grouped", "各地区销售额", "grouped"),
                    ("top1", "销量最高的是哪款产品？", "ranking"), ("top3", "销售额最高的Top3产品", "ranking"),
                    ("trend", "每个月销售额趋势", "trend"), ("bounded", "2025年8月到2026年1月销售额月趋势", "bounded_trend"),
                    ("south", "华南销售额", "scalar"),
                    ("synonym", "销售收入合计是多少", "scalar"),
                    ("english", "What is the total sales amount?", "scalar"),
                    ("member_set", "华南和华北销售额分别是多少", "member_set"),
                    ("combined", "华南和华北销售额加起来多少", "filtered_aggregation"),
                    ("quantity", "总销量是多少", "scalar"),
                    ("category", "各品类销售额", "grouped"),
                ]
                if args.phase == "focused":
                    profiles = [args.profile, "kimi-k2.6"] if args.compare_profiles else [args.profile]
                    for profile in profiles:
                        for case in cases:
                            if not args.case or case[0] in args.case:
                                await post(*case, profile=profile)
                        for label, text in [
                            ("unknown", "火星区销售额"),
                            ("mixed_unknown", "华南和火星区销售额分别是多少"),
                            ("ambiguous", "哪些产品卖得最好？"),
                            ("compound_region", "东北区域销售额"),
                            ("unproved_place", "上海销售额"),
                        ]:
                            if not args.case or label in args.case:
                                await post(label, text, blocked=True, profile=profile)
                    if args.compare_profiles:
                        for case in {row["case"] for row in summaries}:
                            pair = [row for row in summaries if row["case"] == case]
                            plans = [{k:v for k,v in row["plan"].items() if k not in {"normalized_question", "inherited_context"}}
                                for row in pair]
                            identical = len(pair) == 2 and plans[0] == plans[1] and pair[0].get("result_hash") == pair[1].get("result_hash")
                            print(json.dumps({"provider_consistency": case, "pass": identical}), flush=True)
                            if not identical:
                                for row in pair:
                                    row["pass"] = False
                elif args.phase == "isolation":
                    others = [item for item in options if item["display_name"] == "PowerBIAgent_M3_Test"]
                    if len(others) != 1 or others[0]["key"] == key:
                        raise RuntimeError("second_explicit_pbix_required")
                    other = others[0]["key"]
                    for label, question, shape, measure, dimension in [
                        ("simple_scalar", "总销售额是多少", "scalar", "Total Sales", None),
                        ("simple_entities", "我们销售了哪些产品？", "entity_list", None, "Product"),
                        ("simple_grouped", "各品类销售额", "grouped", "Total Sales", "Category"),
                        ("simple_top1", "销量最高的是哪款产品？", "ranking", "Total Quantity", "Product")]:
                        _, plan = await post(label, question, shape, model_key=other)
                        summaries[-1]["pass"] &= plan.get("measures") == ([measure] if measure else [])
                        summaries[-1]["pass"] &= plan.get("dimensions") == ([dimension] if dimension else [])
                        if dimension:
                            summaries[-1]["pass"] &= (plan.get("dimension_tables") or {}).get(dimension) == "Sales"
                    await post("simple_missing_date", "每月销售额趋势", model_key=other, blocked=True)
                    conversation = str(uuid.uuid4())
                    await post("a_orders", "总订单数是多少", "scalar", conversation=conversation)
                    _, b = await post("b_quantity", "总销量是多少", "scalar", model_key=other, conversation=conversation)
                    summaries[-1]["pass"] &= b.get("measures") == ["Total Quantity"] and not b.get("filters")
                    await post("b_missing_a_metric", "总订单数是多少", model_key=other, conversation=conversation, blocked=True)
                    _, a = await post("back_a_orders", "总订单数是多少", "scalar", conversation=conversation)
                    summaries[-1]["pass"] &= a.get("measures") == ["Total Orders"] and not a.get("dimensions")
                    members = {}
                    for model in (key, other):
                        context = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL, user=UserContext(allowed_semantic_models=[model]))
                        snapshot = await service.tool_gateway.execute("get_column_members", context,
                            ColumnMembersRequest(semantic_model_key=model, table_name="Sales", field_name="Product", limit=100))
                        assert not snapshot.truncated and snapshot.semantic_model_key == model
                        members[model] = set(snapshot.values)
                    a_only, b_only = members[key] - members[other], members[other] - members[key]
                    assert a_only and b_only
                    a_value, b_value = min(a_only), min(b_only)
                    conversation = str(uuid.uuid4())
                    a_question = f"Sales[Product]等于{json.dumps(a_value, ensure_ascii=False)}时总销量是多少"
                    b_question = f"Sales[Product]等于{json.dumps(b_value, ensure_ascii=False)}时总销售额是多少"
                    _, a = await post("a_member", a_question, "scalar", conversation=conversation)
                    summaries[-1]["pass"] &= a.get("filters") == [{"field": "Product", "operator": "eq", "value": a_value}]
                    _, b = await post("b_member", b_question, "scalar", model_key=other, conversation=conversation)
                    summaries[-1]["pass"] &= b.get("filters") == [{"field": "Product", "operator": "eq", "value": b_value}]
                    before = await service.pipeline.get_latest_committed_memory(conversation, RuntimeDataMode.REAL)
                    await post("foreign_member", a_question, model_key=other, conversation=conversation, blocked=True)
                    after = await service.pipeline.get_latest_committed_memory(conversation, RuntimeDataMode.REAL)
                    summaries[-1]["pass"] &= before == after
                    _, a = await post("back_a_member", a_question, "scalar", conversation=conversation)
                    summaries[-1]["pass"] &= a.get("filters") == [{"field": "Product", "operator": "eq", "value": a_value}]
                elif args.phase == "performance":
                    for index in range(2):
                        for label, text, shape in cases[:4]:
                            await post(f"{'first' if index == 0 else 'warm'}_{label}", text, shape)
                    started = time.perf_counter()
                    await asyncio.gather(*(post(f"concurrent_{label}", text, shape) for label, text, shape in cases[:4]))
                    print(json.dumps({"four_way_wall_ms": round((time.perf_counter()-started)*1000, 2),
                        "metadata_bootstrap_ms": bootstrap_ms,
                        "cold_journey_ms": round(bootstrap_ms + summaries[0]["latency_ms"], 2),
                        "note": "first turns follow discovery/schema; cold journey includes that bootstrap; no factual result cache"}), flush=True)
                else:
                    conversation = str(uuid.uuid4())
                    for label, text, shape in [("initial", "2025年5月华南销售额", "scalar"), ("keep", "改成按产品看", "grouped"), ("replace", "那销量呢", "grouped")]:
                        await post(label, text, shape, conversation=conversation)
                    before = await service.pipeline.get_latest_committed_memory(conversation, RuntimeDataMode.REAL)
                    await post("unknown_follow", "火星区销售额", conversation=conversation, blocked=True)
                    after = await service.pipeline.get_latest_committed_memory(conversation, RuntimeDataMode.REAL)
                    summaries[-1]["pass"] &= before == after
                    report_conversation = str(uuid.uuid4())
                    await post("report", "生成销售报表", conversation=report_conversation, template="sales_report")
                    await post("report_to_data", "总订单数是多少", "scalar", conversation=report_conversation, template="sales_report")
                    await post("data_to_report_missing", "生成销售报表", conversation=report_conversation, blocked=True)
                    await post("data_to_report", "生成销售报表", conversation=report_conversation, template="sales_report")
            print(json.dumps({"cases": len(summaries), "passed": sum(x["pass"] for x in summaries),
                "failed_cases": [x["case"] for x in summaries if not x["pass"]],
                "zero_override": True, "execution_witnesses": len(witnesses), "business_residual": 0}), flush=True)
            if not all(item["pass"] for item in summaries):
                raise RuntimeError("cross_language_real_acceptance_failed")
    finally:
        BoundedLLMObjectSelector.select = original_select
        BoundedLLMObjectSelector.select_member = original_member_select
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=30)


def main():
    # Preserve Chinese evidence under Windows redirected stdout as well.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--profile", default="deepseek")
    parser.add_argument("--phase", choices=("inspect", "focused", "extended", "performance", "browser", "isolation"), default="focused")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--case", action="append", help="Run selected focused cases while diagnosing a failure")
    parser.add_argument("--compare-profiles", action="store_true")
    parser.add_argument("--candidate-evidence", action="store_true", help="Print bounded runtime metadata for diagnosis; never prompts or secrets")
    parser.add_argument("--witness-evidence", action="store_true", help="Print validated DAX/result/fact witnesses to the console only; never commit business output")
    args = parser.parse_args()
    with owned_acceptance_tempdir(prefix="powerbiagent-context-real-") as root:
        provider_failures = {}
        with observe_provider_failures(provider_failures):
            asyncio.run(run(args, root, provider_failures))


if __name__ == "__main__":
    main()
