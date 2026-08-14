"""Production M2 acceptance through the formal Chat API and real Memory.

This runner is deliberately observational.  It may capture ToolGateway outputs
for the independent known-answer oracle, but it never supplies semantic state
or replaces committed Memory.  The single frozen failure-recovery turn uses a
deterministic QueryResult error and is reported separately from successful
Local MCP queries.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import Settings
from backend.app.harness.cases.benchmark_models import (
    KnownAnswerCaseSpec,
    MultiTurnExpectedSpec,
)
from backend.app.harness.cases.multi_turn_runner import MultiTurnBenchmarkRunner
from backend.app.harness.oracles.known_answer import BaselineSource
from backend.app.harness.tool_registry import TOOL_NAME_DAX
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.main import create_app
from backend.app.memory.models import (
    MemoryStatus,
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.schemas.data_contracts import DAXRequest, PowerBIError, QueryResult


class _TaskCountingProvider(LLMProvider):
    """Observe task kinds without retaining prompts or model responses."""

    def __init__(self, inner: LLMProvider):
        self._inner = inner
        self.task_counts = {task: 0 for task in LLMTask}

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def is_mock(self) -> bool:
        return self._inner.is_mock

    async def generate(self, request: LLMRequest, output_type: type) -> LLMResponse:
        self.task_counts[request.task] += 1
        return await self._inner.generate(request, output_type)


def exact_known_answer_schedule(
    cases: list[KnownAnswerCaseSpec],
) -> list[KnownAnswerCaseSpec]:
    """Return every committed case in order; oracle keys are never deduplicated."""
    return list(cases)


class ProductionE2ERunner:
    """Run exact known answers, formal conversations, and fresh a1-a2-a3."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.benchmark = MultiTurnBenchmarkRunner()

    async def run(self, *, historical_repeats: int = 10) -> dict[str, Any]:
        known_cases = exact_known_answer_schedule(
            self.benchmark.load_known_answer_cases()
        )
        conversations = self.benchmark.load_conversations()
        required_keys = {case.oracle_key for case in known_cases}
        required_keys.update(
            turn.expected.oracle_key
            for conversation in conversations
            for turn in conversation.turns
            if turn.expected.oracle_key is not None
        )
        configured, code, baseline_count = self.benchmark.oracle.validate_keys(
            BaselineSource.REAL_LOCAL, required_keys
        )
        if not configured:
            return {
                "passed": False,
                "status": code,
                "configured_baseline_count": baseline_count,
            }

        app = create_app(settings=self.settings)
        captured_results: dict[str, QueryResult] = {}
        captured_dax: dict[str, DAXRequest] = {}
        controlled_failures: set[str] = set()
        active_request_id = ""
        fallback_count = 0
        pollution_count = 0
        known_error_counts = {
            "dax_unplanned_group_by_dimension": 0,
            "dax_filter_structure_not_verifiable": 0,
        }

        known_results: list[dict[str, Any]] = []
        conversation_results: list[dict[str, Any]] = []
        historical_results: list[dict[str, Any]] = []
        deterministic_failure_gates = 0
        real_query_successes = 0
        top_n_known_executed = 0
        top_n_known_passed = 0
        top_n_boundary_ties_observed = 0
        top_n_tie_answers_truth_safe = 0

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            observed_provider = _TaskCountingProvider(service.llm_provider)
            service.llm_provider = observed_provider
            original_gateway_execute = service.tool_gateway.execute
            dax_tool = service.tool_gateway.get_tool(TOOL_NAME_DAX)
            original_dax_handler = dax_tool.handler
            if original_dax_handler is None:
                return {"passed": False, "status": "dax_handler_missing"}

            async def controlled_dax_handler(input_data: DAXRequest) -> QueryResult:
                if active_request_id in controlled_failures:
                    return QueryResult(
                        semantic_model_key=input_data.semantic_model_key,
                        request_id=input_data.request_id,
                        source_mode="real",
                        error=PowerBIError(
                            type="controlled_failure",
                            message="deterministic_failure_recovery_gate",
                            retryable=False,
                        ),
                    )
                return await original_dax_handler(input_data)

            dax_tool.handler = controlled_dax_handler

            async def observed_gateway_execute(
                tool_name: str,
                execution_context: Any,
                input_data: Any,
                trace: Any = None,
                controller: Any = None,
            ) -> Any:
                if tool_name == TOOL_NAME_DAX and isinstance(input_data, DAXRequest):
                    captured_dax[execution_context.request_id] = input_data.model_copy(
                        deep=True
                    )
                result = await original_gateway_execute(
                    tool_name,
                    execution_context,
                    input_data,
                    trace=trace,
                    controller=controller,
                )
                if isinstance(result, QueryResult):
                    captured_results[execution_context.request_id] = result.model_copy(
                        deep=True
                    )
                return result

            service.tool_gateway.execute = observed_gateway_execute
            transport = ASGITransport(app=app, raise_app_exceptions=True)

            async with AsyncClient(transport=transport, base_url="http://test") as client:

                async def execute(
                    *,
                    name: str,
                    message: str,
                    conversation_id: str,
                    expected: KnownAnswerCaseSpec | MultiTurnExpectedSpec,
                    inject_failure: bool = False,
                ) -> dict[str, Any]:
                    nonlocal active_request_id, fallback_count, pollution_count
                    request_id = f"m263-{name}-{uuid.uuid4().hex}"
                    before = await service.pipeline.get_latest_committed_memory(
                        conversation_id, RuntimeDataMode.REAL
                    )
                    before_pending = await service.pipeline.get_pending_clarification(
                        conversation_id, RuntimeDataMode.REAL
                    )
                    if inject_failure:
                        controlled_failures.add(request_id)
                    active_request_id = request_id
                    try:
                        response = await client.post(
                            "/api/v1/chat",
                            json={
                                "message": message,
                                "conversation_id": conversation_id,
                                "request_id": request_id,
                                "semantic_model_key": (
                                    self.settings.powerbi_local_semantic_model_key
                                ),
                            },
                        )
                    finally:
                        active_request_id = ""

                    body = response.json()
                    request_memory = await service.pipeline.get_memory_by_request_id(
                        request_id, RuntimeDataMode.REAL
                    )
                    latest = await service.pipeline.get_latest_committed_memory(
                        conversation_id, RuntimeDataMode.REAL
                    )
                    after_pending = await service.pipeline.get_pending_clarification(
                        conversation_id, RuntimeDataMode.REAL
                    )
                    query_result = captured_results.get(request_id)

                    sources = [body.get("source_mode")]
                    if query_result is not None:
                        sources.append(query_result.source_mode)
                    case_fallbacks = sum(source == "mock" for source in sources)
                    fallback_count += case_fallbacks

                    failure_text = " ".join(
                        str(value or "")
                        for value in (
                            body.get("error_type"),
                            request_memory.failure_reason if request_memory else None,
                        )
                    )
                    for signature in known_error_counts:
                        known_error_counts[signature] += len(
                            re.findall(rf"\b{re.escape(signature)}\b", failure_text)
                        )

                    unchanged = _same_committed(before, latest)
                    if not body.get("memory_commit") and not unchanged:
                        pollution_count += 1

                    return {
                        "name": name,
                        "http_status": response.status_code,
                        "body": body,
                        "request_id": request_id,
                        "request_memory": request_memory,
                        "before": before,
                        "before_pending": before_pending,
                        "latest": latest,
                        "after_pending": after_pending,
                        "query_result": query_result,
                        "dax_request": captured_dax.get(request_id),
                        "fallback_count": case_fallbacks,
                        "unchanged": unchanged,
                        "expected": expected,
                    }

                # Every frozen prompt executes independently, even when an oracle
                # key has appeared in a conversation or another known case.
                for case in known_cases:
                    item = await execute(
                        name=f"known-{case.id}",
                        message=case.message,
                        conversation_id=f"m263-known-{case.id}-{uuid.uuid4().hex}",
                        expected=case,
                    )
                    passed, oracle_code = self._evaluate_success(item, case)
                    real_query_successes += passed
                    if case.expected_top_n is not None:
                        top_n_known_executed += 1
                        top_n_known_passed += passed
                        tie_observed = passed and _topn_boundary_tie_observed(
                            item["query_result"], case
                        )
                        if tie_observed:
                            top_n_boundary_ties_observed += 1
                            top_n_tie_answers_truth_safe += (
                                _strict_rank_claim_absent(item["body"].get("answer"))
                            )
                    known_results.append(
                        {
                            "case": case.id,
                            "holdout": case.holdout,
                            "passed": passed,
                            "oracle_code": oracle_code,
                            "terminal_state": item["body"].get("terminal_state"),
                            "failure_stage": (
                                item["request_memory"].failure_stage
                                if item["request_memory"] else None
                            ),
                        }
                    )

                for conversation in conversations:
                    conversation_id = (
                        f"m263-{conversation.id}-{uuid.uuid4().hex}"
                    )
                    turn_results: list[dict[str, Any]] = []
                    for turn in conversation.turns:
                        inject_failure = turn.fixture_key == "controlled_failure"
                        item = await execute(
                            name=f"{conversation.id}-{turn.turn_id}",
                            # The frozen fixture text intentionally names no
                            # business semantics.  Re-execute the last fully
                            # specified successful query and inject a structured
                            # result error; report this separately from Real MCP.
                            message=(
                                "按产品看销售额"
                                if inject_failure else turn.message
                            ),
                            conversation_id=conversation_id,
                            expected=turn.expected,
                            inject_failure=inject_failure,
                        )
                        if inject_failure:
                            deterministic_failure_gates += 1
                            passed = self._evaluate_failure(item, turn.expected)
                            oracle_code = "not_applicable"
                        elif turn.expected.expected_terminal_state == "completed":
                            passed, oracle_code = self._evaluate_success(
                                item, turn.expected
                            )
                            real_query_successes += passed
                        else:
                            passed = self._evaluate_clarification(
                                item, turn.expected
                            )
                            oracle_code = "not_applicable"
                        turn_results.append(
                            {
                                "turn": turn.turn_id,
                                "passed": passed,
                                "oracle_code": oracle_code,
                                "kind": (
                                    "deterministic_failure_recovery"
                                    if inject_failure
                                    else "real"
                                ),
                                "terminal_state": item["body"].get("terminal_state"),
                                "failure_stage": (
                                    item["request_memory"].failure_stage
                                    if item["request_memory"] else None
                                ),
                            }
                        )
                    conversation_results.append(
                        {
                            "conversation": conversation.id,
                            "passed": bool(turn_results)
                            and all(item["passed"] for item in turn_results),
                            "turns": turn_results,
                        }
                    )

                historical_expected = (
                    KnownAnswerCaseSpec(
                        id="historical_a1",
                        message="按类别看销售额",
                        expected_measure="Total Sales",
                        expected_dimensions=["Category"],
                        oracle_key="sales_by_category",
                    ),
                    KnownAnswerCaseSpec(
                        id="historical_a2",
                        message="只看 Electronics",
                        expected_measure="Total Sales",
                        expected_dimensions=["Category"],
                        expected_filters=[
                            {"field": "Category", "operator": "eq", "value": "Electronics"}
                        ],
                        oracle_key="electronics_sales_by_category",
                    ),
                    KnownAnswerCaseSpec(
                        id="historical_a3",
                        message="那销量呢",
                        expected_measure="Total Quantity",
                        expected_dimensions=["Category"],
                        expected_filters=[
                            {"field": "Category", "operator": "eq", "value": "Electronics"}
                        ],
                        oracle_key="electronics_quantity_by_category",
                    ),
                )
                for repeat in range(1, historical_repeats + 1):
                    conversation_id = f"m263-a123-{repeat}-{uuid.uuid4().hex}"
                    turns: list[bool] = []
                    versions: list[int | None] = []
                    for case in historical_expected:
                        item = await execute(
                            name=f"a123-{repeat}-{case.id}",
                            message=case.message,
                            conversation_id=conversation_id,
                            expected=case,
                        )
                        passed, _ = self._evaluate_success(item, case)
                        real_query_successes += passed
                        turns.append(passed)
                        latest = item["latest"]
                        versions.append(latest.memory_version if latest else None)
                    historical_results.append(
                        {
                            "repeat": repeat,
                            "passed": all(turns) and versions == [1, 2, 3],
                            "memory_versions": versions,
                        }
                    )

        known_passed = sum(item["passed"] for item in known_results)
        holdouts = [item for item in known_results if item["holdout"]]
        conversation_turns = [
            turn
            for conversation in conversation_results
            for turn in conversation["turns"]
        ]
        payload = {
            "passed": bool(known_results)
            and all(item["passed"] for item in known_results)
            and bool(conversation_results)
            and all(item["passed"] for item in conversation_results)
            and bool(historical_results)
            and all(item["passed"] for item in historical_results)
            and fallback_count == 0
            and pollution_count == 0
            and top_n_known_executed > 0
            and top_n_known_passed == top_n_known_executed
            and top_n_tie_answers_truth_safe == top_n_boundary_ties_observed
            and observed_provider.task_counts[LLMTask.DAX] == 0
            and observed_provider.task_counts[LLMTask.ANSWER] == 0
            and all(count == 0 for count in known_error_counts.values()),
            "status": "pass",
            "known_exact_executed": len(known_results),
            "known_exact_passed": known_passed,
            "holdouts_executed": len(holdouts),
            "holdouts_passed": sum(item["passed"] for item in holdouts),
            "conversations_defined": len(conversation_results),
            "conversations_passed": sum(
                item["passed"] for item in conversation_results
            ),
            "turns_defined": len(conversation_turns),
            "turns_passed": sum(item["passed"] for item in conversation_turns),
            "successful_real_query_turns": real_query_successes,
            "deterministic_failure_recovery_gates": deterministic_failure_gates,
            "top_n_known_cases_executed": top_n_known_executed,
            "top_n_known_cases_passed": top_n_known_passed,
            "top_n_boundary_tie_cases_observed": top_n_boundary_ties_observed,
            "top_n_tie_answers_truth_safe": top_n_tie_answers_truth_safe,
            "historical_a1_a2_a3": (
                f"{sum(item['passed'] for item in historical_results)}/"
                f"{len(historical_results)}"
            ),
            "fallback_count": fallback_count,
            "state_pollution_count": pollution_count,
            "llm_task_counts": {
                task.value: observed_provider.task_counts[task] for task in LLMTask
            },
            "dax_llm_calls": observed_provider.task_counts[LLMTask.DAX],
            "answer_llm_calls": observed_provider.task_counts[LLMTask.ANSWER],
            "known_dax_error_counts": known_error_counts,
            "known_cases": known_results,
            "conversations": conversation_results,
            "historical": historical_results,
        }
        if not payload["passed"]:
            payload["status"] = "acceptance_failed"
        return payload

    def _evaluate_success(
        self,
        item: dict[str, Any],
        expected: KnownAnswerCaseSpec | MultiTurnExpectedSpec,
    ) -> tuple[bool, str]:
        body = item["body"]
        memory: StructuredWorkMemory | None = item["request_memory"]
        latest: StructuredWorkMemory | None = item["latest"]
        result: QueryResult | None = item["query_result"]
        audit = body.get("execution_audit") or {}
        plan = audit.get("canonical_query_plan") or {}
        oracle_key = expected.oracle_key or ""
        oracle = self.benchmark.oracle.evaluate(
            oracle_key, result, source=BaselineSource.REAL_LOCAL
        )
        passed = bool(
            item["http_status"] == 200
            and body.get("terminal_state") == "completed"
            and body.get("memory_commit") is True
            and body.get("is_mock") is False
            and body.get("source_mode") == "real"
            and item["fallback_count"] == 0
            and result is not None
            and result.error is None
            and result.source_mode == "real"
            and _plan_matches(plan, expected)
            and audit.get("deterministic_dax") is True
            and audit.get("layer3_pass") is True
            and audit.get("query_result_success") is True
            and audit.get("source_mode") == "real"
            and bool(audit.get("verified_fact_set_id"))
            and audit.get("verified_fact_count", 0) > 0
            and audit.get("factual_validation_pass") is True
            and audit.get("llm_dax_call_count") == 0
            and memory is not None
            and memory.state_status == MemoryStatus.COMMITTED
            and latest is not None
            and latest.request_id == item["request_id"]
            and latest.memory_version == memory.memory_version
            and audit.get("memory_version") == latest.memory_version
            and item["after_pending"] is None
            and oracle.passed
        )
        return passed, oracle.code

    @staticmethod
    def _evaluate_clarification(
        item: dict[str, Any], expected: MultiTurnExpectedSpec
    ) -> bool:
        body = item["body"]
        memory: StructuredWorkMemory | None = item["request_memory"]
        pending: PendingClarificationContext | None = item["after_pending"]
        audit = body.get("execution_audit") or {}
        return bool(
            item["http_status"] == 200
            and body.get("terminal_state") == expected.expected_terminal_state
            and body.get("memory_commit") is False
            and body.get("source_mode") == "real"
            and item["fallback_count"] == 0
            and item["unchanged"]
            and (memory is None or memory.state_status == MemoryStatus.FAILED)
            and item["query_result"] is None
            and pending is not None
            and pending.missing_slots == expected.expected_pending_missing_slots
            and pending.measures == expected.expected_pending_measures
            and pending.dimensions == expected.expected_pending_dimensions
            and audit.get("pending_clarification") is True
            and audit.get("clarification_chain_id") == pending.chain_id
            and audit.get("missing_slots") == pending.missing_slots
            and audit.get("committed_memory_mutated") is False
        )

    @staticmethod
    def _evaluate_failure(
        item: dict[str, Any], expected: MultiTurnExpectedSpec
    ) -> bool:
        body = item["body"]
        memory: StructuredWorkMemory | None = item["request_memory"]
        dax_request: DAXRequest | None = item["dax_request"]
        result: QueryResult | None = item["query_result"]
        return bool(
            item["http_status"] == 200
            and body.get("terminal_state") == expected.expected_terminal_state
            and body.get("memory_commit") is False
            and body.get("source_mode") == "real"
            and item["fallback_count"] == 0
            and item["unchanged"]
            and dax_request is not None
            and result is not None
            and result.error is not None
            and result.error.type == "controlled_failure"
            and memory is not None
            and memory.state_status == MemoryStatus.FAILED
            and memory.failure_stage == expected.expected_failure_stage
        )


