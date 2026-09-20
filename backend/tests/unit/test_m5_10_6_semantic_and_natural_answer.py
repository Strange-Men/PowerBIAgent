"""M5.10.6 failure-first contracts for open language and natural facts."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.answer.natural import NaturalAnswerComposer, NaturalAnswerDraft
from backend.app.facts import FactBoundedAnswerBuilder, FactOutputValidator, VerifiedFactSetBuilder
from backend.app.facts.availability import (
    AvailabilityProbeBuilder,
    AvailableDataHorizon,
    DataAvailabilityContext,
    DataHorizonStatus,
)
from backend.app.intent.question_router import QuestionRoute, QuestionRouter
from backend.app.intent.semantic_interpreter import (
    LLMSemanticInterpreter,
    SemanticCoverageDecision,
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    CanonicalQueryPlan,
    QueryResult,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


class _QueuedProvider(LLMProvider):
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[LLMRequest] = []

    async def generate(self, request, output_type):
        self.calls.append(request)
        structured = self.responses.pop(0)
        assert isinstance(structured, output_type)
        return LLMResponse(content="{}", structured=structured, model="fixture")

    @property
    def provider_name(self) -> str:
        return "fixture"

    @property
    def is_mock(self) -> bool:
        return False


def _plan(**updates) -> CanonicalQueryPlan:
    values = {
        "normalized_question": "query",
        "semantic_model_key": "model",
        "query_shape": QueryShape.SCALAR,
        "measures": ["Total Sales"],
    }
    values.update(updates)
    return CanonicalQueryPlan(**values)


def _result(columns: list[str], rows: list[list[object]], *, result_id: str = "r1") -> QueryResult:
    return QueryResult(
        result_id=result_id,
        semantic_model_key="model",
        columns=columns,
        rows=rows,
        row_count=len(rows),
        source_mode="real",
    )


def test_unseen_general_language_enters_open_interpreter_not_business_default():
    router = QuestionRouter()
    for text in (
        "我今天有点累，陪我随便聊聊",
        "帮我把这句话说得更自然一点",
        "为什么平均值容易受极端值影响",
        "帮我想个标题",
        "在不改动数据的前提下，你通常怎样帮助我理解一张报表？",
        "顺便说说，为什么复盘有用？",
    ):
        assert router.route(text).route is QuestionRoute.LLM_SEMANTIC_INTERPRETATION


def test_semantic_frame_mode_is_the_only_general_business_boundary():
    business = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="销售额"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
        ),
    )
    general = SemanticFrame(
        mode=SemanticInterpretationMode.GENERAL,
        general_answer="当然，我们聊点轻松的。",
    )
    assert business.mode is SemanticInterpretationMode.DATA
    assert general.mode is SemanticInterpretationMode.GENERAL


@pytest.mark.asyncio
async def test_open_interpreter_emits_one_frame_then_veto_only_coverage():
    provider = _QueuedProvider(
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            query_shape=QueryShape.SCALAR,
            measure_mentions=("华南销售额",),
            evidence_spans=(
                SemanticEvidenceSpan(slot="query_shape", text="看一下"),
                SemanticEvidenceSpan(slot="measure", text="华南销售额"),
            ),
        ),
        SemanticCoverageDecision(decision="ACCEPT"),
    )
    draft = await LLMSemanticInterpreter(provider).interpret(
        "谢谢，再帮我看一下华南销售额"
    )

    assert draft.mode is SemanticInterpretationMode.DATA
    assert draft.general_answer == ""
    assert [call.task for call in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]
    assert "华南销售额" in provider.calls[0].messages[-1]["content"]
    assert provider.calls[0].metadata == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_input", "frame", "expected_mode"),
    [
        (
            "你怎样帮助我理解一张报表",
            SemanticFrame(
                mode=SemanticInterpretationMode.GENERAL,
                general_answer="我可以解释指标、筛选、趋势和需要核验的问题。",
            ),
            SemanticInterpretationMode.GENERAL,
        ),
        (
            "帮我分析这张报表里今年销售额为什么下降",
            SemanticFrame(
                mode=SemanticInterpretationMode.DATA,
                query_shape=QueryShape.SCALAR,
                measure_mentions=("销售额",),
                evidence_spans=(
                    SemanticEvidenceSpan(slot="query_shape", text="销售额"),
                    SemanticEvidenceSpan(slot="measure", text="销售额"),
                ),
            ),
            SemanticInterpretationMode.DATA,
        ),
        (
            "当前报表销售额最高的区域",
            SemanticFrame(
                mode=SemanticInterpretationMode.DATA,
                query_shape=QueryShape.SCALAR,
                measure_mentions=("销售额",),
                evidence_spans=(
                    SemanticEvidenceSpan(slot="query_shape", text="销售额"),
                    SemanticEvidenceSpan(slot="measure", text="销售额"),
                ),
            ),
            SemanticInterpretationMode.DATA,
        ),
    ],
)
async def test_understanding_boundary_uses_bounded_semantic_frame(
    user_input,
    frame,
    expected_mode,
):
    responses = [frame]
    if frame.mode is not SemanticInterpretationMode.GENERAL:
        responses.append(SemanticCoverageDecision(decision="ACCEPT"))
    provider = _QueuedProvider(*responses)

    answer = await LLMSemanticInterpreter(provider).interpret(user_input)

    assert answer.mode is expected_mode
    assert len(provider.calls) == (1 if expected_mode is SemanticInterpretationMode.GENERAL else 2)
    request = provider.calls[0]
    assert request.task is LLMTask.UNDERSTANDING
    assert user_input in request.messages[-1]["content"]
    assert request.metadata == {}
    assert len(request.messages) == 2


def test_natural_scalar_answer_does_not_expose_canonical_scope_prefix():
    plan = _plan(
        filters=[StructuredFilter(field="Region", value="South")],
        time_range=TimeRangeSpec(
            date_field="Order Date",
            start_date=date(2025, 5, 1),
            end_date=date(2025, 5, 31),
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month",
        ),
    )
    result = _result(["[Total Sales]"], [[197199.61]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    answer = FactBoundedAnswerBuilder().build(
        plan,
        result,
        facts,
        effective_scope="模型：local_desktop:93d · 指标：销售额 · 筛选：Region=South · 查询时间：2025年5月",
    )

    assert "模型：" not in answer.answer
    assert "Region=South" not in answer.answer
    assert "2025年5月" in answer.answer
    assert "South" in answer.answer
    assert "197,199.61" in answer.answer
    assert answer.evidence["requested_query_scope"].startswith("模型：")


def test_natural_ranking_answer_names_every_verified_top_item():
    plan = _plan(
        query_shape=QueryShape.RANKING,
        dimensions=["Product"],
        sort="desc",
        top_n=3,
    )
    result = _result(
        ["Product[Product]", "[Total Sales]"],
        [["Laptop Pro", 2757482.96], ["Laptop Air", 1800000], ["Monitor 27", 900000]],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    answer = FactBoundedAnswerBuilder().build(plan, result, facts)

    assert all(name in answer.answer for name in ("Laptop Pro", "Laptop Air", "Monitor 27"))
    assert "2,757,482.96" in answer.answer
    assert FactOutputValidator().validate_answer(answer, facts) == []


def test_availability_probe_is_canonical_derived_and_measure_aware():
    source = _plan(
        time_range=TimeRangeSpec(
            date_field="Order Date",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            mode=TimeRangeMode.CURRENT_YEAR,
            grain="month",
        ),
        dimension_tables={"Order Date": "Date"},
    )
    probe = AvailabilityProbeBuilder().build_plan(source)

    assert probe.measures == ["Total Sales"]
    assert probe.dimensions == ["Order Date"]
    assert probe.dimension_tables == {"Order Date": "Date"}
    assert probe.time_range is None
    assert probe.filters == []
    assert probe.query_shape is QueryShape.GROUPED
    assert probe.dimension_order == "desc"

    probe_result = _result(
        ["Date[Order Date]", "[Total Sales]"],
        [["2026-01-01T00:00:00", 100], ["2026-02-01T00:00:00", 200], ["2026-03-01T00:00:00", 300]],
        result_id="horizon-result",
    )
    probe_facts = VerifiedFactSetBuilder().build(probe, probe_result)
    horizon = AvailabilityProbeBuilder().derive_horizon(probe, probe_result, probe_facts)
    assert horizon.status is DataHorizonStatus.KNOWN
    assert horizon.latest_period == date(2026, 3, 31)
    assert horizon.measure == "Total Sales"
    assert horizon.temporal_dimension == "Order Date"


def test_partial_year_answer_explains_observable_horizon_without_refresh_claim():
    plan = _plan(
        time_range=TimeRangeSpec(
            date_field="Order Date",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            mode=TimeRangeMode.CURRENT_YEAR,
            grain="month",
        )
    )
    result = _result(["[Total Sales]"], [[999466.89]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    availability = DataAvailabilityContext(
        observed_data_coverage=facts.observed_data_coverage,
        available_data_horizon=AvailableDataHorizon(
            status=DataHorizonStatus.KNOWN,
            latest_period=date(2026, 3, 31),
            grain="month",
            semantic_model_key="model",
            measure="Total Sales",
            temporal_dimension="Order Date",
            source_result_id="horizon-result",
            source_fact_set_id="horizon-facts",
        ),
    )
    answer = FactBoundedAnswerBuilder().build(
        plan, result, facts, data_availability=availability
    )

    assert "当前模型中可观测到" in answer.answer
    assert "截至2026年3月" in answer.answer
    assert "更新到" not in answer.answer
    assert "截至3月" in answer.answer


def test_empty_horizon_probe_and_zero_business_value_are_distinct():
    source = _plan(
        time_range=TimeRangeSpec(
            date_field="Order Date",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 9, 30),
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month",
        )
    )
    probe = AvailabilityProbeBuilder().build_plan(source)
    empty_result = _result(
        ["Date[Order Date]", "[Total Sales]"],
        [],
        result_id="empty-horizon",
    )
    empty_facts = VerifiedFactSetBuilder().build(probe, empty_result)
    horizon = AvailabilityProbeBuilder().derive_horizon(
        probe,
        empty_result,
        empty_facts,
    )
    assert horizon.status is DataHorizonStatus.EMPTY

    zero_result = _result(["[Total Sales]"], [[0]], result_id="zero-value")
    zero_facts = VerifiedFactSetBuilder().build(source, zero_result)
    zero_answer = FactBoundedAnswerBuilder().build(source, zero_result, zero_facts)
    assert "为0" in zero_answer.answer
    assert "未返回数据" not in zero_answer.answer


def test_recent_six_month_empty_fallback_keeps_structural_numbers_scoped() -> None:
    plan = _plan(
        query_shape=QueryShape.BOUNDED_TREND,
        dimensions=["Order Date"],
        dimension_tables={"Order Date": "Date"},
        dimension_order="asc",
        time_range=TimeRangeSpec(
            date_field="Order Date",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 9, 30),
            mode=TimeRangeMode.RECENT_MONTHS,
            grain="month",
        ),
    )
    result = _result(
        ["Date[Order Date]", "[Total Sales]"],
        [],
        result_id="recent-six-empty",
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    availability = DataAvailabilityContext(
        observed_data_coverage=facts.observed_data_coverage,
        available_data_horizon=AvailableDataHorizon(
            status=DataHorizonStatus.KNOWN,
            latest_period=date(2026, 3, 31),
            grain="month",
            semantic_model_key="model",
            measure="Total Sales",
            temporal_dimension="Order Date",
            source_result_id="horizon-result",
            source_fact_set_id="horizon-facts",
        ),
    )

    answer = FactBoundedAnswerBuilder().build(
        plan,
        result,
        facts,
        data_availability=availability,
    )

    assert FactOutputValidator().validate_answer(answer, facts) == []
    assert "2026年3月" in answer.answer
    assert "2026年4月至2026年9月" in answer.answer

    poisoned = AnswerSpec.model_validate({
        **answer.model_dump(),
        "answer": "销售额是2026年4月至2026年9月。",
        "summary": "销售额是2026年4月至2026年9月。",
    })
    assert "unverified_numeric_claim" in FactOutputValidator().validate_answer(
        poisoned,
        facts,
    )


def test_validator_rejects_comparison_cause_and_availability_hallucination():
    plan = _plan()
    result = _result(["[Total Sales]"], [[20]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    base = FactBoundedAnswerBuilder().build(plan, result, facts)

    for mutation in (
        "销售额同比增长20%。",
        "销售额下降是因为市场需求疲软。",
        "销售数据已更新至2026年9月。",
    ):
        poisoned = AnswerSpec.model_validate({
            **base.model_dump(),
            "answer": mutation,
            "summary": mutation,
        })
        assert FactOutputValidator().validate_answer(poisoned, facts)


@pytest.mark.asyncio
async def test_natural_composer_accepts_only_fact_complete_wording():
    plan = _plan()
    result = _result(["[Total Sales]"], [[20]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    fallback = FactBoundedAnswerBuilder().build(
        plan,
        result,
        facts,
        display_bindings={
            "[Total Sales]": SimpleNamespace(
                canonical_name="Total Sales",
                display_name="销售额",
                format_kind=None,
            )
        },
    )
    provider = _QueuedProvider(NaturalAnswerDraft(answer="销售额是20。"))

    answer = await NaturalAnswerComposer(provider).compose(
        fallback,
        facts,
        data_availability=None,
    )

    assert answer.answer == "销售额是20。"
    assert answer.evidence == fallback.evidence
    assert [call.task for call in provider.calls] == [LLMTask.ANSWER]


@pytest.mark.asyncio
async def test_natural_composer_repairs_then_falls_back_on_hallucination():
    plan = _plan()
    result = _result(["[Total Sales]"], [[20]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    fallback = FactBoundedAnswerBuilder().build(plan, result, facts)
    provider = _QueuedProvider(
        NaturalAnswerDraft(answer="销售额是21，因为需求增长。"),
        NaturalAnswerDraft(answer="销售额同比增长20%。"),
    )

    answer = await NaturalAnswerComposer(provider).compose(
        fallback,
        facts,
        data_availability=None,
    )

    assert answer == fallback
    assert len(provider.calls) == 2
