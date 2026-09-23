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
import math
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
from scripts.manual_smoke.m5_10_6_real_language_stress_cases import (
    CASES as M5106_STRESS_CASES,
    CATEGORY_COUNTS as M5106_STRESS_CATEGORY_COUNTS,
    FOCUSED_EXPLAIN_CASES as M5106_FOCUSED_EXPLAIN_CASES,
)

ACCEPTANCE_REQUEST = ContextVar("cross_language_acceptance_request", default=None)


@contextmanager
def observe_provider_failures(
    failures, timings=None, *, provider_type=OpenAICompatibleLLMProvider
):
    """Observe safe categories before weak-draft services handle exceptions."""
    timings = timings if timings is not None else {}
    original = provider_type.generate
    original_once = getattr(provider_type, "_generate_once", None)

    async def generate_once(self, request, output_type):
        started = time.perf_counter()
        outcome = "success"
        failure_category = None
        failure_code = None
        try:
            return await original_once(self, request, output_type)
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except LLMProviderError as error:
            outcome = "provider_error"
            failure_category = error.error_category.value
            failure_code = error.error_code
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            timing = {
                "kind": "provider_attempt",
                "task": request.task.value,
                "outcome": outcome,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            if failure_category is not None:
                timing["failure_category"] = failure_category
            if failure_code in {
                "connect_timeout", "read_timeout", "pool_timeout",
                "write_timeout", "request_deadline_timeout",
            }:
                timing["failure_code"] = failure_code
            timings.setdefault(ACCEPTANCE_REQUEST.get(), []).append(timing)

    async def generate(self, request, output_type):
        started = time.perf_counter()
        outcome = "success"
        try:
            response = await original(self, request, output_type)
            if request.task.value in {"intent_recognition", "query_plan"}:
                for failure in failures.get(ACCEPTANCE_REQUEST.get(), []):
                    if failure["task"] == request.task.value and failure["category"] == "response_validation":
                        failure["repaired"] = True
            return response
        except LLMProviderError as error:
            outcome = "provider_error"
            failure = {"task": request.task.value, "category": error.error_category.value}
            if error.error_code in {"invalid_content_json", "output_schema_invalid", "empty_content",
                    "connect_timeout", "read_timeout", "pool_timeout", "write_timeout",
                    "request_deadline_timeout",
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
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            timings.setdefault(ACCEPTANCE_REQUEST.get(), []).append({
                "kind": "provider_call",
                "task": request.task.value,
                "outcome": outcome,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            })

    if original_once is not None:
        provider_type._generate_once = generate_once
    provider_type.generate = generate
    try:
        yield
    finally:
        provider_type.generate = original
        if original_once is not None:
            provider_type._generate_once = original_once


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


def check(condition, label):
    if not condition:
        raise RuntimeError(label)


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


async def run(args, root, provider_failures, provider_timings):
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
    service = None
    witnesses, selections, summaries = {}, {}, []
    tool_timings = {}
    original_select = BoundedLLMObjectSelector.select
    original_member_select = BoundedLLMObjectSelector.select_member
    original_tool_execute = None
    member_selections = []

    async def observe_selection(self, phrase, user_input, candidates, committed_context="", **kwargs):
        result = await original_select(self, phrase, user_input, candidates, committed_context, **kwargs)
        selections.setdefault(ACCEPTANCE_REQUEST.get(), []).append({"role": kwargs.get("role"), "phrase": phrase,
            "candidate_evidence": kwargs.get("evidence"), "status": result.status.value,
            "selected_id": result.canonical_object.object_id if result.canonical_object else None,
            "candidate_ids": list(result.candidate_ids), "method": result.method})
        return result

    BoundedLLMObjectSelector.select = observe_selection
    async def observe_member(self, requested_value, field, members, **kwargs):
        result = await original_member_select(self, requested_value, field, members, **kwargs)
        member_selections.append({"request_id": ACCEPTANCE_REQUEST.get(), "user_input": kwargs.get("user_input"), "requested": requested_value,
            "field_id": field.object_id, "candidate_values": members.values,
            "truncated": members.truncated, "status": result.status.value, "method": result.method})
        return result
    BoundedLLMObjectSelector.select_member = observe_member

    async def observe_tool_execute(
        tool_name, execution_context, input_data, trace=None, controller=None
    ):
        request_id = ACCEPTANCE_REQUEST.get()
        started = time.perf_counter()
        outcome = "success"
        try:
            return await original_tool_execute(
                tool_name,
                execution_context,
                input_data,
                trace=trace,
                controller=controller,
            )
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            if request_id is not None:
                tool_timings.setdefault(request_id, []).append({
                    "tool": tool_name,
                    "outcome": outcome,
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                })

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
        service = app.state.turn_service
        original_tool_execute = service.tool_gateway.execute
        service.tool_gateway.execute = observe_tool_execute
        # Local acceptance traffic must not take the machine's external proxy.
        # The longer observer deadline lets production's own LLM timeouts finish;
        # it does not change provider timeouts or retry failed semantic choices.
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{args.port}", timeout=600, trust_env=False) as client:
            reply = await client.get("/api/v1/semantic-models")
            options = [item for item in reply.json()["items"] if item.get("selectable")]
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

                async def post(label, text, shape=None, *, conversation=None, model_key=key, profile=args.profile, template=None, blocked=False, allow_unsupported=False):
                    if args.phase in {"m585", "m5104"} and args.case and label not in args.case:
                        return {}, {}
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
                    expected_terminal = "clarification_required" if blocked else "completed"
                    success = response.status_code == 200 and (
                        body.get("terminal_state") == expected_terminal
                        or (
                            allow_unsupported
                            and body.get("terminal_state") == "unsupported"
                        )
                    )
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
                    summary = {"case": label, "user_text": text, "profile": profile,
                        "semantic_model": next((item["display_name"] for item in options if item["key"] == model_key), model_key),
                        "pass": bool(success),
                        "provider_failures": provider_failures.get(request_id, []),
                        "provider_timings": provider_timings.get(request_id, []),
                        "tool_timings": tool_timings.get(request_id, []),
                        "http": response.status_code, "terminal": body.get("terminal_state"), "error": body.get("error_type"),
                        "plan": plan, "clarification": body.get("clarification_question"),
                        "obligations": audit.get("semantic_obligations"),
                        "obligation_coverage": audit.get("semantic_obligation_coverage"),
                        "shape_reconciliation": audit.get("query_shape_reconciliation"),
                        "grounded_delta": audit.get("grounded_delta"),
                        "inheritance": audit.get("inheritance_decision"),
                        "dax_executed": bool(audit.get("dax_executed")),
                        "result_shape": {"row_count": audit.get("result_row_count"),
                            "inspection": audit.get("result_semantic_inspection")},
                        "effective_scope": audit.get("effective_query_scope"),
                        "requested_query_scope": audit.get("requested_query_scope"),
                        "canonical_query_scope": audit.get("canonical_query_scope"),
                        "observed_data_coverage": audit.get("observed_data_coverage"),
                        "objects": audit.get("object_grounding_status"), "selections": [{"role": x["role"], "phrase": x["phrase"], "status": x["status"], "selected_id": x["selected_id"]} for x in selections.get(request_id, [])],
                        "members": audit.get("member_grounding_status"),
                        "member_evidence": [entry for entry in member_selections if entry["request_id"] == request_id],
                        "latency_ms": round((time.perf_counter()-started)*1000, 2),
                        "llm_call_count": sum(
                            item.get("kind") == "provider_call"
                            for item in provider_timings.get(request_id, [])
                        ),
                        "reported_usage_call_count": int(
                            (body.get("usage") or {}).get("call_count") or 0
                        ),
                        "max_single_llm_ms": max(
                            (
                                item["duration_ms"]
                                for item in provider_timings.get(request_id, [])
                                if item.get("kind") == "provider_attempt"
                            ),
                            default=0,
                        ),
                        "max_logical_llm_call_ms": max(
                            (
                                item["duration_ms"]
                                for item in provider_timings.get(request_id, [])
                                if item.get("kind") == "provider_call"
                            ),
                            default=0,
                        ),
                        "tool_call_count": len(body.get("tool_sequence") or []),
                        "performance": {
                            "total_turn_ms": (audit.get("performance") or {}).get("total_turn_ms"),
                            "session_reuse_rate": (audit.get("performance") or {}).get("session_reuse_rate"),
                            "stages": {name: sum(op["duration_ms"] for op in (audit.get("performance") or {}).get("operations", []) if op["operation"] == name)
                                for name in ("intent_llm", "query_plan", "grounding", "schema_read", "model_semantic_context_build", "semantic_catalog_build", "dax_execution")}}}
                    if witness and "facts" in witness:
                        summary.update(dax_hash=digest(witness["dax"]), result_hash=digest(witness["result"].rows),
                            fact_count=len(witness["facts"].facts), verified_facts_match=True)
                    if args.phase == "m585":
                        presentation = body.get("presentation") or {}
                        datasets = presentation.get("datasets") or []
                        blocks = presentation.get("blocks") or []
                        data_references = {
                            block.get("data_reference") for block in blocks
                            if block.get("type") in {"table", "chart"}
                        }
                        dataset_rows = datasets[0].get("rows") if len(datasets) == 1 else None
                        result_rows = (
                            witness["result"].model_dump(mode="json").get("rows")
                            if witness else None
                        )
                        display_metric_desc = None
                        if (
                            plan.get("query_shape") == "grouped"
                            and not plan.get("sort")
                            and len(plan.get("measures") or []) == 1
                            and len(datasets) == 1
                        ):
                            columns = datasets[0].get("columns") or []
                            measure = plan["measures"][0]
                            indexes = [
                                index for index, column in enumerate(columns)
                                if column == measure or column.endswith(f"[{measure}]")
                            ]
                            if len(indexes) == 1:
                                values = [row[indexes[0]] for row in (dataset_rows or [])]
                                display_metric_desc = all(
                                    left >= right for left, right in zip(values, values[1:])
                                )
                        summary.update(
                            final_answer=body.get("answer"),
                            presentation_order={
                                "shared_table_chart_dataset": len(data_references) <= 1,
                                "matches_query_result": (
                                    dataset_rows == result_rows
                                    if dataset_rows is not None and result_rows is not None
                                    else None
                                ),
                                "grouped_default_metric_desc": display_metric_desc,
                            },
                        )
                    summaries.append(summary)
                    if args.candidate_evidence:
                        summary["candidate_evidence"] = selections.get(request_id, [])
                    if args.witness_evidence and witness and "facts" in witness:
                        summary["execution_witness"] = {"dax": witness["dax"],
                            "query_result": witness["result"].model_dump(mode="json", include={
                                "semantic_model_key", "columns", "rows", "row_count", "source_mode",
                                "result_id", "request_id"}),
                            "verified_fact_set": witness["facts"].model_dump(mode="json")}
                    emitted = summary
                    if args.phase in {"m5106", "m5106stress"}:
                        emitted = {
                            "case": label,
                            "pass": bool(summary["pass"]),
                            "http": response.status_code,
                            "terminal": body.get("terminal_state"),
                            "response_type": body.get("response_type"),
                            "query_shape": plan.get("query_shape"),
                            "dax_executed": bool(audit.get("dax_executed")),
                            "memory_commit": bool(body.get("memory_commit")),
                            "deterministic_dax": audit.get("deterministic_dax"),
                            "llm_dax_call_count": audit.get("llm_dax_call_count"),
                            "factual_validation_pass": audit.get(
                                "factual_validation_pass"
                            ),
                            "semantic_error_code": audit.get(
                                "semantic_interpretation_error_code"
                            ),
                            "error_type": body.get("error_type"),
                            "answer_validation_errors": audit.get(
                                "answer_validation_errors"
                            ),
                            "semantic_frame": audit.get("semantic_frame"),
                            "grounded_delta": audit.get("grounded_delta"),
                            "inheritance": audit.get("inheritance_decision"),
                            "clarification_reason": audit.get(
                                "clarification_reason"
                            ),
                            "object_statuses": [
                                {
                                    "role": item.get("role"),
                                    "status": item.get("status"),
                                    "method": item.get("method"),
                                }
                                for item in (
                                    audit.get("object_grounding_status") or []
                                )
                            ],
                            "member_statuses": [
                                {
                                    "status": item.get("status"),
                                    "method": item.get("method"),
                                }
                                for item in (
                                    audit.get("member_grounding_status") or []
                                )
                            ],
                            "provider_failures": provider_failures.get(
                                request_id, []
                            ),
                            "latency_ms": summary["latency_ms"],
                            "llm_call_count": summary["llm_call_count"],
                            "max_single_llm_ms": summary["max_single_llm_ms"],
                            "max_logical_llm_call_ms": summary[
                                "max_logical_llm_call_ms"
                            ],
                            "tool_call_count": summary["tool_call_count"],
                        }
                        if args.candidate_evidence:
                            emitted["candidate_evidence"] = summary.get(
                                "candidate_evidence", []
                            )
                    if not (
                        args.phase == "m5106stress" and args.stress_summary_only
                    ):
                        print(
                            json.dumps(emitted, ensure_ascii=False, default=str),
                            flush=True,
                        )
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
                elif args.phase == "m585":
                    by_name = {item["display_name"]: item["key"] for item in options}
                    required_models = {
                        "rich": "PowerBIAgent_M3_Rich_Test",
                        "simple": "PowerBIAgent_M3_Test",
                        "logistics": "PowerBIAgent_M5_8_5_Logistics_Test",
                    }
                    if any(name not in by_name for name in required_models.values()):
                        raise RuntimeError("m585_three_explicit_pbix_required")
                    model_keys = {
                        alias: by_name[name] for alias, name in required_models.items()
                    }

                    async def members(model_alias, table, field):
                        model_key = model_keys[model_alias]
                        context = ToolExecutionContext(
                            runtime_mode=RuntimeDataMode.REAL,
                            user=UserContext(allowed_semantic_models=[model_key]),
                        )
                        snapshot = await service.tool_gateway.execute(
                            "get_column_members",
                            context,
                            ColumnMembersRequest(
                                semantic_model_key=model_key,
                                table_name=table,
                                field_name=field,
                                limit=200,
                            ),
                        )
                        check(
                            snapshot.semantic_model_key == model_key
                            and not snapshot.truncated
                            and snapshot.values,
                            f"{model_alias}_{field}_member_snapshot_invalid",
                        )
                        return [str(value) for value in snapshot.values]

                    rich_regions = await members("rich", "Region", "Region")
                    rich_products = await members("rich", "Product", "Product")
                    simple_products = await members("simple", "Sales", "Product")
                    logistics_hubs = await members("logistics", "DimHub", "HubName")
                    logistics_carriers = await members("logistics", "DimCarrier", "CarrierName")
                    check(len(rich_regions) >= 2 and len(rich_products) >= 2, "rich_members_insufficient")
                    check(len(simple_products) >= 2, "simple_members_insufficient")
                    check(len(logistics_hubs) >= 2 and len(logistics_carriers) >= 2, "logistics_members_insufficient")

                    async def completed_case(label, text, shape, *, model_alias, profile, conversation=None):
                        summary_count = len(summaries)
                        body, plan = await post(
                            label,
                            text,
                            shape,
                            model_key=model_keys[model_alias],
                            profile=profile,
                            conversation=conversation,
                        )
                        if len(summaries) == summary_count:
                            return body, plan
                        item = summaries[-1]
                        inspection = item["result_shape"].get("inspection") or {}
                        scope = item.get("effective_scope")
                        item["pass"] &= bool(
                            item.get("obligation_coverage") is True
                            and item.get("grounded_delta") is not None
                            and inspection.get("passed") is True
                            and scope
                            and scope in (body.get("answer") or "")
                            and item["presentation_order"]["shared_table_chart_dataset"]
                        )
                        if shape in {"ranking", "trend", "bounded_trend"}:
                            item["pass"] &= item["presentation_order"]["matches_query_result"] is True
                        if shape == "grouped" and not plan.get("sort"):
                            item["pass"] &= item["presentation_order"]["grouped_default_metric_desc"] is True
                        return body, plan

                    async def blocked_case(label, text, *, model_alias, profile, conversation=None):
                        summary_count = len(summaries)
                        body, plan = await post(
                            label,
                            text,
                            model_key=model_keys[model_alias],
                            profile=profile,
                            conversation=conversation,
                            blocked=True,
                        )
                        if len(summaries) == summary_count:
                            return body, plan
                        item = summaries[-1]
                        item["pass"] &= bool(
                            not item["dax_executed"]
                            and item["result_shape"]["row_count"] is None
                            and not body.get("memory_commit")
                        )
                        return body, plan

                    def mark(plan, condition):
                        if plan:
                            summaries[-1]["pass"] &= bool(condition)

                    profiles = (
                        (args.profile,)
                        if args.m585_single_profile
                        else tuple(dict.fromkeys((args.profile, "kimi-k2.6")))
                    )
                    for profile in profiles:
                        rich = model_keys["rich"]
                        rich_chain = str(uuid.uuid4())
                        await completed_case("rich_time_scalar", "2025年5月销售额是多少？", "scalar", model_alias="rich", profile=profile, conversation=rich_chain)
                        await completed_case("rich_filter_followup", f"那 {rich_regions[0]} 呢？", "scalar", model_alias="rich", profile=profile, conversation=rich_chain)
                        await completed_case("rich_measure_replace", "换成销量", "scalar", model_alias="rich", profile=profile, conversation=rich_chain)
                        await completed_case("rich_grouped", "按产品看", "grouped", model_alias="rich", profile=profile, conversation=rich_chain)
                        _, rich_top1 = await completed_case("rich_top1", "销量最高的是哪个产品？", "ranking", model_alias="rich", profile=profile)
                        mark(rich_top1, rich_top1.get("top_n") == 1 and rich_top1.get("sort") == "desc")
                        _, rich_top3 = await completed_case("rich_top3", "销售额最高的前三个产品", "ranking", model_alias="rich", profile=profile)
                        mark(rich_top3, rich_top3.get("top_n") == 3 and rich_top3.get("sort") == "desc")
                        await completed_case("rich_trend", "每个月销售额趋势", "trend", model_alias="rich", profile=profile)
                        await completed_case("rich_bounded", "2025年8月到2026年1月销售额月趋势", "bounded_trend", model_alias="rich", profile=profile)
                        await completed_case("rich_entities", "有哪些产品？", "entity_list", model_alias="rich", profile=profile)
                        rich_set = " 和 ".join(rich_regions[:2])
                        await completed_case("rich_member_set", f"{rich_set} 的销售额分别是多少？", "member_set", model_alias="rich", profile=profile)
                        await completed_case("rich_known_member", f"{rich_regions[0]} 的销售额是多少？", "scalar", model_alias="rich", profile=profile)
                        await blocked_case("rich_unknown", "地球销售额多少？", model_alias="rich", profile=profile)
                        await blocked_case("rich_mixed_unknown", f"{rich_regions[0]} 和火星区的销售额", model_alias="rich", profile=profile)
                        rich_fresh = str(uuid.uuid4())
                        await blocked_case("rich_pending", "哪个产品最好？", model_alias="rich", profile=profile, conversation=rich_fresh)
                        _, fresh_plan = await completed_case("rich_fresh", "独立问题：总订单数是多少？", "scalar", model_alias="rich", profile=profile, conversation=rich_fresh)
                        mark(fresh_plan, not fresh_plan.get("dimensions") and not fresh_plan.get("filters") and fresh_plan.get("top_n") is None)

                        report_conversation = str(uuid.uuid4())
                        await post("report", "生成销售报表", model_key=rich, profile=profile,
                            conversation=report_conversation, template="sales_report")
                        await completed_case("report_to_data", "总订单数是多少", "scalar", model_alias="rich", profile=profile, conversation=report_conversation)
                        await post("data_to_report", "生成销售报表", model_key=rich, profile=profile,
                            conversation=report_conversation, template="sales_report")

                        await completed_case("simple_scalar", "总销售额是多少？", "scalar", model_alias="simple", profile=profile)
                        await completed_case("simple_grouped", "按产品看销售额", "grouped", model_alias="simple", profile=profile)
                        _, simple_top1 = await completed_case("simple_top1", "销量最高的是哪个产品？", "ranking", model_alias="simple", profile=profile)
                        mark(simple_top1, simple_top1.get("top_n") == 1)
                        _, simple_top3 = await completed_case("simple_top3", "销售额最高的前三个产品", "ranking", model_alias="simple", profile=profile)
                        mark(simple_top3, simple_top3.get("top_n") == 3)
                        await completed_case("simple_entities", "有哪些产品？", "entity_list", model_alias="simple", profile=profile)
                        simple_set = " 和 ".join(simple_products[:2])
                        await completed_case("simple_member_set", f"{simple_set} 的销售额分别是多少？", "member_set", model_alias="simple", profile=profile)
                        await blocked_case("simple_unknown", "地球销售额多少？", model_alias="simple", profile=profile)
                        await blocked_case("simple_mixed_unknown", f"{simple_products[0]} 和火星产品的销售额", model_alias="simple", profile=profile)
                        await blocked_case("simple_temporal_unsupported", "2025年5月销售额", model_alias="simple", profile=profile)
                        simple_fresh = str(uuid.uuid4())
                        await completed_case("simple_seed", "按产品看销售额", "grouped", model_alias="simple", profile=profile, conversation=simple_fresh)
                        _, simple_fresh_plan = await completed_case("simple_fresh", "新问题：总销量是多少？", "scalar", model_alias="simple", profile=profile, conversation=simple_fresh)
                        mark(simple_fresh_plan, not simple_fresh_plan.get("dimensions") and not simple_fresh_plan.get("filters"))

                        logistics_chain = str(uuid.uuid4())
                        _, logistics_initial = await completed_case("logistics_time_scalar", "2025年5月总运单数是多少？", "scalar", model_alias="logistics", profile=profile, conversation=logistics_chain)
                        mark(logistics_initial, logistics_initial.get("measures") == ["Total Shipments"])
                        _, logistics_filtered = await completed_case("logistics_filter_followup", "那 North Hub 呢？", "scalar", model_alias="logistics", profile=profile, conversation=logistics_chain)
                        mark(logistics_filtered, logistics_filtered.get("filters") == [{"field": "HubName", "operator": "eq", "value": "North Hub"}])
                        _, logistics_replace = await completed_case("logistics_measure_replace", "换成包裹数", "scalar", model_alias="logistics", profile=profile, conversation=logistics_chain)
                        mark(logistics_replace, logistics_replace.get("measures") == ["Total Packages"])
                        _, logistics_grouped = await completed_case("logistics_grouped", "按承运商看", "grouped", model_alias="logistics", profile=profile, conversation=logistics_chain)
                        mark(logistics_grouped, logistics_grouped.get("dimensions") == ["CarrierName"])
                        _, logistics_top1 = await completed_case("logistics_top1", "包裹数最高的是哪个承运商？", "ranking", model_alias="logistics", profile=profile)
                        mark(logistics_top1, logistics_top1.get("measures") == ["Total Packages"] and logistics_top1.get("dimensions") == ["CarrierName"] and logistics_top1.get("top_n") == 1)
                        _, logistics_top3 = await completed_case("logistics_top3", "包裹数最高的前三个承运商", "ranking", model_alias="logistics", profile=profile)
                        mark(logistics_top3, logistics_top3.get("top_n") == 3)
                        await completed_case("logistics_trend", "每个月运单趋势", "trend", model_alias="logistics", profile=profile)
                        await completed_case("logistics_bounded", "2025年8月到2026年1月运单月趋势", "bounded_trend", model_alias="logistics", profile=profile)
                        await completed_case("logistics_entities", "有哪些承运商？", "entity_list", model_alias="logistics", profile=profile)
                        logistics_set = " 和 ".join(logistics_hubs[:2])
                        await completed_case("logistics_member_set", f"{logistics_set} 的包裹数分别是多少？", "member_set", model_alias="logistics", profile=profile)
                        await completed_case("logistics_known_member", "North Hub 的运单数多少？", "scalar", model_alias="logistics", profile=profile)
                        await blocked_case("logistics_unknown", "地球枢纽运单数多少？", model_alias="logistics", profile=profile)
                        await blocked_case("logistics_mixed_unknown", "North Hub 和火星枢纽的包裹数", model_alias="logistics", profile=profile)
                        _, logistics_fresh = await completed_case("logistics_fresh", "独立问题：2026年1月平均延误小时数", "scalar", model_alias="logistics", profile=profile, conversation=logistics_chain)
                        mark(logistics_fresh, logistics_fresh.get("measures") == ["Average Delay Hours"] and not logistics_fresh.get("filters") and not logistics_fresh.get("dimensions"))
                        _, hub_ontime = await completed_case("logistics_hub_ontime", "哪个枢纽最准时？", "ranking", model_alias="logistics", profile=profile)
                        mark(hub_ontime, hub_ontime.get("measures") == ["On-Time Rate"] and hub_ontime.get("dimensions") == ["HubName"] and hub_ontime.get("sort") == "desc")
                        _, carrier_delay = await completed_case("logistics_carrier_delay", "哪个承运商延误最严重？", "ranking", model_alias="logistics", profile=profile)
                        mark(carrier_delay, carrier_delay.get("measures") == ["Average Delay Hours"] and carrier_delay.get("dimensions") == ["CarrierName"] and carrier_delay.get("sort") == "desc")

                        isolation = str(uuid.uuid4())
                        _, a1 = await completed_case("isolation_a1", "独立问题：总订单数是多少", "scalar", model_alias="rich", profile=profile, conversation=isolation)
                        _, b = await completed_case("isolation_b", "独立问题：总销量是多少", "scalar", model_alias="simple", profile=profile, conversation=isolation)
                        _, c = await completed_case("isolation_c", "独立问题：总运单数是多少", "scalar", model_alias="logistics", profile=profile, conversation=isolation)
                        _, a2 = await completed_case("isolation_a2", "独立问题：总订单数是多少", "scalar", model_alias="rich", profile=profile, conversation=isolation)
                        mark(a2, a1.get("measures") == a2.get("measures") == ["Total Orders"] and b.get("measures") == ["Total Quantity"] and c.get("measures") == ["Total Shipments"])

                    comparable = {}
                    for item in summaries:
                        if item.get("profile") not in profiles or not item.get("result_hash"):
                            continue
                        comparable.setdefault((item["semantic_model"], item["case"]), []).append(item)
                    consistency = []
                    for identity, pair in comparable.items():
                        if len(pair) != len(profiles):
                            continue
                        normalized_plans = [
                            {name: value for name, value in row["plan"].items()
                                if name not in {"normalized_question", "inherited_context"}}
                            for row in pair
                        ]
                        passed = normalized_plans[0] == normalized_plans[1] and pair[0]["result_hash"] == pair[1]["result_hash"]
                        consistency.append({"semantic_model": identity[0], "case": identity[1], "pass": passed})
                        if not passed:
                            for row in pair:
                                row["pass"] = False
                    print(json.dumps({"m585_provider_consistency": consistency,
                        "passed": all(item["pass"] for item in consistency)}, ensure_ascii=False), flush=True)
                elif args.phase == "m5104":
                    by_name = {item["display_name"]: item["key"] for item in options}
                    required_models = {
                        "rich": "PowerBIAgent_M3_Rich_Test",
                        "logistics": "PowerBIAgent_M5_8_5_Logistics_Test",
                    }
                    if any(name not in by_name for name in required_models.values()):
                        raise RuntimeError("m5104_two_explicit_pbix_required")
                    model_keys = {
                        alias: by_name[name] for alias, name in required_models.items()
                    }

                    async def completed_case(
                        label, text, shape, *, model_alias="rich", conversation=None
                    ):
                        body, plan = await post(
                            label,
                            text,
                            shape,
                            model_key=model_keys[model_alias],
                            conversation=conversation,
                        )
                        return body, plan

                    async def blocked_case(
                        label, text, *, model_alias="rich", conversation=None
                    ):
                        return await post(
                            label,
                            text,
                            model_key=model_keys[model_alias],
                            conversation=conversation,
                            blocked=True,
                        )

                    def mark(plan, condition):
                        if plan:
                            summaries[-1]["pass"] &= bool(condition)

                    _, grouped_cn = await completed_case(
                        "m5104_grouped_cn", "各产品销售额是多少？", "grouped"
                    )
                    mark(
                        grouped_cn,
                        grouped_cn.get("measures") == ["Total Sales"]
                        and grouped_cn.get("dimensions") == ["Product"],
                    )
                    for label, text in (
                        ("m5104_ranking_mixed", "Product 按销售额排前三"),
                        ("m5104_ranking_en", "top 3 products by sales"),
                        ("m5104_ranking_word_order", "销售额前三的产品"),
                    ):
                        _, ranking = await completed_case(label, text, "ranking")
                        mark(
                            ranking,
                            ranking.get("measures") == ["Total Sales"]
                            and ranking.get("dimensions") == ["Product"]
                            and ranking.get("sort") == "desc"
                            and ranking.get("top_n") == 3,
                        )
                    _, grouped_en = await completed_case(
                        "m5104_grouped_en", "sales by product", "grouped"
                    )
                    mark(
                        grouped_en,
                        grouped_en.get("measures") == ["Total Sales"]
                        and grouped_en.get("dimensions") == ["Product"],
                    )
                    _, mixed_filter = await completed_case(
                        "m5104_mixed_filter",
                        "华南 region 的 sales",
                        "filtered_aggregation",
                    )
                    mark(
                        mixed_filter,
                        mixed_filter.get("measures") == ["Total Sales"]
                        and mixed_filter.get("filters")
                        == [{"field": "Region", "operator": "eq", "value": "South"}],
                    )

                    await blocked_case(
                        "m5104_measure_ambiguity", "哪三个产品最挣钱"
                    )
                    await blocked_case(
                        "m5104_incomplete_ranking", "销售额按区域排一下"
                    )
                    vague, _ = await blocked_case(
                        "m5104_vague_trend",
                        "最近几个月的运单趋势",
                        model_alias="logistics",
                    )
                    vague_audit = vague.get("execution_audit") or {}
                    summaries[-1]["pass"] &= bool(
                        vague_audit.get("clarification_reason")
                        == "incomplete_time_range"
                        and (
                            vague_audit.get("query_shape_reconciliation") or {}
                        ).get("effective")
                        in {"trend", "bounded_trend"}
                    )
                    for label, text in (
                        (
                            "m5104_logistics_ranking_en",
                            "top 3 carriers by total shipments",
                        ),
                        (
                            "m5104_logistics_ranking_mixed",
                            "承运商 top 3 by Total Shipments",
                        ),
                    ):
                        _, logistics = await completed_case(
                            label, text, "ranking", model_alias="logistics"
                        )
                        mark(
                            logistics,
                            logistics.get("measures") == ["Total Shipments"]
                            and logistics.get("dimensions") == ["CarrierName"]
                            and logistics.get("sort") == "desc"
                            and logistics.get("top_n") == 3,
                        )

                    chain = str(uuid.uuid4())
                    _, seed = await completed_case(
                        "m5104_chain_seed", "总销售额是多少？", "scalar",
                        conversation=chain,
                    )
                    mark(seed, seed.get("measures") == ["Total Sales"])
                    _, richer = await completed_case(
                        "m5104_chain_richer",
                        "那么 Product 按 Total Sales 排前三",
                        "ranking",
                        conversation=chain,
                    )
                    mark(
                        richer,
                        richer.get("measures") == ["Total Sales"]
                        and richer.get("dimensions") == ["Product"]
                        and richer.get("top_n") == 3,
                    )
                    before_unknown = await service.pipeline.get_latest_committed_memory(
                        chain, RuntimeDataMode.REAL
                    )
                    await blocked_case(
                        "m5104_unknown_after_memory", "火星区 sales",
                        conversation=chain,
                    )
                    after_unknown = await service.pipeline.get_latest_committed_memory(
                        chain, RuntimeDataMode.REAL
                    )
                    summaries[-1]["pass"] &= before_unknown == after_unknown

                elif args.phase == "m5105":
                    direct_cases = (
                        ("m5105_greeting", "你好", "social_conversation", 1),
                        ("m5105_joke", "讲个简短的笑话", "social_conversation", 1),
                        ("m5105_warm_greeting", "写一句轻松的问候", "social_conversation", 1),
                        ("m5105_current_date", "今天几号", "system_datetime", 0),
                        ("m5105_current_time", "现在几点", "system_datetime", 0),
                    )
                    for label, text, route, expected_llm_calls in direct_cases:
                        witness_count = len(witnesses)
                        body, _ = await post(label, text)
                        audit = body.get("execution_audit") or {}
                        usage = body.get("usage") or {}
                        summaries[-1]["pass"] &= bool(
                            audit.get("question_route") == route
                            and not audit.get("dax_executed")
                            and not body.get("memory_commit")
                            and body.get("tool_sequence") == []
                            and len(witnesses) == witness_count
                            and usage.get("call_count", 0) == expected_llm_calls
                        )
                        if route == "social_conversation":
                            summaries[-1]["pass"] &= bool(
                                (usage.get("per_task") or {}).get("conversation") == 1
                                and audit.get("schema_read") is False
                                and audit.get("member_lookup") is False
                                and audit.get("pending_semantic_mutation") is False
                                and audit.get("powerbi_tool_calls") == 0
                                and audit.get("report_calls") == 0
                            )
                        if route == "system_datetime":
                            summaries[-1]["pass"] &= "Asia/Shanghai" in (
                                body.get("answer") or ""
                            )

                    escalation, escalation_plan = await post(
                        "m5105_business_escalation",
                        "你好，顺便看一下今年销售额",
                        "scalar",
                    )
                    escalation_audit = escalation.get("execution_audit") or {}
                    summaries[-1]["pass"] &= bool(
                        escalation_audit.get("question_route")
                        == "business_data_query"
                        and escalation_audit.get("dax_executed")
                        and escalation_plan.get("measures") == ["Total Sales"]
                        and escalation_plan.get("time_range")
                    )

                    business_social = str(uuid.uuid4())
                    await post(
                        "m5105_business_before_social",
                        "总销售额是多少",
                        "scalar",
                        conversation=business_social,
                    )
                    memory_before = await service.pipeline.get_latest_committed_memory(
                        business_social, RuntimeDataMode.REAL
                    )
                    witness_count = len(witnesses)
                    social_after, _ = await post(
                        "m5105_social_after_business",
                        "讲个简短的笑话",
                        conversation=business_social,
                    )
                    memory_after = await service.pipeline.get_latest_committed_memory(
                        business_social, RuntimeDataMode.REAL
                    )
                    social_audit = social_after.get("execution_audit") or {}
                    social_usage = social_after.get("usage") or {}
                    summaries[-1]["pass"] &= bool(
                        memory_before == memory_after
                        and not social_after.get("memory_commit")
                        and not social_audit.get("dax_executed")
                        and social_usage.get("call_count") == 1
                        and (social_usage.get("per_task") or {}).get(
                            "conversation"
                        ) == 1
                        and len(witnesses) == witness_count
                    )

                    social_business = str(uuid.uuid4())
                    await post(
                        "m5105_social_before_business",
                        "写一句轻松的问候",
                        conversation=social_business,
                    )
                    business_after, business_after_plan = await post(
                        "m5105_business_after_social",
                        "总销售额是多少",
                        "scalar",
                        conversation=social_business,
                    )
                    summaries[-1]["pass"] &= bool(
                        business_after_plan.get("measures") == ["Total Sales"]
                        and (business_after.get("execution_audit") or {}).get(
                            "dax_executed"
                        )
                        and business_after.get("memory_commit")
                    )

                    async def completed_time_case(
                        label, text, shape, *, conversation=None
                    ):
                        body, plan = await post(
                            label,
                            text,
                            shape,
                            conversation=conversation,
                        )
                        audit = body.get("execution_audit") or {}
                        coverage = audit.get("observed_data_coverage") or {}
                        summaries[-1]["pass"] &= bool(
                            plan.get("measures") == ["Total Sales"]
                            and plan.get("dimensions") == ["YearMonth"]
                            and (plan.get("dimension_tables") or {}).get(
                                "YearMonth"
                            ) == "Date"
                            and plan.get("time_range")
                            and audit.get("requested_query_scope")
                            == audit.get("effective_query_scope")
                            and (audit.get("canonical_query_scope") or {}).get(
                                "requested_time_range"
                            ) == plan.get("time_range")
                            and coverage.get("status")
                            in {"full", "partial", "empty"}
                        )
                        return body, plan

                    await completed_time_case(
                        "m5105_absolute_q4",
                        "2025 Q4 销售额趋势",
                        "trend",
                    )
                    await completed_time_case(
                        "m5105_relative_six_months",
                        "最近6个月销售额趋势",
                        "trend",
                    )

                    pending_conversation = str(uuid.uuid4())
                    witness_count = len(witnesses)
                    vague, _ = await post(
                        "m5105_vague_time",
                        "最近几个月的销售额趋势",
                        conversation=pending_conversation,
                        blocked=True,
                    )
                    vague_audit = vague.get("execution_audit") or {}
                    pending = await service.pipeline.get_pending_clarification(
                        pending_conversation,
                        RuntimeDataMode.REAL,
                    )
                    summaries[-1]["pass"] &= bool(
                        vague_audit.get("clarification_reason")
                        == "incomplete_time_range"
                        and pending is not None
                        and pending.missing_slots == ["time"]
                        and pending.measures == ["Total Sales"]
                        and pending.query_shape is not None
                        and pending.query_shape.value == "trend"
                        and len(witnesses) == witness_count
                    )
                    bounded, bounded_plan = await completed_time_case(
                        "m5105_vague_followup",
                        "最近6个月",
                        "trend",
                        conversation=pending_conversation,
                    )
                    summaries[-1]["pass"] &= bool(
                        (bounded_plan.get("time_range") or {}).get("grain")
                        == "month"
                        and await service.pipeline.get_pending_clarification(
                            pending_conversation,
                            RuntimeDataMode.REAL,
                        )
                        is None
                    )

                    partial, partial_plan = await completed_time_case(
                        "m5105_partial_coverage",
                        "2020年1月到2030年12月销售额趋势",
                        "bounded_trend",
                    )
                    partial_audit = partial.get("execution_audit") or {}
                    coverage = partial_audit.get("observed_data_coverage") or {}
                    summaries[-1]["pass"] &= bool(
                        coverage.get("status") == "partial"
                        and coverage.get("start_date")
                        and coverage.get("end_date")
                        and (partial_audit.get("canonical_query_scope") or {}).get(
                            "requested_time_range"
                        ) == partial_plan.get("time_range")
                        and "实际返回数据覆盖" in (partial.get("answer") or "")
                    )

                    for label, text, shape in (
                        ("m5105_scalar_regression", "总销售额是多少", "scalar"),
                        ("m5105_grouped_regression", "各产品销售额是多少", "grouped"),
                        (
                            "m5105_ranking_regression",
                            "销售额最高的前三个产品",
                            "ranking",
                        ),
                    ):
                        body, plan = await post(label, text, shape)
                        summaries[-1]["pass"] &= bool(
                            plan.get("measures") == ["Total Sales"]
                            and (
                                shape == "scalar"
                                or plan.get("dimensions") == ["Product"]
                            )
                            and (
                                shape != "ranking"
                                or (
                                    plan.get("top_n") == 3
                                    and plan.get("sort") == "desc"
                                )
                            )
                        )

                    report_body, _ = await post(
                        "m5105_time_report",
                        "生成2025年销售经营分析报表",
                        template="sales_executive_report",
                    )
                    report = report_body.get("report") or {}
                    html = report.get("html") or ""
                    report_audit = report_body.get("execution_audit") or {}
                    report_plans = (
                        report_audit.get("canonical_query_plans") or {}
                    )
                    summaries[-1]["pass"] &= bool(
                        report_body.get("intent") == "report_generation"
                        and report_body.get("response_type") == "report"
                        and report_body.get("memory_commit")
                        and report.get("template_key")
                        == "sales_executive_report"
                        and report_plans
                        and all(
                            (item.get("time_range") or {}).get("start_date")
                            == "2025-01-01"
                            and (item.get("time_range") or {}).get("end_date")
                            == "2025-12-31"
                            for item in report_plans.values()
                        )
                        and (
                            report_audit.get("report_analysis_period") or {}
                        ).get("start_date") == "2025-01-01"
                        and (
                            report_audit.get("report_analysis_period") or {}
                        ).get("end_date") == "2025-12-31"
                        and (
                            report_audit.get("observed_data_coverage") or {}
                        ).get("status") in {"full", "partial", "empty", "unknown"}
                        and "2025-01-01 至 2025-12-31" in html
                        and "实际数据覆盖：" in html
                        and report.get("content_hash")
                        == hashlib.sha256(html.encode("utf-8")).hexdigest()
                    )

                elif args.phase == "m5106":
                    def mark(condition):
                        summaries[-1]["pass"] &= bool(condition)

                    async def general_case(label, text, *, conversation=None, model_key=key):
                        before_witnesses = len(witnesses)
                        body, plan = await post(
                            label,
                            text,
                            conversation=conversation,
                            model_key=model_key,
                        )
                        audit = body.get("execution_audit") or {}
                        usage = body.get("usage") or {}
                        mark(
                            not plan
                            and body.get("terminal_state") == "completed"
                            and body.get("response_type") == "answer"
                            and not body.get("memory_commit")
                            and body.get("tool_sequence") == []
                            and audit.get("semantic_mode") == "general"
                            and audit.get("schema_read") is False
                            and audit.get("member_lookup") is False
                            and audit.get("dax_executed") is False
                            and audit.get("pending_semantic_mutation") is False
                            and audit.get("powerbi_tool_calls") == 0
                            and audit.get("report_calls") == 0
                            and usage.get("call_count") == 1
                            and (usage.get("per_task") or {}).get("understanding") == 1
                            and len(witnesses) == before_witnesses
                        )
                        return body

                    async def completed_business(
                        label,
                        text,
                        shape,
                        *,
                        conversation=None,
                        model_key=key,
                    ):
                        body, plan = await post(
                            label,
                            text,
                            shape,
                            conversation=conversation,
                            model_key=model_key,
                        )
                        audit = body.get("execution_audit") or {}
                        mark(
                            audit.get("semantic_interpretation_authority")
                            == "semantic_frame"
                            and audit.get("query_shape_authority")
                            == "semantic_frame"
                            and audit.get("deterministic_dax") is True
                            and audit.get("llm_dax_call_count") == 0
                            and audit.get("layer3_pass") is True
                            and audit.get("factual_validation_pass") is True
                        )
                        return body, plan

                    for label, text in (
                        ("m5106_general_tired", "我今天有点累，聊两句"),
                        (
                            "m5106_general_location",
                            "我公司在深圳岗厦北，有什么推荐？",
                        ),
                        (
                            "m5106_general_mean",
                            "为什么平均数容易受极端值影响",
                        ),
                        (
                            "m5106_general_report_help",
                            "你怎样帮助我理解一张报表",
                        ),
                    ):
                        await general_case(label, text)

                    for label, text, display_term in (
                        (
                            "m5106_south_localized",
                            "2025年5月南方销售额是多少",
                            "南方",
                        ),
                        (
                            "m5106_south_conventional",
                            "2025年5月华南销售额是多少",
                            "华南",
                        ),
                        (
                            "m5106_south_mixed_language",
                            "Could you briefly show 2025年5月华南销售额",
                            "华南",
                        ),
                    ):
                        body, plan = await completed_business(
                            label, text, "scalar"
                        )
                        answer = body.get("answer") or ""
                        mark(
                            plan.get("measures") == ["Total Sales"]
                            and plan.get("filters")
                            == [
                                {
                                    "field": "Region",
                                    "operator": "eq",
                                    "value": "South",
                                }
                            ]
                            and (plan.get("time_range") or {}).get("start_date")
                            == "2025-05-01"
                            and (plan.get("time_range") or {}).get("end_date")
                            == "2025-05-31"
                            and display_term in answer
                            and not any(
                                token in answer
                                for token in (
                                    "Total Sales",
                                    "Region=South",
                                    "local_desktop_model",
                                    "measure:",
                                )
                            )
                        )

                    ambiguous_conversation = str(uuid.uuid4())
                    before_ambiguous = len(witnesses)
                    ambiguous, _ = await post(
                        "m5106_ambiguous_sales",
                        "2026年销售情况",
                        conversation=ambiguous_conversation,
                        blocked=True,
                    )
                    ambiguous_audit = ambiguous.get("execution_audit") or {}
                    mark(
                        not ambiguous.get("memory_commit")
                        and not ambiguous_audit.get("dax_executed")
                        and len(witnesses) == before_ambiguous
                        and ambiguous_audit.get("clarification_reason")
                        in {
                            "measure_ambiguous",
                            "measure_unresolved",
                            "unsupported_semantic_request",
                        }
                    )

                    for label, text in (
                        ("m5106_scalar_absolute", "2026年销售额情况"),
                        ("m5106_scalar_relative", "今年销售额"),
                    ):
                        body, plan = await completed_business(
                            label, text, "scalar"
                        )
                        mark(
                            plan.get("measures") == ["Total Sales"]
                            and plan.get("dimensions") == []
                            and plan.get("sort") is None
                            and plan.get("top_n") is None
                            and plan.get("time_range") is not None
                        )

                    unknown_conversation = str(uuid.uuid4())
                    before_unknown = len(witnesses)
                    unknown, _ = await post(
                        "m5106_unknown_member",
                        "火星区销售额",
                        conversation=unknown_conversation,
                        blocked=True,
                    )
                    unknown_audit = unknown.get("execution_audit") or {}
                    mark(
                        not unknown.get("memory_commit")
                        and not unknown_audit.get("dax_executed")
                        and len(witnesses) == before_unknown
                        and any(
                            item.get("status") in {"UNRESOLVED", "AMBIGUOUS"}
                            for item in (
                                unknown_audit.get("member_grounding_status") or []
                            )
                        )
                    )

                    ranking_body, ranking_plan = await completed_business(
                        "m5106_ranking",
                        "销售额最高的三个产品",
                        "ranking",
                    )
                    mark(
                        ranking_plan.get("measures") == ["Total Sales"]
                        and ranking_plan.get("dimensions") == ["Product"]
                        and ranking_plan.get("sort") == "desc"
                        and ranking_plan.get("top_n") == 3
                    )

                    chain = str(uuid.uuid4())
                    _, initial_plan = await completed_business(
                        "m5106_chain_initial",
                        "销售额最高的三个产品",
                        "ranking",
                        conversation=chain,
                    )
                    _, quantity_plan = await completed_business(
                        "m5106_chain_quantity",
                        "改成销售数量",
                        "ranking",
                        conversation=chain,
                    )
                    memory_before_general = (
                        await service.pipeline.get_latest_committed_memory(
                            chain, RuntimeDataMode.REAL
                        )
                    )
                    witness_count = len(witnesses)
                    await general_case(
                        "m5106_chain_general",
                        "讲个笑话",
                        conversation=chain,
                    )
                    memory_after_general = (
                        await service.pipeline.get_latest_committed_memory(
                            chain, RuntimeDataMode.REAL
                        )
                    )
                    _, final_plan = await completed_business(
                        "m5106_chain_sales",
                        "按销售额",
                        "ranking",
                        conversation=chain,
                    )
                    mark(
                        initial_plan.get("measures") == ["Total Sales"]
                        and quantity_plan.get("measures") == ["Total Quantity"]
                        and memory_before_general == memory_after_general
                        and len(witnesses) == witness_count + 1
                        and final_plan.get("measures") == ["Total Sales"]
                        and final_plan.get("dimensions") == ["Product"]
                        and final_plan.get("sort") == "desc"
                        and final_plan.get("top_n") == 3
                    )

                    explanation, explanation_plan = await post(
                        "m5106_explain_change",
                        "帮我分析当前报表里今年销售额为什么下降",
                    )
                    explanation_audit = explanation.get("execution_audit") or {}
                    explanation_answer = explanation.get("answer") or ""
                    mark(
                        explanation.get("terminal_state") == "completed"
                        and explanation.get("memory_commit")
                        and explanation_plan.get("measures") == ["Total Sales"]
                        and explanation_plan.get("time_range") is not None
                        and explanation_audit.get("dax_executed")
                        and explanation_audit.get("deterministic_dax") is True
                        and explanation_audit.get("llm_dax_call_count") == 0
                        and "不能证明具体原因" in explanation_answer
                    )

                    horizon, horizon_plan = await post(
                        "m5106_horizon",
                        "最近6个月销售额趋势",
                    )
                    horizon_audit = horizon.get("execution_audit") or {}
                    mark(
                        horizon.get("terminal_state") == "completed"
                        and horizon.get("memory_commit")
                        and horizon_plan.get("query_shape")
                        in {"trend", "bounded_trend"}
                        and horizon_plan.get("measures") == ["Total Sales"]
                        and horizon_plan.get("time_range") is not None
                        and (
                            horizon_audit.get("data_availability") or {}
                        ).get("available_data_horizon")
                        is not None
                        and horizon_audit.get("dax_executed")
                    )

                    second_models = [item for item in options if item["key"] != key]
                    if not second_models:
                        summaries.append(
                            {
                                "case": "m5106_cross_model_unavailable",
                                "pass": False,
                            }
                        )
                        print(
                            json.dumps(
                                {
                                    "case": "m5106_cross_model_unavailable",
                                    "pass": False,
                                    "available_target_count": 0,
                                }
                            ),
                            flush=True,
                        )
                    else:
                        second_model = next(
                            (
                                item
                                for item in second_models
                                if item["display_name"]
                                == "PowerBIAgent_M3_Test"
                            ),
                            second_models[0],
                        )
                        second_schema = schemas[second_model["key"]]
                        second_measures = [
                            measure.name
                            for table in second_schema.tables
                            for measure in table.measures
                        ]
                        if not second_measures:
                            raise RuntimeError(
                                "m5106_cross_model_measure_unavailable"
                            )
                        second_measure = second_measures[0]
                        cross_model = str(uuid.uuid4())
                        _, model_a_plan = await completed_business(
                            "m5106_cross_model_a",
                            "总销售额是多少",
                            "scalar",
                            conversation=cross_model,
                        )
                        memory_a = (
                            await service.pipeline.get_latest_committed_memory(
                                cross_model, RuntimeDataMode.REAL
                            )
                        )
                        await general_case(
                            "m5106_cross_model_general",
                            "我今天有点累，聊两句",
                            conversation=cross_model,
                        )
                        memory_general = (
                            await service.pipeline.get_latest_committed_memory(
                                cross_model, RuntimeDataMode.REAL
                            )
                        )
                        _, model_b_plan = await completed_business(
                            "m5106_cross_model_b",
                            f"{second_measure}是多少",
                            "scalar",
                            conversation=cross_model,
                            model_key=second_model["key"],
                        )
                        memory_b = (
                            await service.pipeline.get_latest_committed_memory(
                                cross_model, RuntimeDataMode.REAL
                            )
                        )
                        mark(
                            model_a_plan.get("measures") == ["Total Sales"]
                            and memory_a == memory_general
                            and model_b_plan.get("measures") == [second_measure]
                            and memory_b is not None
                            and memory_b.semantic_model_key
                            == second_model["key"]
                            and memory_b.measures == [second_measure]
                            and memory_b.filters == []
                        )

                elif args.phase == "m5106stress":
                    stress_results = {}
                    stability = {}
                    request_latencies_ms = []
                    provider_call_latencies_ms = []
                    provider_logical_call_latencies_ms = []
                    stress_metrics = {
                        "real_chat_turns": 0,
                        "real_llm_calls": 0,
                        "real_mcp_executions": 0,
                        "completed": 0,
                        "clarification": 0,
                        "unsupported": 0,
                        "provider_transient": 0,
                        "request_timeout_count": 0,
                        "provider_timeout_count": 0,
                        "http_504_count": 0,
                        "wrong_mode": 0,
                        "wrong_query_shape": 0,
                        "wrong_object": 0,
                        "wrong_member": 0,
                        "wrong_time": 0,
                        "wrong_dax": 0,
                        "wrong_factual_answer": 0,
                        "unexpected_dax_on_unknown": 0,
                        "unexpected_memory_mutation": 0,
                        "cross_model_bleed": 0,
                        "technical_presentation_leakage": 0,
                        "external_fact_hallucination": 0,
                        "stability_mismatch": 0,
                    }

                    def record_turn(body, summary):
                        audit = body.get("execution_audit") or {}
                        stress_metrics["real_chat_turns"] += 1
                        stress_metrics["real_llm_calls"] += int(
                            summary["llm_call_count"]
                        )
                        stress_metrics["real_mcp_executions"] += len(
                            body.get("tool_sequence") or []
                        )
                        terminal = body.get("terminal_state")
                        if terminal == "completed":
                            stress_metrics["completed"] += 1
                        elif terminal == "clarification_required":
                            stress_metrics["clarification"] += 1
                        if body.get("response_type") == "unsupported":
                            stress_metrics["unsupported"] += 1
                        if audit.get("provider_failure"):
                            stress_metrics["provider_transient"] += 1
                        request_latencies_ms.append(float(summary["latency_ms"]))
                        provider_call_latencies_ms.extend(
                            float(item["duration_ms"])
                            for item in summary.get("provider_timings", [])
                            if item.get("kind") == "provider_attempt"
                        )
                        provider_logical_call_latencies_ms.extend(
                            float(item["duration_ms"])
                            for item in summary.get("provider_timings", [])
                            if item.get("kind") == "provider_call"
                        )
                        if body.get("error_type") == "request_deadline_exceeded":
                            stress_metrics["request_timeout_count"] += 1
                        if summary.get("http") == 504:
                            stress_metrics["http_504_count"] += 1
                        stress_metrics["provider_timeout_count"] += sum(
                            item.get("kind") == "provider_attempt"
                            and item.get("failure_category") == "timeout"
                            for item in summary.get("provider_timings", [])
                        )

                    def add_failure(case_id, code):
                        stress_results.setdefault(case_id, []).append(code)
                        if code in stress_metrics:
                            stress_metrics[code] += 1

                    def normalized_signature(body, plan, summary):
                        audit = body.get("execution_audit") or {}
                        frame = audit.get("semantic_frame") or {}
                        canonical = {
                            name: value
                            for name, value in plan.items()
                            if name not in {"normalized_question", "inherited_context"}
                        }
                        return {
                            "terminal": body.get("terminal_state"),
                            "response_type": body.get("response_type"),
                            "mode": frame.get("mode") or audit.get("semantic_mode"),
                            "general_fact_scope": frame.get("general_fact_scope"),
                            "relation": frame.get("relation"),
                            "plan": canonical,
                            "clarification_reason": audit.get("clarification_reason"),
                            "dax_executed": bool(audit.get("dax_executed")),
                            "memory_commit": bool(body.get("memory_commit")),
                            "result_hash": summary.get("result_hash"),
                        }

                    async def support_turn(case_id, index, spec, conversation):
                        outcome = spec["outcome"]
                        body, plan = await post(
                            f"support__{case_id}__{index}",
                            spec["text"],
                            spec.get("shape") if outcome == "completed" else None,
                            conversation=conversation,
                            blocked=outcome == "blocked",
                        )
                        record_turn(body, summaries[-1])
                        if outcome == "general":
                            audit = body.get("execution_audit") or {}
                            if (
                                body.get("terminal_state") != "completed"
                                or body.get("memory_commit")
                                or audit.get("dax_executed")
                            ):
                                add_failure(case_id, "unexpected_memory_mutation")
                        return body, plan

                    async def run_stress_case(case, run_index):
                        case_id = case["id"]
                        conversation = str(uuid.uuid4())
                        for index, spec in enumerate(case.get("setup", []), 1):
                            await support_turn(case_id, index, spec, conversation)
                        outcome = case["outcome"]
                        label = (
                            f"stress__{case_id}"
                            if run_index == 1
                            else f"stress_repeat{run_index}__{case_id}"
                        )
                        body, plan = await post(
                            label,
                            case["text"],
                            case.get("shape")
                            if outcome in {"completed", "explain"}
                            else None,
                            conversation=conversation,
                            blocked=outcome == "blocked",
                            template=case.get("template"),
                            allow_unsupported=outcome == "external",
                        )
                        record_turn(body, summaries[-1])
                        audit = body.get("execution_audit") or {}
                        answer = body.get("answer") or ""
                        summary = summaries[-1]
                        errors = []

                        def fail(code):
                            errors.append(code)
                            add_failure(case_id, code)

                        transient_error = (
                            body.get("error_type") in {
                                "request_deadline_exceeded",
                                "llm_provider_error",
                                "llm_response_error",
                                "llm_validation_error",
                            }
                            and summary.get("http") in {502, 503, 504}
                        ) or any(
                            failure.get("category") in {
                                "connection", "timeout", "rate_limit", "service"
                            }
                            for failure in summary.get("provider_failures", [])
                        )
                        if transient_error:
                            errors.append("provider_transient")
                            stress_results.setdefault(case_id, []).append(
                                "provider_transient"
                            )
                            stress_metrics["provider_transient"] += 1
                            print(json.dumps({
                                "stress_contract": case_id,
                                "category": case["category"],
                                "run": run_index,
                                "pass": False,
                                "errors": errors,
                                "http": summary.get("http"),
                                "terminal": body.get("terminal_state"),
                                "response_type": body.get("response_type"),
                                "error_type": body.get("error_type"),
                                "semantic_error_code": None,
                                "provider_failures": summary.get("provider_failures"),
                                "provider_timings": summary.get("provider_timings"),
                                "tool_timings": summary.get("tool_timings"),
                                "signature": None,
                            }, ensure_ascii=False, default=str), flush=True)
                            if args.stress_stop_on_transient:
                                raise RuntimeError(
                                    "stress_provider_transient_trace_complete"
                                )
                            return

                        if outcome == "general":
                            if (
                                plan
                                or body.get("terminal_state") != "completed"
                                or body.get("response_type") != "answer"
                                or body.get("memory_commit")
                                or body.get("tool_sequence")
                                or audit.get("semantic_mode") != "general"
                                or audit.get("dax_executed")
                            ):
                                fail("wrong_mode")
                        elif outcome == "external":
                            frame = audit.get("semantic_frame") or {}
                            bounded_general = (
                                audit.get("semantic_mode") == "general"
                                and frame.get("general_fact_scope")
                                == "REQUIRES_CURRENT_EXTERNAL_FACTS"
                            )
                            bounded_direct = (
                                body.get("terminal_state") == "unsupported"
                                and body.get("response_type") == "unsupported"
                            )
                            safe_wording = bounded_direct or any(
                                token in answer
                                for token in (
                                    "没有可验证", "无法确认", "无法回答", "不能核实"
                                )
                            )
                            unsafe_specifics = any(
                                token in answer
                                for token in (
                                    "肯德基", "汉堡王", "星巴克", "瑞幸",
                                    "晴", "多云", "美元", "涨到", "跌到",
                                )
                            )
                            if not (
                                not plan
                                and not body.get("memory_commit")
                                and not body.get("tool_sequence")
                                and not audit.get("dax_executed")
                                and (bounded_general or bounded_direct)
                                and safe_wording
                                and not unsafe_specifics
                            ):
                                fail("external_fact_hallucination")
                        elif outcome == "blocked":
                            if body.get("terminal_state") != "clarification_required":
                                fail("wrong_mode")
                            if audit.get("dax_executed"):
                                fail("unexpected_dax_on_unknown")
                            if body.get("memory_commit"):
                                fail("unexpected_memory_mutation")
                        elif outcome == "report":
                            report = body.get("report") or {}
                            if not (
                                body.get("terminal_state") == "completed"
                                and body.get("response_type") == "report"
                                and body.get("memory_commit")
                                and report.get("template_key") == case["template"]
                                and report.get("report_id")
                                and report.get("content_hash")
                            ):
                                fail("wrong_factual_answer")
                        else:
                            if body.get("terminal_state") != "completed":
                                fail("wrong_mode")
                            if plan.get("query_shape") != case.get("shape"):
                                fail("wrong_query_shape")
                            if plan.get("measures") != case.get("measures", []):
                                fail("wrong_object")
                            if "dimensions" in case and plan.get("dimensions") != case["dimensions"]:
                                fail("wrong_object")
                            if "filters" in case and plan.get("filters") != case["filters"]:
                                fail("wrong_member")
                            if case.get("time") and not plan.get("time_range"):
                                fail("wrong_time")
                            expected_time = case.get("time_range")
                            if expected_time and any(
                                (plan.get("time_range") or {}).get(key) != value
                                for key, value in expected_time.items()
                            ):
                                fail("wrong_time")
                            if "top_n" in case and plan.get("top_n") != case["top_n"]:
                                fail("wrong_query_shape")
                            if "sort" in case and plan.get("sort") != case["sort"]:
                                fail("wrong_query_shape")
                            if not (
                                audit.get("dax_executed")
                                and audit.get("deterministic_dax") is True
                                and audit.get("llm_dax_call_count") == 0
                                and audit.get("factual_validation_pass") is True
                                and body.get("memory_commit")
                            ):
                                fail("wrong_dax")
                            if outcome == "explain" and "不能证明具体原因" not in answer:
                                fail("wrong_factual_answer")
                            forbidden = [
                                "Region=South", "semantic_model_key", "local_desktop:",
                                "measure:", "fact-", "result-",
                            ]
                            if "Total Sales" not in case["text"]:
                                forbidden.append("Total Sales")
                            if "Total Quantity" not in case["text"]:
                                forbidden.append("Total Quantity")
                            if any(token in answer for token in forbidden):
                                fail("technical_presentation_leakage")
                            if "数据更新至" in answer:
                                fail("wrong_factual_answer")

                        if errors:
                            summary["pass"] = False
                        signature = normalized_signature(body, plan, summary)
                        stability.setdefault(case_id, []).append(signature)
                        if (
                            not args.stress_summary_only
                            or errors
                            or not summary.get("pass")
                        ):
                            print(json.dumps({
                                "stress_contract": case_id,
                                "category": case["category"],
                                "run": run_index,
                                "pass": not errors and bool(summary.get("pass")),
                                "errors": errors,
                                "http": summary.get("http"),
                                "terminal": body.get("terminal_state"),
                                "response_type": body.get("response_type"),
                                "error_type": body.get("error_type"),
                                "semantic_error_code": (
                                    (body.get("execution_audit") or {}).get(
                                        "semantic_interpretation_error_code"
                                    )
                                ),
                                "provider_failures": summary.get("provider_failures"),
                                "provider_timings": summary.get("provider_timings"),
                                "tool_timings": summary.get("tool_timings"),
                                "signature": signature,
                            }, ensure_ascii=False, default=str), flush=True)

                    selectable_cases = [*M5106_STRESS_CASES]
                    if args.case:
                        selectable_cases.extend(M5106_FOCUSED_EXPLAIN_CASES)
                    selected_cases = [
                        case for case in selectable_cases
                        if not args.case or case["id"] in args.case
                    ]
                    for case in selected_cases:
                        await run_stress_case(case, 1)
                    if not args.stress_baseline_only:
                        for run_index in (2, 3):
                            for case in selected_cases:
                                if case.get("high_risk") or args.stress_repeat_selected:
                                    await run_stress_case(case, run_index)

                    for case_id, signatures in stability.items():
                        if len(signatures) < 2:
                            continue
                        if any(item != signatures[0] for item in signatures[1:]):
                            stress_metrics["stability_mismatch"] += 1
                            stress_results.setdefault(case_id, []).append(
                                "stability_mismatch"
                            )
                            for item in summaries:
                                if item.get("case", "").endswith(f"__{case_id}"):
                                    item["pass"] = False
                            print(json.dumps({
                                "stability_mismatch_detail": case_id,
                                "signatures": signatures,
                            }, ensure_ascii=False, default=str), flush=True)

                    def percentile(values, quantile):
                        if not values:
                            return 0
                        ordered = sorted(values)
                        index = max(0, math.ceil(len(ordered) * quantile) - 1)
                        return round(ordered[index], 2)

                    stress_metrics["request_latency_ms"] = {
                        "p50": percentile(request_latencies_ms, 0.50),
                        "p95": percentile(request_latencies_ms, 0.95),
                        "max": round(max(request_latencies_ms), 2)
                        if request_latencies_ms else 0,
                    }
                    stress_metrics["max_single_llm_attempt_ms"] = (
                        round(max(provider_call_latencies_ms), 2)
                        if provider_call_latencies_ms else 0
                    )
                    stress_metrics["max_logical_llm_call_ms"] = (
                        round(max(provider_logical_call_latencies_ms), 2)
                        if provider_logical_call_latencies_ms else 0
                    )

                    print(json.dumps({
                        "real_language_stress": {
                            "declared_unique_scenarios": len(M5106_STRESS_CASES),
                            "executed_unique_scenarios": len(selected_cases),
                            "category_counts": M5106_STRESS_CATEGORY_COUNTS,
                            "high_risk_scenarios": sum(
                                bool(item.get("high_risk")) for item in selected_cases
                            ),
                            "metrics": stress_metrics,
                            "failed_contracts": stress_results,
                            "baseline_only": bool(args.stress_baseline_only),
                        }
                    }, ensure_ascii=False, default=str), flush=True)

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
        if service is not None and original_tool_execute is not None:
            service.tool_gateway.execute = original_tool_execute
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=30)


def main():
    # Preserve Chinese evidence under Windows redirected stdout as well.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--profile", default="deepseek")
    parser.add_argument("--phase", choices=("inspect", "focused", "extended", "performance", "browser", "isolation", "m585", "m5104", "m5105", "m5106", "m5106stress"), default="focused")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--case", action="append", help="Run selected focused cases while diagnosing a failure")
    parser.add_argument("--compare-profiles", action="store_true")
    parser.add_argument("--m585-single-profile", action="store_true", help="Run only --profile for focused M5.8.5 diagnosis")
    parser.add_argument("--candidate-evidence", action="store_true", help="Print bounded runtime metadata for diagnosis; never prompts or secrets")
    parser.add_argument("--witness-evidence", action="store_true", help="Print validated DAX/result/fact witnesses to the console only; never commit business output")
    parser.add_argument("--stress-baseline-only", action="store_true", help="Run the 72 unique stress scenarios once without the 24 high-risk repeats")
    parser.add_argument("--stress-repeat-selected", action="store_true", help="Repeat explicitly selected stress cases three times for a focused stability check")
    parser.add_argument("--stress-summary-only", action="store_true", help="Suppress passing per-case stress output while retaining failures and final metrics")
    parser.add_argument("--stress-stop-on-transient", action="store_true", help="Stop after the first classified provider/deadline transient for bounded latency diagnosis")
    args = parser.parse_args()
    with owned_acceptance_tempdir(prefix="powerbiagent-context-real-") as root:
        provider_failures = {}
        provider_timings = {}
        with observe_provider_failures(provider_failures, provider_timings):
            asyncio.run(run(args, root, provider_failures, provider_timings))


if __name__ == "__main__":
    main()
