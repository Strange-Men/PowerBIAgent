"""API-first offline runner for the formal Real multi-turn benchmark.

The runner calls ``create_app -> /api/v1/chat`` with one conversation ID and
unique request IDs. A scripted Fake provider/adapter supplies fictional data;
the production TurnPipeline, ToolGateway, Memory and API paths remain intact.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.mock_turn_service import MockScenarioSelection
from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.harness.cases.benchmark_models import (
    ConversationSpec,
    KnownAnswerCaseSpec,
    MultiTurnSpec,
)
from backend.app.harness.oracles.known_answer import (
    BaselineSource,
    KnownAnswerOracle,
    OracleEvaluation,
)
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.models import FilterSpec, IntentSpec, IntentType
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse
from backend.app.main import create_app
from backend.app.memory.models import MemoryStatus, RuntimeDataMode, StructuredWorkMemory
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    ColumnSchema,
    DAXRequest,
    MeasureSchema,
    QueryPlan,
    QueryResult,
    SemanticModelSchema,
    StructuredFilter,
    TableSchema,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONVERSATIONS_PATH = PROJECT_ROOT / "harness" / "cases" / "multi_turn_conversations.yaml"
DEFAULT_KNOWN_ANSWER_CASES_PATH = PROJECT_ROOT / "harness" / "cases" / "known_answer_cases.yaml"
DEFAULT_EXAMPLE_BASELINE_PATH = PROJECT_ROOT / "harness" / "baselines" / "example_known_answers.yaml"
DEFAULT_REAL_BASELINE_PATH = PROJECT_ROOT / "local_state" / "m2_known_answers.yaml"


class TurnEvaluation(BaseModel):
    turn_id: str
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    mismatches: list[str] = Field(default_factory=list)
    oracle: OracleEvaluation | None = None

    model_config = ConfigDict(extra="forbid")


class ConversationEvaluation(BaseModel):
    conversation_id: str
    passed: bool
    turns: list[TurnEvaluation]

    model_config = ConfigDict(extra="forbid")


class BenchmarkSummary(BaseModel):
    passed: bool
    conversations_defined: int
    conversations_passed: int
    turns_defined: int
    turns_passed: int
    deepseek_real_calls: int = 0
    local_mcp_real_calls: int = 0
    conversations: list[ConversationEvaluation]

    model_config = ConfigDict(extra="forbid")


class _ScriptedProvider(LLMProvider):
    PROVIDER_NAME = "m261_offline_fake_llm"

    def __init__(self, scripted: dict[str, dict[type[BaseModel], BaseModel]]):
        self._scripted = scripted
        self.active_fixture_key = ""

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return True

    async def generate(
        self, request: LLMRequest, output_type: type[BaseModel]
    ) -> LLMResponse:
        fixture = self._scripted.get(self.active_fixture_key, {})
        structured = fixture.get(output_type)
        if structured is None:
            raise RuntimeError(
                f"offline fixture '{self.active_fixture_key}' lacks {output_type.__name__}"
            )
        value = structured.model_copy(deep=True)
        return LLMResponse(
            content=value.model_dump_json(),
            structured=value,
            model="offline-fake",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )


class _ScriptedPowerBIAdapter(MockPowerBIAdapter):
    PROVIDER_NAME = "m261_offline_fake_powerbi"

    def __init__(self, results: dict[str, QueryResult]):
        super().__init__()
        self._offline_results = results
        self.active_fixture_key = ""
        self.last_query_result: QueryResult | None = None

    async def get_semantic_model_schema(self, semantic_model_key: str) -> SemanticModelSchema:
        return _offline_schema()

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        result = self._offline_results[self.active_fixture_key].model_copy(deep=True)
        result.request_id = request.request_id
        self.last_query_result = result
        return result


class MultiTurnBenchmarkRunner:
    def __init__(
        self,
        *,
        conversations_path: Path = DEFAULT_CONVERSATIONS_PATH,
        known_answer_cases_path: Path = DEFAULT_KNOWN_ANSWER_CASES_PATH,
        example_baseline_path: Path = DEFAULT_EXAMPLE_BASELINE_PATH,
        real_baseline_path: Path = DEFAULT_REAL_BASELINE_PATH,
    ):
        self.conversations_path = Path(conversations_path)
        self.known_answer_cases_path = Path(known_answer_cases_path)
        self.oracle = KnownAnswerOracle(example_baseline_path, real_baseline_path)

    def load_conversations(self) -> list[ConversationSpec]:
        raw = yaml.safe_load(self.conversations_path.read_text(encoding="utf-8"))
        return [ConversationSpec.model_validate(item) for item in raw["conversations"]]

    def load_known_answer_cases(self) -> list[KnownAnswerCaseSpec]:
        raw = yaml.safe_load(self.known_answer_cases_path.read_text(encoding="utf-8"))
        return [KnownAnswerCaseSpec.model_validate(item) for item in raw["cases"]]

    async def run_offline(self) -> BenchmarkSummary:
        conversations = self.load_conversations()
        fixtures, query_results = _offline_fixtures()
        evaluations: list[ConversationEvaluation] = []
        for conversation in conversations:
            evaluations.append(
                await self._run_conversation_offline(
                    conversation,
                    fixtures,
                    query_results,
                )
            )
        turns = [turn for item in evaluations for turn in item.turns]
        return BenchmarkSummary(
            passed=bool(evaluations) and all(item.passed for item in evaluations),
            conversations_defined=len(evaluations),
            conversations_passed=sum(item.passed for item in evaluations),
            turns_defined=len(turns),
            turns_passed=sum(turn.passed for turn in turns),
            conversations=evaluations,
        )

    async def _run_conversation_offline(
        self,
        conversation: ConversationSpec,
        fixtures: dict[str, dict[type[BaseModel], BaseModel]],
        query_results: dict[str, QueryResult],
    ) -> ConversationEvaluation:
        provider = _ScriptedProvider(fixtures)
        adapter = _ScriptedPowerBIAdapter(query_results)
        settings = Settings(llm_mode=LLMMode.MOCK, powerbi_mode=PowerBIMode.MOCK)
        app = create_app(settings=settings)

        async with app.router.lifespan_context(app):
            service = app.state.turn_service
            service.llm_provider = provider
            service.powerbi = adapter
            service.tool_gateway = service._build_tool_gateway()

            original_execute = service.execute

            async def _execute_with_fixture(*args: Any, **kwargs: Any) -> dict[str, Any]:
                key = provider.active_fixture_key
                return await original_execute(
                    *args,
                    scenario=MockScenarioSelection(
                        intent_key=key,
                        query_plan_key=key,
                        dax_key=key,
                        powerbi_key=key,
                        response_key=key,
                    ),
                    **kwargs,
                )

            service.execute = _execute_with_fixture
            transport = ASGITransport(app=app)
            turn_evaluations: list[TurnEvaluation] = []
            previous_committed: StructuredWorkMemory | None = None
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for turn in conversation.turns:
                    provider.active_fixture_key = turn.fixture_key
                    adapter.active_fixture_key = turn.fixture_key
                    response = await client.post(
                        "/api/v1/chat",
                        json={
                            "message": turn.message,
                            "conversation_id": conversation.conversation_id,
                            "request_id": turn.request_id,
                            "semantic_model_key": "mock_sales_model",
                        },
                    )
                    actual = response.json()
                    request_memory = await service.pipeline.get_memory_by_request_id(
                        turn.request_id, RuntimeDataMode.MOCK
                    )
                    latest = await service.pipeline.get_latest_committed_memory(
                        conversation.conversation_id, RuntimeDataMode.MOCK
                    )
                    evaluation = self._evaluate_turn(
                        turn,
                        response.status_code,
                        actual,
                        request_memory,
                        latest,
                        previous_committed,
                        adapter.last_query_result,
                        fixtures[turn.fixture_key].get(AnswerSpec),
                    )
                    turn_evaluations.append(evaluation)
                    if latest is not None:
                        previous_committed = latest.model_copy(deep=True)

        return self.score_conversation(conversation.id, turn_evaluations)

    @staticmethod
    def score_conversation(
        conversation_id: str, turns: list[TurnEvaluation]
    ) -> ConversationEvaluation:
        """SParC-style interaction match: every turn must pass."""
        return ConversationEvaluation(
            conversation_id=conversation_id,
            passed=bool(turns) and all(item.passed for item in turns),
            turns=turns,
        )

    def _evaluate_turn(
        self,
        turn: MultiTurnSpec,
        http_status: int,
        actual: dict[str, Any],
        request_memory: StructuredWorkMemory | None,
        latest: StructuredWorkMemory | None,
        previous_committed: StructuredWorkMemory | None,
        query_result: QueryResult | None,
        answer: BaseModel | None,
    ) -> TurnEvaluation:
        expected = turn.expected
        expected_filters = [item.model_dump(mode="json") for item in expected.expected_filters]
        actual_filters = [
            {**item, "operator": getattr(item.get("operator"), "value", item.get("operator"))}
            for item in (request_memory.filters if request_memory else [])
        ]
        checks = {
            "http_200": http_status == 200,
            "intent": actual.get("intent") == expected.expected_intent,
            "terminal_state": actual.get("terminal_state") == expected.expected_terminal_state,
            "tool_sequence": actual.get("tool_sequence", []) == expected.expected_tool_sequence,
            "memory_commit": actual.get("memory_commit") is expected.expected_memory_commit,
        }

        is_data_success = (
            expected.expected_intent == "data_question"
            and expected.expected_terminal_state == "completed"
        )
        oracle_evaluation: OracleEvaluation | None = None
        if is_data_success:
            plan = request_memory.last_query_plan if request_memory else None
            plan_obj = QueryPlan.model_validate(plan) if plan else None
            schema = _offline_schema()
            layer2 = ValidationService().validate_query_plan(plan_obj, schema) if plan_obj else None
            layer3 = (
                ValidationService().validate_dax_query_plan_consistency(
                    DAXRequest(
                        semantic_model_key=plan_obj.semantic_model_key,
                        dax=request_memory.last_dax or "",
                    ),
                    plan_obj,
                    schema,
                )
                if plan_obj and request_memory and request_memory.last_dax
                else None
            )
            answer_provenance = (
                ValidationService().validate_answer_strict(answer, query_result)
                if isinstance(answer, AnswerSpec) and query_result is not None
                else None
            )
            oracle_evaluation = self.oracle.evaluate(
                expected.oracle_key or "", query_result, source=BaselineSource.EXAMPLE
            )
            checks.update({
                "query_plan_measure": bool(plan_obj and plan_obj.measures == [expected.expected_measure]),
                "query_plan_dimensions": bool(plan_obj and plan_obj.dimensions == expected.expected_dimensions),
                "query_plan_filters": bool(
                    plan_obj
                    and [item.model_dump(mode="json") for item in plan_obj.filters]
                    == expected_filters
                ),
                "query_plan_sort_top_n": bool(
                    plan_obj
                    and plan_obj.sort == expected.expected_sort
                    and plan_obj.top_n == expected.expected_top_n
                ),
                "layer2": bool(layer2 and layer2.is_valid),
                "layer3": bool(layer3 and layer3.is_valid),
                "query_result": bool(query_result and query_result.error is None),
                "formal_source_mode_contract": expected.expected_source_mode == "real",
                "offline_source_is_mock": bool(
                    query_result
                    and query_result.source_mode == "mock"
                    and actual.get("source_mode") == "mock"
                ),
                "oracle": oracle_evaluation.passed,
                "answer_provenance": bool(answer_provenance and answer_provenance.is_valid),
                "memory_committed": bool(
                    request_memory and request_memory.state_status == MemoryStatus.COMMITTED
                ),
                "inheritance": self._inheritance_matches(
                    expected.expected_inheritance,
                    request_memory,
                    previous_committed,
                ),
                "real_to_mock_fallback_deferred_to_m2_6_2": True,
            })
        elif expected.expected_intent in {"clarification", "unsupported"}:
            checks.update({
                "no_powerbi_execute": "execute_dax" not in actual.get("tool_sequence", []),
                "no_memory_record": request_memory is None,
            })
        else:
            checks.update({
                "failed_memory_record": bool(
                    request_memory and request_memory.state_status == MemoryStatus.FAILED
                ),
                "failure_stage": bool(
                    request_memory
                    and request_memory.failure_stage == expected.expected_failure_stage
                ),
                "last_committed_unchanged": bool(
                    previous_committed
                    and latest
                    and latest.request_id == previous_committed.request_id
                    and latest.memory_version == previous_committed.memory_version
                ),
                "inheritance": self._inheritance_matches(
                    expected.expected_inheritance,
                    request_memory,
                    previous_committed,
                ),
            })

        mismatches = [name for name, passed in checks.items() if not passed]
        return TurnEvaluation(
            turn_id=turn.turn_id,
            passed=not mismatches,
            checks=checks,
            mismatches=mismatches,
            oracle=oracle_evaluation,
        )

    @staticmethod
    def _inheritance_matches(
        expectation: str,
        request_memory: StructuredWorkMemory | None,
        previous_committed: StructuredWorkMemory | None,
    ) -> bool:
        if request_memory is None:
            return expectation == "none"
        if expectation in {"none", "clarification_resolution"}:
            return request_memory.base_memory_version == 0
        return bool(
            previous_committed
            and request_memory.base_memory_version == previous_committed.memory_version
        )


def _offline_fixtures() -> tuple[
    dict[str, dict[type[BaseModel], BaseModel]], dict[str, QueryResult]
]:
    plans: dict[str, QueryPlan] = {
        "sales_by_category": _plan("Total Sales", ["Category"]),
        "electronics_sales_by_category": _plan(
            "Total Sales", ["Category"], filters=[("Category", "Electronics")]
        ),
        "electronics_quantity_by_category": _plan(
            "Total Quantity", ["Category"], filters=[("Category", "Electronics")]
        ),
        "sales_by_product": _plan("Total Sales", ["Product"]),
        "top3_products_sales": _plan(
            "Total Sales", ["Product"], sort="desc", top_n=3
        ),
        "electronics_sales": _plan(
            "Total Sales", filters=[("Category", "Electronics")]
        ),
        "furniture_sales": _plan(
            "Total Sales", filters=[("Category", "Furniture")]
        ),
        "quantity_by_product": _plan("Total Quantity", ["Product"]),
        "top_product_sales_after_clarification": _plan(
            "Total Sales", ["Product"], sort="desc", top_n=1
        ),
        "controlled_failure": _plan("Total Sales", ["Product"]),
    }
    query_results = _offline_query_results()
    fixtures: dict[str, dict[type[BaseModel], BaseModel]] = {}
    for key, plan in plans.items():
        result = query_results[key]
        fixtures[key] = {
            IntentSpec: _intent_for_plan(plan),
            QueryPlan: plan,
            DAXRequest: _dax_for_plan(plan),
            AnswerSpec: _answer_for_result(result),
        }
    fixtures["ambiguous_best"] = {
        IntentSpec: IntentSpec(
            intent=IntentType.CLARIFICATION,
            confidence=0.80,
            normalized_question="哪个表现最好？",
            needs_clarification=True,
            clarification_question="请明确按销售额还是总数量判断。",
        )
    }
    fixtures["partial_sales_clarification"] = {
        IntentSpec: IntentSpec(
            intent=IntentType.CLARIFICATION,
            confidence=0.95,
            normalized_question="按销售额",
            detected_measures=["Total Sales"],
            needs_clarification=True,
            clarification_question="请明确要按哪个分析维度比较。",
        )
    }
    return fixtures, query_results


def _offline_schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="M2.6.1 Offline Fictional Model",
        key="mock_sales_model",
        tables=[
            TableSchema(
                name="Product",
                columns=[
                    ColumnSchema(name="Category", data_type="string"),
                    ColumnSchema(name="Product", data_type="string"),
                ],
                measures=[
                    MeasureSchema(name="Total Sales", data_type="decimal"),
                    MeasureSchema(name="Total Quantity", data_type="int64"),
                ],
            )
        ],
    )


def _plan(
    measure: str,
    dimensions: list[str] | None = None,
    *,
    filters: list[tuple[str, str]] | None = None,
    sort: str | None = None,
    top_n: int | None = None,
) -> QueryPlan:
    return QueryPlan(
        normalized_question="offline fictional benchmark",
        semantic_model_key="mock_sales_model",
        measures=[measure],
        dimensions=dimensions or [],
        filters=[StructuredFilter(field=field, value=value) for field, value in filters or []],
        sort=sort,
        top_n=top_n,
        is_mock=True,
    )


def _intent_for_plan(plan: QueryPlan) -> IntentSpec:
    return IntentSpec(
        intent=IntentType.DATA_QUESTION,
        confidence=1.0,
        normalized_question=plan.normalized_question,
        detected_measures=plan.measures,
        detected_dimensions=plan.dimensions,
        detected_filters=[
            FilterSpec(field=item.field, operator=item.operator.value, value=item.value)
            for item in plan.filters
        ],
        inherited_context=plan.inherited_context,
    )


def _dax_for_plan(plan: QueryPlan) -> DAXRequest:
    filters = "".join(
        f'TREATAS({{"{item.value}"}}, \'Product\'[{item.field}]), '
        for item in plan.filters
    )
    dimensions = "".join(f"'Product'[{item}], " for item in plan.dimensions)
    core = (
        f"SUMMARIZECOLUMNS({dimensions}{filters}"
        f'"{plan.measures[0]}", [{plan.measures[0]}])'
    )
    if plan.top_n is not None:
        dax = (
            f"EVALUATE TOPN({plan.top_n}, {core}, [{plan.measures[0]}], {plan.sort}) "
            f"ORDER BY [{plan.measures[0]}] {plan.sort}"
        )
    else:
        dax = f"EVALUATE {core}"
    return DAXRequest(
        semantic_model_key="mock_sales_model", dax=dax, is_mock=True
    )


def _answer_for_result(result: QueryResult) -> AnswerSpec:
    metrics: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    numeric_columns = [
        column for index, column in enumerate(result.columns)
        if any(
            isinstance(row[index], (int, float)) and not isinstance(row[index], bool)
            for row in result.rows
        )
    ]
    if len(result.rows) == 1 and numeric_columns:
        column = numeric_columns[0]
        value = result.rows[0][result.columns.index(column)]
        metrics[column] = value
        provenance[column] = {"source_field": column, "aggregation": "direct"}
    return AnswerSpec(
        answer="离线虚构结果已返回。",
        metrics=metrics,
        evidence={
            "result_id": result.result_id,
            "semantic_model_key": result.semantic_model_key,
            "row_count": result.row_count,
            "source_mode": result.source_mode,
            "metric_provenance": provenance,
        },
        semantic_model_key=result.semantic_model_key,
        source_mode=result.source_mode,
    )


def _offline_query_results() -> dict[str, QueryResult]:
    def result(columns: list[str], rows: list[list[Any]]) -> QueryResult:
        return QueryResult(
            semantic_model_key="mock_sales_model",
            columns=columns,
            rows=copy.deepcopy(rows),
            row_count=len(rows),
            source_mode="mock",
        )

    return {
        "sales_by_category": result(
            ["Category", "[Total Sales]"],
            [["Office", 260.10], ["Electronics", 410.10], ["Furniture", 330.05]],
        ),
        "electronics_sales_by_category": result(
            ["Category", "[Total Sales]"], [["Electronics", 410.10]]
        ),
        "electronics_quantity_by_category": result(
            ["Category", "[Total Quantity]"], [["Electronics", 18]]
        ),
        "sales_by_product": result(
            ["Product", "[Total Sales]"],
            [["Gamma", 200.00], ["Alpha", 300.00], ["Beta", 250.00]],
        ),
        "top3_products_sales": result(
            ["Product", "[Total Sales]"],
            [["Alpha", 300.00], ["Beta", 250.00], ["Gamma", 200.00], ["Delta", 200.00]],
        ),
        "electronics_sales": result(["[Total Sales]"], [[410.10]]),
        "furniture_sales": result(["[Total Sales]"], [[330.05]]),
        "quantity_by_product": result(
            ["Product", "[Total Quantity]"],
            [["Gamma", 9], ["Alpha", 13], ["Beta", 11]],
        ),
        "top_product_sales_after_clarification": result(
            ["Product", "[Total Sales]"], [["Alpha", 300.00]]
        ),
        "controlled_failure": QueryResult(
            semantic_model_key="mock_sales_model",
            columns=[],
            rows=[],
            row_count=0,
            source_mode="mock",
            error={"type": "dax_error", "message": "controlled offline failure"},
        ),
    }
