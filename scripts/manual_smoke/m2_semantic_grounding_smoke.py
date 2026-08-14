"""M2.6.2 real semantic acceptance at the Canonical QueryPlan boundary.

The formal Chat API and production TurnPipeline still run end to end.  This
runner observes the actual plan passed to production Layer2 and evaluates only
the M2.6.2 boundary.  DAX/Layer3/QueryResult outcomes are retained as downstream
observations and never converted into a semantic pass.

For multi-turn acceptance, an isolated observer-owned semantic state is derived
only from a successfully grounded, Layer2-valid canonical plan.  It is supplied
as the next turn's committed context so downstream DAX variability cannot hide
or erase semantic transition coverage.  No expected value is used to construct
that state, and production Memory commit policy is unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _desktop_running() -> bool:
    if sys.platform != "win32":
        return False
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "if (Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue) "
                "{ exit 0 } else { exit 1 }"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


@dataclass(frozen=True)
class Expected:
    semantic_outcome: Literal["resolved", "clarification", "failure"] = "resolved"
    measure: str | None = None
    dimensions: tuple[str, ...] = ()
    filters: tuple[tuple[str, str], ...] = ()
    time_mode: str | None = None
    time_date_field: str | None = None
    time_start: str | None = None
    time_end: str | None = None
    sort: str | None = None
    top_n: int | None = None
    measure_transition: str | None = None
    dimension_transition: str | None = None
    time_transition: str | None = None
    sort_transition: str | None = None
    top_n_transition: str | None = None
    filter_transition: str | None = None
    requires_member_lookup: bool = False
    expected_failure_stage: str | None = None


def _downstream_error_code(failure_reason: str | None, error_type: str | None) -> str | None:
    if failure_reason:
        match = re.search(r"\b(dax_[a-z0-9_]+)\b", failure_reason)
        if match:
            return match.group(1)
    return error_type


def _exception_chain(exc: BaseException) -> str:
    items: list[str] = []
    current: BaseException | None = exc
    while current is not None and len(items) < 4:
        error_code = getattr(current, "error_code", None)
        items.append(
            f"{type(current).__name__}[{error_code or ''}]: {str(current)[:240]}"
        )
        current = current.__cause__ or current.__context__
    return " <- ".join(items)


async def _run(*, historical_repeats: int, selected_case: str | None) -> int:
    from httpx import ASGITransport, AsyncClient

    from backend.app.config.settings import LLMMode, PowerBIMode, Settings
    from backend.app.harness.errors import ToolExecutionError
    from backend.app.harness.tool_registry import (
        TOOL_NAME_DAX,
        TOOL_NAME_MEMBERS,
    )
    from backend.app.main import create_app
    from backend.app.memory.models import (
        MemoryStatus,
        RuntimeDataMode,
        StructuredWorkMemory,
    )
    from backend.app.schemas.data_contracts import (
        CanonicalQueryPlan,
        ColumnMembersResult,
        QueryResult,
        SemanticModelSchema,
    )

    settings = Settings(
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
    )
    ready = all((
        sys.platform == "win32",
        settings.is_deepseek_configured,
        settings.is_powerbi_local_mcp_configured,
        shutil.which(settings.powerbi_local_mcp_executable) is not None,
        _desktop_running(),
    ))
    if not ready:
        print(json.dumps({
            "passed": False,
            "status": "local_prerequisite_missing",
            "source_mode": "",
            "fallback_count": 0,
        }, ensure_ascii=False, indent=2))
        return 1

    app = create_app(settings=settings)
    results: list[dict[str, Any]] = []
    fallback_count = 0
    controlled_member_failures: set[str] = set()
    traces: dict[str, Any] = {}
    query_results: dict[str, QueryResult] = {}
    member_results: dict[str, list[ColumnMembersResult]] = {}
    schemas: dict[str, SemanticModelSchema] = {}
    canonical_artifacts: dict[str, dict[str, Any]] = {}
    semantic_states: dict[str, StructuredWorkMemory] = {}
    service_errors: dict[str, str] = {}
    grounding_errors: dict[str, str] = {}
    grounding_outcomes: dict[str, Any] = {}
    active_request_id: str | None = None

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        from backend.app.application import deepseek_turn_service as turn_service_module

        original_service_execute = service.execute
        original_ground = turn_service_module.SemanticGroundingService.ground
        original_gateway_execute = service.tool_gateway.execute
        original_validate_query_plan = service.validator.validate_query_plan
        original_get_latest_committed = service.pipeline.memory_repo.get_latest_committed

        async def semantic_get_latest_committed(
            conversation_id: str,
            runtime_mode: RuntimeDataMode | None = None,
        ) -> StructuredWorkMemory | None:
            observed = semantic_states.get(conversation_id)
            if observed is not None and runtime_mode in {None, RuntimeDataMode.REAL}:
                return copy.deepcopy(observed)
            return await original_get_latest_committed(conversation_id, runtime_mode)

        service.pipeline.memory_repo.get_latest_committed = semantic_get_latest_committed

        async def observed_service_execute(*args: Any, **kwargs: Any) -> Any:
            request_id = str(kwargs.get("request_id") or "")
            try:
                return await original_service_execute(*args, **kwargs)
            except Exception as exc:
                service_errors[request_id] = _exception_chain(exc)
                raise

        service.execute = observed_service_execute

        async def observed_ground(grounder: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                result = await original_ground(grounder, *args, **kwargs)
                if active_request_id is not None:
                    grounding_outcomes[active_request_id] = result
                return result
            except Exception as exc:
                if active_request_id is not None:
                    grounding_errors[active_request_id] = _exception_chain(exc)
                raise

        turn_service_module.SemanticGroundingService.ground = observed_ground

        def observed_validate_query_plan(
            plan: Any,
            schema: SemanticModelSchema,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            result = original_validate_query_plan(plan, schema, *args, **kwargs)
            if (
                active_request_id is not None
                and kwargs.get("enforce_semantic_grounding") is True
                and isinstance(plan, CanonicalQueryPlan)
            ):
                canonical_artifacts[active_request_id] = {
                    "plan": plan.model_copy(deep=True),
                    "layer2": result,
                    "schema": schema.model_copy(deep=True),
                }
            return result

        service.validator.validate_query_plan = observed_validate_query_plan

        async def observed_gateway_execute(
            tool_name: str,
            execution_context: Any,
            input_data: Any,
            trace: Any = None,
            controller: Any = None,
        ) -> Any:
            request_id = execution_context.request_id
            if trace is not None:
                traces[request_id] = trace
            if (
                tool_name == TOOL_NAME_MEMBERS
                and request_id in controlled_member_failures
            ):
                raise ToolExecutionError("controlled_member_grounding_failure")
            result = await original_gateway_execute(
                tool_name,
                execution_context,
                input_data,
                trace=trace,
                controller=controller,
            )
            if isinstance(result, SemanticModelSchema):
                schemas[request_id] = result
            elif isinstance(result, QueryResult):
                query_results[request_id] = result
            elif isinstance(result, ColumnMembersResult):
                member_results.setdefault(request_id, []).append(result)
            return result

        service.tool_gateway.execute = observed_gateway_execute
        transport = ASGITransport(app=app, raise_app_exceptions=True)

        async def execute_case(
            client: AsyncClient,
            *,
            name: str,
            message: str,
            conversation_id: str,
            expected: Expected,
            inject_member_failure: bool = False,
        ) -> dict[str, Any]:
            nonlocal active_request_id, fallback_count
            request_id = f"m262-{name}-{uuid.uuid4().hex}"
            before_semantic = copy.deepcopy(semantic_states.get(conversation_id))
            before_production = await original_get_latest_committed(
                conversation_id, RuntimeDataMode.REAL
            )
            if inject_member_failure:
                controlled_member_failures.add(request_id)
            active_request_id = request_id
            try:
                response = await client.post("/api/v1/chat", json={
                    "message": message,
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "semantic_model_key": settings.powerbi_local_semantic_model_key,
                })
            finally:
                active_request_id = None

            try:
                body = response.json()
            except json.JSONDecodeError:
                body = {}
            request_memory = await service.pipeline.get_memory_by_request_id(
                request_id, RuntimeDataMode.REAL
            )
            after_production = await original_get_latest_committed(
                conversation_id, RuntimeDataMode.REAL
            )
            artifact = canonical_artifacts.get(request_id)
            plan: CanonicalQueryPlan | None = artifact["plan"] if artifact else None
            layer2 = artifact["layer2"] if artifact else None
            trace = traces.get(request_id)
            grounding_events = (
                trace.get_events_by_type("semantic_grounding_resolved")
                if trace is not None else []
            )
            clarification_events = (
                trace.get_events_by_type("semantic_grounding_clarification")
                if trace is not None else []
            )
            transition = (
                grounding_events[-1].data_summary if grounding_events else {}
            )

            schema = schemas.get(request_id)
            members = member_results.get(request_id, [])
            real_runtime_ok = bool(
                service._source_mode == "real"
                and not service.powerbi.is_mock
                and schema is not None
                and schema.key == settings.powerbi_local_semantic_model_key
                and all(item.source_mode == "real" for item in members)
            )
            if expected.requires_member_lookup:
                real_runtime_ok = real_runtime_ok and bool(members)
            sources = [item.source_mode for item in members]
            query_result = query_results.get(request_id)
            if query_result is not None:
                sources.append(query_result.source_mode)
            case_fallbacks = sum(source == "mock" for source in sources)
            fallback_count += case_fallbacks

            filters = tuple(sorted(
                (item.field, str(item.value)) for item in (plan.filters if plan else [])
            ))
            time_range = plan.time_range if plan else None
            failure_stage = request_memory.failure_stage if request_memory else None
            failure_reason = request_memory.failure_reason if request_memory else None

            boundary_reached = bool(
                plan is not None
                and layer2 is not None
                and layer2.is_valid
                and grounding_events
                and plan.grounding_authority == "semantic_catalog"
            )
            if boundary_reached and plan is not None:
                previous_version = before_semantic.memory_version if before_semantic else 0
                semantic_states[conversation_id] = StructuredWorkMemory(
                    conversation_id=conversation_id,
                    request_id=request_id,
                    semantic_model_key=plan.semantic_model_key,
                    current_intent=body.get("intent") or "data_question",
                    measures=list(plan.measures),
                    dimensions=list(plan.dimensions),
                    filters=[item.model_dump() for item in plan.filters],
                    time_range=plan.time_range,
                    sort=plan.sort,
                    top_n=plan.top_n,
                    comparison_mode=plan.comparison_mode,
                    last_query_plan=plan.model_dump(),
                    base_memory_version=previous_version,
                    memory_version=previous_version + 1,
                    state_status=MemoryStatus.COMMITTED,
                    runtime_mode=RuntimeDataMode.REAL,
                    is_mock=False,
                    llm_provider="deepseek",
                    powerbi_provider=service.powerbi.provider_name,
                )

            state_unchanged = semantic_states.get(conversation_id) == before_semantic
            production_unchanged = (
                (before_production is None and after_production is None)
                or (
                    before_production is not None
                    and after_production is not None
                    and before_production.memory_version == after_production.memory_version
                    and before_production.last_query_plan == after_production.last_query_plan
                )
            )

            transition_checks = {
                "measure_transition": expected.measure_transition,
                "dimension_transition": expected.dimension_transition,
                "time_transition": expected.time_transition,
                "sort_transition": expected.sort_transition,
                "top_n_transition": expected.top_n_transition,
            }
            transition_ok = all(
                expected_value is None or transition.get(key) == expected_value
                for key, expected_value in transition_checks.items()
            )
            if expected.filter_transition is not None:
                transition_ok = transition_ok and expected.filter_transition in (
                    transition.get("filter_transitions") or []
                )

            if expected.semantic_outcome == "resolved":
                semantic_assertions = bool(
                    boundary_reached
                    and plan is not None
                    and plan.measures == [expected.measure]
                    and tuple(plan.dimensions) == expected.dimensions
                    and filters == tuple(sorted(expected.filters))
                    and (time_range.mode.value if time_range else None)
                    == expected.time_mode
                    and (time_range.date_field if time_range else None)
                    == expected.time_date_field
                    and (time_range.start_date.isoformat() if time_range else None)
                    == expected.time_start
                    and (time_range.end_date.isoformat() if time_range else None)
                    == expected.time_end
                    and plan.sort == expected.sort
                    and plan.top_n == expected.top_n
                    and transition_ok
                )
                semantic_state_decision = "UPDATE"
            elif expected.semantic_outcome == "clarification":
                semantic_assertions = bool(
                    not boundary_reached
                    and clarification_events
                    and body.get("terminal_state") == "clarification_required"
                    and body.get("memory_commit") is False
                    and state_unchanged
                    and production_unchanged
                )
                semantic_state_decision = "NO_COMMIT"
            else:
                semantic_assertions = bool(
                    not boundary_reached
                    and failure_stage == expected.expected_failure_stage
                    and body.get("memory_commit") is False
                    and state_unchanged
                    and production_unchanged
                )
                semantic_state_decision = "NO_COMMIT"

            passed = bool(
                semantic_assertions
                and real_runtime_ok
                and case_fallbacks == 0
            )
            summary = {
                "case": name,
                "semantic_pass": passed,
                "semantic_outcome": expected.semantic_outcome,
                "canonical_measure": plan.measures[0] if plan and plan.measures else None,
                "canonical_dimensions": list(plan.dimensions) if plan else None,
                "canonical_filters": [list(item) for item in filters] if plan else None,
                "canonical_time": time_range.model_dump(mode="json") if time_range else None,
                "canonical_sort": plan.sort if plan else None,
                "canonical_top_n": plan.top_n if plan else None,
                "layer2_pass": bool(layer2 and layer2.is_valid),
                "measure_transition": transition.get("measure_transition"),
                "dimension_transition": transition.get("dimension_transition"),
                "time_transition": transition.get("time_transition"),
                "filter_transitions": transition.get("filter_transitions", []),
                "semantic_state_decision": semantic_state_decision,
                "production_memory_commit": body.get("memory_commit", False),
                "source_mode": "real" if real_runtime_ok else "invalid",
                "fallback_count": case_fallbacks,
                "downstream_status": body.get("terminal_state") or f"http_{response.status_code}",
                "downstream_stage": failure_stage,
                "downstream_error_code": _downstream_error_code(
                    failure_reason, body.get("error_type")
                ),
                "runner_service_error": service_errors.get(request_id),
                "runner_grounding_error": grounding_errors.get(request_id),
                "grounding_status": (
                    grounding_outcomes[request_id].status.value
                    if request_id in grounding_outcomes else None
                ),
                "grounding_objects": [
                    {
                        "role": item.role,
                        "status": item.status.value,
                        "method": item.method,
                        "canonical": (
                            item.canonical_object.canonical_name
                            if item.canonical_object else None
                        ),
                    }
                    for item in (
                        grounding_outcomes[request_id].object_results
                        if request_id in grounding_outcomes else []
                    )
                ],
            }
            results.append(summary)
            return {
                "summary": summary,
                "semantic_state": copy.deepcopy(semantic_states.get(conversation_id)),
            }

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            today = date.today()
            month_end = date(
                today.year + (today.month == 12),
                1 if today.month == 12 else today.month + 1,
                1,
            ).fromordinal(
                date(
                    today.year + (today.month == 12),
                    1 if today.month == 12 else today.month + 1,
                    1,
                ).toordinal() - 1
            )
            month_index = today.year * 12 + today.month - 3
            recent_start_year, recent_zero_month = divmod(month_index, 12)
            standalone = (
                (
                    "measure_canonical", "Total Sales 是多少？",
                    Expected(measure="Total Sales", measure_transition="REPLACE"),
                ),
                (
                    "measure_alias", "销量是多少？",
                    Expected(measure="Total Quantity", measure_transition="REPLACE"),
                ),
                (
                    "dimension_alias", "按品类看销售额",
                    Expected(
                        measure="Total Sales", dimensions=("Category",),
                        measure_transition="REPLACE", dimension_transition="REPLACE",
                    ),
                ),
                (
                    "filter_field_member_exact", "Electronics 品类的销售额是多少？",
                    Expected(
                        measure="Total Sales", filters=(("Category", "Electronics"),),
                        filter_transition="ADD", requires_member_lookup=True,
                    ),
                ),
                (
                    "member_normalized", "electronics 品类的销售额是多少？",
                    Expected(
                        measure="Total Sales", filters=(("Category", "Electronics"),),
                        filter_transition="ADD", requires_member_lookup=True,
                    ),
                ),
                (
                    "time_current_month", "本月销售额是多少？",
                    Expected(
                        measure="Total Sales", time_mode="current_month",
                        time_date_field="OrderDate",
                        time_start=today.replace(day=1).isoformat(),
                        time_end=month_end.isoformat(),
                        time_transition="REPLACE",
                    ),
                ),
                (
                    "time_recent_months", "最近3个月销售额是多少？",
                    Expected(
                        measure="Total Sales", time_mode="recent_months",
                        time_date_field="OrderDate",
                        time_start=date(
                            recent_start_year, recent_zero_month + 1, 1
                        ).isoformat(),
                        time_end=month_end.isoformat(),
                        time_transition="REPLACE",
                    ),
                ),
                (
                    "analysis_top_n", "按品类看销售额最高的前3个",
                    Expected(
                        measure="Total Sales", dimensions=("Category",),
                        sort="desc", top_n=3,
                        dimension_transition="REPLACE",
                        sort_transition="REPLACE", top_n_transition="REPLACE",
                    ),
                ),
                (
                    "known_filter_topn_holdout",
                    "Electronics 类别中总数量最高的前3个产品是什么？",
                    Expected(
                        measure="Total Quantity", dimensions=("Product",),
                        filters=(("Category", "Electronics"),),
                        sort="desc", top_n=3,
                        measure_transition="REPLACE",
                        dimension_transition="REPLACE",
                        filter_transition="ADD",
                        sort_transition="REPLACE",
                        top_n_transition="REPLACE",
                        requires_member_lookup=True,
                    ),
                ),
            )
            for name, message, expected in standalone:
                if selected_case is not None and name != selected_case:
                    continue
                await execute_case(
                    client,
                    name=name,
                    message=message,
                    conversation_id=f"m262-{name}-{uuid.uuid4().hex}",
                    expected=expected,
                )

            state_conversation = f"m262-state-{uuid.uuid4().hex}"
            if selected_case in {None, "state_sequence"}:
                await execute_case(
                    client,
                    name="state_seed",
                    message="本月按类别看销售额",
                    conversation_id=state_conversation,
                    expected=Expected(
                        measure="Total Sales", dimensions=("Category",),
                        time_mode="current_month", time_date_field="OrderDate",
                        time_start=today.replace(day=1).isoformat(),
                        time_end=month_end.isoformat(),
                    ),
                )
                await execute_case(
                    client,
                    name="dimension_only_switch",
                    message="改成按产品看",
                    conversation_id=state_conversation,
                    expected=Expected(
                        measure="Total Sales", dimensions=("Product",),
                        time_mode="current_month", time_date_field="OrderDate",
                        time_start=today.replace(day=1).isoformat(),
                        time_end=month_end.isoformat(),
                        measure_transition="KEEP", dimension_transition="REPLACE",
                        time_transition="KEEP",
                    ),
                )
                await execute_case(
                    client,
                    name="measure_only_switch",
                    message="那销量呢",
                    conversation_id=state_conversation,
                    expected=Expected(
                        measure="Total Quantity", dimensions=("Product",),
                        time_mode="current_month", time_date_field="OrderDate",
                        time_start=today.replace(day=1).isoformat(),
                        time_end=month_end.isoformat(),
                        measure_transition="REPLACE", dimension_transition="KEEP",
                        time_transition="KEEP",
                    ),
                )
                await execute_case(
                    client,
                    name="time_only_replace",
                    message="改成今年",
                    conversation_id=state_conversation,
                    expected=Expected(
                        measure="Total Quantity", dimensions=("Product",),
                        time_mode="current_year", time_date_field="OrderDate",
                        time_start=date(today.year, 1, 1).isoformat(),
                        time_end=date(today.year, 12, 31).isoformat(),
                        measure_transition="KEEP", dimension_transition="KEEP",
                        time_transition="REPLACE",
                    ),
                )
                await execute_case(
                    client,
                    name="time_clear",
                    message="清除时间",
                    conversation_id=state_conversation,
                    expected=Expected(
                        measure="Total Quantity", dimensions=("Product",),
                        measure_transition="KEEP", dimension_transition="KEEP",
                        time_transition="CLEAR",
                    ),
                )

            filter_conversation = f"m262-filter-{uuid.uuid4().hex}"
            if selected_case in {None, "filter_sequence"}:
                await execute_case(
                    client,
                    name="filter_seed",
                    message="Electronics 类别的销售额是多少？",
                    conversation_id=filter_conversation,
                    expected=Expected(
                        measure="Total Sales", filters=(("Category", "Electronics"),),
                        filter_transition="ADD", requires_member_lookup=True,
                    ),
                )
                await execute_case(
                    client,
                    name="filter_member_only_replace",
                    message="换成 Furniture",
                    conversation_id=filter_conversation,
                    expected=Expected(
                        measure="Total Sales", filters=(("Category", "Furniture"),),
                        measure_transition="KEEP",
                        filter_transition="REPLACE_SAME_FIELD",
                        requires_member_lookup=True,
                    ),
                )
                await execute_case(
                    client,
                    name="ambiguity_no_commit",
                    message="改成按类别和产品看",
                    conversation_id=filter_conversation,
                    expected=Expected(semantic_outcome="clarification"),
                )
                await execute_case(
                    client,
                    name="unresolved_member_no_commit",
                    message="换成 NotARealCategoryMember",
                    conversation_id=filter_conversation,
                    expected=Expected(
                        semantic_outcome="clarification", requires_member_lookup=True
                    ),
                )
                await execute_case(
                    client,
                    name="failed_semantic_turn_no_pollution",
                    message="换成 Electronics",
                    conversation_id=filter_conversation,
                    expected=Expected(
                        semantic_outcome="failure", requires_member_lookup=False,
                        expected_failure_stage="member_grounding",
                    ),
                    inject_member_failure=True,
                )

            historical_passes = 0
            historical_details: list[dict[str, Any]] = []
            repeats = (
                range(1, historical_repeats + 1)
                if selected_case in {None, "historical"} else ()
            )
            for repeat in repeats:
                conversation_id = f"m262-a123-{repeat}-{uuid.uuid4().hex}"
                a1 = await execute_case(
                    client,
                    name=f"a123_{repeat}_a1",
                    message="按类别看销售额",
                    conversation_id=conversation_id,
                    expected=Expected(
                        measure="Total Sales", dimensions=("Category",),
                        measure_transition="REPLACE", dimension_transition="REPLACE",
                    ),
                )
                a2 = await execute_case(
                    client,
                    name=f"a123_{repeat}_a2",
                    message="只看 Electronics",
                    conversation_id=conversation_id,
                    expected=Expected(
                        measure="Total Sales", dimensions=("Category",),
                        filters=(("Category", "Electronics"),),
                        measure_transition="KEEP", dimension_transition="KEEP",
                        filter_transition="ADD", requires_member_lookup=True,
                    ),
                )
                a3 = await execute_case(
                    client,
                    name=f"a123_{repeat}_a3",
                    message="那销量呢",
                    conversation_id=conversation_id,
                    expected=Expected(
                        measure="Total Quantity", dimensions=("Category",),
                        filters=(("Category", "Electronics"),),
                        measure_transition="REPLACE", dimension_transition="KEEP",
                        filter_transition="KEEP",
                    ),
                )
                passed = all(
                    item["summary"]["semantic_pass"] for item in (a1, a2, a3)
                )
                historical_passes += passed
                a3_state = a3["semantic_state"]
                historical_details.append({
                    "repeat": repeat,
                    "semantic_pass": passed,
                    "a1_canonical_measure": a1["summary"]["canonical_measure"],
                    "a2_inherited_measure": a2["summary"]["canonical_measure"],
                    "a2_filter_transition": a2["summary"]["filter_transitions"],
                    "a3_grounded_measure": a3["summary"]["canonical_measure"],
                    "a3_state_operation": a3["summary"]["measure_transition"],
                    "a3_final_query_plan_measure": a3["summary"]["canonical_measure"],
                    "a3_memory_decision": a3["summary"]["semantic_state_decision"],
                    "a3_semantic_state_measure": (
                        a3_state.measures[0] if a3_state and a3_state.measures else None
                    ),
                    "downstream_statuses": [
                        item["summary"]["downstream_status"] for item in (a1, a2, a3)
                    ],
                    "downstream_error_codes": [
                        item["summary"]["downstream_error_code"]
                        for item in (a1, a2, a3)
                    ],
                })

    semantic_cases_passed = sum(item["semantic_pass"] for item in results)
    historical_defined = historical_repeats if selected_case in {None, "historical"} else 0
    safety_names = {
        "ambiguity_no_commit",
        "unresolved_member_no_commit",
        "failed_semantic_turn_no_pollution",
    }
    payload = {
        "passed": bool(results) and all(item["semantic_pass"] for item in results),
        "semantic_cases_passed": semantic_cases_passed,
        "semantic_cases_defined": len(results),
        "source_mode": "real",
        "fallback_count": fallback_count,
        "state_pollution_count": sum(
            not item["semantic_pass"] for item in results if item["case"] in safety_names
        ),
        "historical_a1_a2_a3": f"{historical_passes}/{historical_defined}",
        "historical_details": historical_details,
        "known_downstream_issues": sorted({
            item["downstream_error_code"]
            for item in results
            if item["downstream_error_code"] == "dax_unplanned_group_by_dimension"
        }),
        "cases": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-repeats", type=int, default=5, choices=range(1, 6))
    parser.add_argument(
        "--case",
        choices=(
            "measure_canonical",
            "measure_alias",
            "dimension_alias",
            "filter_field_member_exact",
            "member_normalized",
            "time_current_month",
            "time_recent_months",
            "analysis_top_n",
            "known_filter_topn_holdout",
            "state_sequence",
            "filter_sequence",
            "historical",
        ),
        default=None,
    )
    args = parser.parse_args()
    return asyncio.run(_run(
        historical_repeats=args.historical_repeats,
        selected_case=args.case,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