def _plan_matches(
    plan: dict[str, Any], expected: KnownAnswerCaseSpec | MultiTurnExpectedSpec
) -> bool:
    expected_measure = expected.expected_measure
    expected_filters = sorted(
        (item.field, item.operator.value, str(item.value))
        for item in expected.expected_filters
    )
    actual_filters = sorted(
        (
            str(item.get("field")),
            str(item.get("operator")),
            str(item.get("value")),
        )
        for item in plan.get("filters", [])
        if isinstance(item, dict)
    )
    return bool(
        expected_measure
        and plan.get("grounding_authority") == "semantic_catalog"
        and plan.get("measures") == [expected_measure]
        and plan.get("dimensions", []) == expected.expected_dimensions
        and actual_filters == expected_filters
        and plan.get("sort") == expected.expected_sort
        and plan.get("top_n") == expected.expected_top_n
        and plan.get("comparison_mode") is None
    )


def _same_committed(
    before: StructuredWorkMemory | None, after: StructuredWorkMemory | None
) -> bool:
    if before is None or after is None:
        return before is None and after is None
    return bool(
        before.request_id == after.request_id
        and before.memory_version == after.memory_version
        and before.last_query_plan == after.last_query_plan
        and before.last_query_result_id == after.last_query_result_id
    )


def _topn_boundary_tie_observed(
    result: QueryResult | None,
    expected: KnownAnswerCaseSpec,
) -> bool:
    """Detect an observed rows-beyond-N boundary tie without exposing values."""

    top_n = expected.expected_top_n
    metric = f"[{expected.expected_measure}]"
    if (
        result is None
        or top_n is None
        or len(result.rows) <= top_n
        or metric not in result.columns
    ):
        return False
    metric_index = result.columns.index(metric)
    try:
        boundary = Decimal(str(result.rows[top_n - 1][metric_index]))
        return any(
            Decimal(str(row[metric_index])) == boundary
            for row in result.rows[top_n:]
        )
    except (InvalidOperation, IndexError, TypeError, ValueError):
        return False


def _strict_rank_claim_absent(answer: Any) -> bool:
    """A tied TopN answer may describe result order, never strict semantic rank."""

    text = str(answer or "")
    return bool(text) and re.search(r"第\s*\d+\s*位|排名|位居", text) is None
