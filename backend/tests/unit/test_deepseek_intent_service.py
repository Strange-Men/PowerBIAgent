"""Regression tests for the single LLM Understanding authority.

The former ``DeepSeekIntentService`` was removed in M5.10.6 because it was a
second open-language authority. These tests retain its safety/repair coverage
at the replacement ``LLMSemanticInterpreter`` boundary.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.intent.models import TimeIntentDraft, TimeIntentKind, TurnRelation
from backend.app.intent.semantic_interpreter import (
    AnalysisGoal,
    GeneralFactScope,
    LLMSemanticInterpreter,
    SemanticCoverageDecision,
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticInterpretationError,
    SemanticInterpretationMode,
)
from backend.app.llm.base import (
    LLMErrorCategory,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTask,
    LLMValidationError,
)
from backend.app.schemas.data_contracts import QueryShape


def _general(answer: str = "可以，我们聊聊。") -> SemanticFrame:
    return SemanticFrame(
        mode=SemanticInterpretationMode.GENERAL,
        general_fact_scope=GeneralFactScope.TIME_STABLE_OR_NONFACTUAL,
        general_answer=answer,
    )


def _scalar() -> SemanticFrame:
    return SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="销售额"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
        ),
    )


class _QueueProvider(LLMProvider):
    provider_name = "test-understanding"
    is_mock = False

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.calls: list[tuple[LLMRequest, type]] = []

    async def generate(self, request: LLMRequest, output_type: type) -> LLMResponse:
        self.calls.append((request, output_type))
        if not self.items:
            raise AssertionError("unexpected extra understanding call")
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return LLMResponse(content="{}", structured=item, model="offline")


def _accept() -> SemanticCoverageDecision:
    return SemanticCoverageDecision(decision="ACCEPT")


@pytest.mark.asyncio
async def test_general_is_one_current_message_only_understanding_call() -> None:
    provider = _QueueProvider(_general())

    frame = await LLMSemanticInterpreter(provider).interpret("我今天有点累，聊两句")

    assert frame.mode is SemanticInterpretationMode.GENERAL
    assert frame.general_answer
    assert [request.task for request, _ in provider.calls] == [LLMTask.UNDERSTANDING]
    prompt = provider.calls[0][0].messages[-1]["content"]
    assert "我今天有点累，聊两句" in prompt
    system_prompt = provider.calls[0][0].messages[0]["content"]
    assert "GENERAL has one strict structural reset" in system_prompt
    assert "every mention/filter/unresolved/evidence/changed/context array" in system_prompt
    assert "not an unresolved business mention" in system_prompt
    assert "only when the user's literal metric wording is English" in system_prompt
    assert "never transfer it to another language's bare activity noun" in system_prompt
    assert "DAX" not in frame.model_dump_json()


@pytest.mark.asyncio
async def test_data_uses_understanding_then_veto_only_coverage() -> None:
    provider = _QueueProvider(_scalar(), _accept())

    frame = await LLMSemanticInterpreter(provider).interpret("今年销售额")

    assert frame.query_shape is QueryShape.SCALAR
    assert [request.task for request, _ in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]
    assert provider.calls[1][1] is SemanticCoverageDecision


@pytest.mark.asyncio
async def test_understanding_contract_preserves_compatible_omitted_follow_up_scope() -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FOLLOW_UP,
        query_shape=QueryShape.GROUPED,
        measure_mentions=("销售额",),
        dimension_mentions=("地区",),
        changed_slots=("query_shape", "dimension"),
        referenced_context_slots=("time", "time_range"),
        evidence_spans=(
            SemanticEvidenceSpan(slot="relation", text="那"),
            SemanticEvidenceSpan(slot="query_shape", text="各地区"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="dimension", text="地区"),
        ),
    )
    provider = _QueueProvider(frame, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "那各地区的销售额分别是多少？",
        committed_context={
            "measures": ["Total Sales"],
            "time_range": {
                "date_field": "Order Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    )

    assert result.relation is TurnRelation.FOLLOW_UP
    assert set(result.referenced_context_slots) == {"time", "time_range"}
    prompt = provider.calls[0][0].messages[0]["content"]
    assert "deictic or conversational continuation" in prompt
    assert "including time/time_range" in prompt


@pytest.mark.asyncio
async def test_complete_same_topic_ranking_is_allowed_as_follow_up() -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FOLLOW_UP,
        query_shape=QueryShape.RANKING,
        measure_mentions=("销售额",),
        dimension_mentions=("地区",),
        ranking_intent={
            "direction": "desc",
            "top_n": 3,
            "evidence_span": "前三个",
        },
        changed_slots=("query_shape", "ranking", "sort", "top_n"),
        referenced_context_slots=("time", "time_range"),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="最高的前三个"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="dimension", text="地区"),
            SemanticEvidenceSpan(slot="ranking", text="前三个"),
        ),
    )
    provider = _QueueProvider(frame, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "销售额最高的前三个地区是哪几个？",
        committed_context={
            "query_shape": "grouped",
            "measures": ["Total Sales"],
            "dimensions": ["Region"],
            "analysis_goal": "用户提问: 那各地区的销售额分别是多少？",
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    )

    assert result.relation is TurnRelation.FOLLOW_UP
    assert result.changed_slots == ("query_shape", "ranking", "sort", "top_n")
    assert set(result.referenced_context_slots) == {"time", "time_range"}
    prompt = provider.calls[0][0].messages[0]["content"]
    assert "not from whether the current sentence is grammatically complete" in prompt
    assert "stays on the same business topic" in prompt
    assert "measure, dimension, or" in prompt
    assert '"previous_user_message": "那各地区的销售额分别是多少？"' not in (
        provider.calls[0][0].messages[1]["content"]
    )


@pytest.mark.asyncio
async def test_repeated_fresh_ranking_is_normalized_by_continuity_invariant() -> None:
    fresh = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FRESH_QUESTION,
        query_shape=QueryShape.RANKING,
        measure_mentions=("销售额",),
        dimension_mentions=("地区",),
        ranking_intent={
            "direction": "desc",
            "top_n": 3,
            "evidence_span": "前三个",
        },
        changed_slots=("query_shape", "ranking_intent"),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="最高的前三个"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="dimension", text="地区"),
            SemanticEvidenceSpan(slot="ranking", text="前三个"),
        ),
    )
    reviewed_but_still_fresh = fresh.model_copy(
        update={
            "changed_slots": (),
        }
    )
    provider = _QueueProvider(fresh, reviewed_but_still_fresh, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "销售额最高的前三个地区是哪几个？",
        committed_context={
            "query_shape": "grouped",
            "measures": ["Total Sales"],
            "dimensions": ["Region"],
            "analysis_goal": "用户提问: 那各地区的销售额分别是多少？",
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    )

    assert result.relation is TurnRelation.FOLLOW_UP
    assert result.changed_slots == (
        "dimension",
        "measure",
        "query_shape",
        "ranking",
        "sort",
        "top_n",
    )
    assert result.referenced_context_slots == ("time_range",)
    assert [request.task for request, _ in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]
    repair_prompt = provider.calls[1][0].messages[0]["content"]
    assert "semantic_relation_continuity_review_required" in repair_prompt
    assert "Grammatical completeness does not imply semantic freshness" in repair_prompt
    assert '"previous_user_message": "那各地区的销售额分别是多少？"' not in (
        provider.calls[0][0].messages[1]["content"]
    )
    assert '"previous_user_message": "那各地区的销售额分别是多少？"' in (
        provider.calls[1][0].messages[1]["content"]
    )


@pytest.mark.asyncio
async def test_changed_slots_alone_do_not_prove_continuity() -> None:
    fresh = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FRESH_QUESTION,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("总订单数",),
        changed_slots=("measure",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="总订单数"),
            SemanticEvidenceSpan(slot="measure", text="总订单数"),
        ),
    )
    provider = _QueueProvider(fresh, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "总订单数是多少？",
        committed_context={
            "query_shape": "ranking",
            "measures": ["Total Sales"],
            "dimensions": ["Region"],
            "filters": [{"field": "Region", "operator": "eq", "value": "South"}],
            "analysis_goal": "用户提问: 销售额最高的三个地区",
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    )

    assert result.relation is TurnRelation.FRESH_QUESTION
    assert result.referenced_context_slots == ()
    assert [request.task for request, _ in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]


@pytest.mark.asyncio
async def test_unrelated_ranking_topic_stays_fresh() -> None:
    fresh = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FRESH_QUESTION,
        query_shape=QueryShape.RANKING,
        measure_mentions=("利润",),
        dimension_mentions=("产品",),
        ranking_intent={
            "direction": "desc",
            "top_n": 5,
            "evidence_span": "前五个",
        },
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="最高的前五个"),
            SemanticEvidenceSpan(slot="measure", text="利润"),
            SemanticEvidenceSpan(slot="dimension", text="产品"),
            SemanticEvidenceSpan(slot="ranking", text="前五个"),
        ),
    )
    provider = _QueueProvider(fresh, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "利润最高的前五个产品是什么？",
        committed_context={
            "query_shape": "grouped",
            "measures": ["Total Sales"],
            "dimensions": ["Region"],
            "analysis_goal": "用户提问: 那各地区的销售额分别是多少？",
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    )

    assert result.relation is TurnRelation.FRESH_QUESTION
    assert result.referenced_context_slots == ()
    assert [request.task for request, _ in provider.calls].count(
        LLMTask.UNDERSTANDING
    ) == 1


@pytest.mark.asyncio
async def test_explicit_reset_keeps_same_topic_ranking_fresh() -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FRESH_QUESTION,
        query_shape=QueryShape.RANKING,
        measure_mentions=("销售额",),
        dimension_mentions=("地区",),
        ranking_intent={
            "direction": "desc",
            "top_n": 3,
            "evidence_span": "前三个",
        },
        evidence_spans=(
            SemanticEvidenceSpan(slot="relation", text="新问题"),
            SemanticEvidenceSpan(slot="query_shape", text="最高的前三个"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="dimension", text="地区"),
            SemanticEvidenceSpan(slot="ranking", text="前三个"),
        ),
    )
    provider = _QueueProvider(frame, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "新问题：销售额最高的前三个地区是哪几个？",
        committed_context={
            "query_shape": "grouped",
            "measures": ["Total Sales"],
            "dimensions": ["Region"],
            "analysis_goal": "用户提问: 那各地区的销售额分别是多少？",
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    )

    assert result.relation is TurnRelation.FRESH_QUESTION
    assert result.referenced_context_slots == ()
    assert [request.task for request, _ in provider.calls].count(
        LLMTask.UNDERSTANDING
    ) == 1


@pytest.mark.asyncio
async def test_repeated_fresh_explicit_replacement_is_normalized() -> None:
    fresh = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FRESH_QUESTION,
        query_shape=None,
        measure_mentions=("销量",),
        changed_slots=("measure",),
        evidence_spans=(SemanticEvidenceSpan(slot="measure", text="销量"),),
    )
    provider = _QueueProvider(fresh, fresh, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "换成销量。",
        committed_context={
            "query_shape": "ranking",
            "measures": ["Total Sales"],
            "dimensions": ["Region"],
            "filters": [{"field": "Region", "operator": "eq", "value": "South"}],
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
            "sort": "desc",
            "top_n": 3,
            "analysis_goal": "用户提问: 只看南区。",
        },
    )

    assert result.relation is TurnRelation.FOLLOW_UP
    assert result.changed_slots == ("measure",)
    assert set(result.referenced_context_slots) == {
        "query_shape",
        "dimension",
        "filter",
        "time_range",
        "sort",
        "top_n",
    }


@pytest.mark.asyncio
async def test_illegal_relation_slot_gets_exact_repair() -> None:
    invalid = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FOLLOW_UP,
        query_shape=QueryShape.RANKING,
        dimension_mentions=("地区",),
        ranking_intent={
            "direction": "desc",
            "top_n": 3,
            "evidence_span": "前三个",
        },
        changed_slots=("ranking_intent",),
        referenced_context_slots=("measure", "time_range"),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="前三个地区"),
            SemanticEvidenceSpan(slot="dimension", text="地区"),
            SemanticEvidenceSpan(slot="ranking", text="前三个"),
        ),
    )
    repaired = invalid.model_copy(update={"changed_slots": ("ranking",)})
    provider = _QueueProvider(invalid, repaired, _accept())

    result = await LLMSemanticInterpreter(provider).interpret("前三个地区")

    assert result.changed_slots == ("ranking",)
    repair_prompt = provider.calls[1][0].messages[0]["content"]
    assert "semantic_changed_slot_invalid" in repair_prompt
    assert "Use ranking, never ranking_intent" in repair_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "measure", "time_text"),
    [
        ("新问题：2024年订单数是多少？", "订单数", "2024年"),
        ("总订单数是多少？", "总订单数", None),
    ],
)
async def test_explicit_reset_or_different_complete_topic_stays_fresh(
    message: str, measure: str, time_text: str | None
) -> None:
    spans = [
        SemanticEvidenceSpan(slot="query_shape", text=measure),
        SemanticEvidenceSpan(slot="measure", text=measure),
    ]
    if time_text is not None:
        spans.append(SemanticEvidenceSpan(slot="time", text=time_text))
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        relation=TurnRelation.FRESH_QUESTION,
        query_shape=QueryShape.SCALAR,
        measure_mentions=(measure,),
        time_mentions=(time_text,) if time_text is not None else (),
        time_intent=(
            TimeIntentDraft(
                kind=TimeIntentKind.ABSOLUTE_YEAR,
                expression=time_text,
                year=2024,
            )
            if time_text is not None
            else None
        ),
        evidence_spans=tuple(spans),
    )
    provider = _QueueProvider(frame, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        message,
        committed_context={
            "query_shape": "grouped",
            "measures": ["Total Sales"],
            "dimensions": ["Region"],
            "time_range": {
                "date_field": "Date",
                "start_date": "2025-05-01",
                "end_date": "2025-05-31",
            },
        },
    )

    assert result.relation is TurnRelation.FRESH_QUESTION
    assert result.referenced_context_slots == ()
    prompt = provider.calls[0][0].messages[0]["content"]
    assert "explicit new-question/reset signal" in prompt
    assert "different business topic" in prompt


@pytest.mark.asyncio
async def test_yearless_named_month_non_verbatim_mention_gets_exact_repair() -> None:
    invalid = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.TREND,
        measure_mentions=("销售额",),
        time_mentions=("6月",),
        time_intent=TimeIntentDraft(
            kind=TimeIntentKind.ABSOLUTE_MONTH,
            expression="6月",
            month=6,
        ),
        analysis_goal=AnalysisGoal.EXPLAIN_CHANGE,
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="下降了"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="time", text="六月份"),
        ),
    )
    repaired = invalid.model_copy(
        update={
            "time_mentions": ("六月份",),
            "time_intent": TimeIntentDraft(
                kind=TimeIntentKind.ABSOLUTE_MONTH,
                expression="六月份",
                month=6,
            ),
        }
    )
    provider = _QueueProvider(invalid, repaired, _accept())

    result = await LLMSemanticInterpreter(provider).interpret(
        "为什么六月份销售额下降了？"
    )

    assert result.time_mentions == ("六月份",)
    assert result.time_intent is not None
    assert result.time_intent.expression == "六月份"
    repair_prompt = provider.calls[1][0].messages[0]["content"]
    assert "Validation code: semantic_mention_not_verbatim" in repair_prompt
    assert 'slot="time", text="6月"' in repair_prompt
    assert "time_mentions, time_intent.expression" in repair_prompt


@pytest.mark.asyncio
async def test_report_mode_is_forced_without_creating_template_authority() -> None:
    provider = _QueueProvider(
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            query_shape=None,
            unresolved_mentions=("销售",),
            evidence_spans=(SemanticEvidenceSpan(slot="unresolved", text="销售"),),
        ),
        _accept(),
    )

    frame = await LLMSemanticInterpreter(provider).interpret(
        "生成销售报表",
        forced_mode=SemanticInterpretationMode.REPORT,
    )

    assert frame.mode is SemanticInterpretationMode.REPORT
    assert frame.output_mode == "report"
    assert "requested_template" not in type(frame).model_fields


@pytest.mark.asyncio
async def test_pure_report_output_frame_does_not_require_data_query_shape() -> None:
    provider = _QueueProvider(
        SemanticFrame(
            mode=SemanticInterpretationMode.REPORT,
            query_shape=None,
            output_mode="report",
            evidence_spans=(
                SemanticEvidenceSpan(
                    slot="output_mode", text="专业销售经营分析报表"
                ),
            ),
        ),
        _accept(),
    )

    frame = await LLMSemanticInterpreter(provider).interpret(
        "生成专业销售经营分析报表",
        forced_mode=SemanticInterpretationMode.REPORT,
    )

    assert frame.mode is SemanticInterpretationMode.REPORT
    assert frame.output_mode == "report"
    assert frame.query_shape is None
    assert frame.unresolved_mentions == ()
    assert [request.task for request, _ in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]


@pytest.mark.asyncio
async def test_follow_up_relation_and_changed_slots_are_language_only() -> None:
    provider = _QueueProvider(
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            relation=TurnRelation.FOLLOW_UP,
            query_shape=None,
            measure_mentions=("销售额",),
            changed_slots=("measure",),
            referenced_context_slots=("query_shape", "dimension", "top_n", "sort"),
            evidence_spans=(SemanticEvidenceSpan(slot="measure", text="销售额"),),
        ),
        _accept(),
    )

    frame = await LLMSemanticInterpreter(provider).interpret("按销售额")

    assert frame.relation is TurnRelation.FOLLOW_UP
    assert frame.changed_slots == ("measure",)
    assert frame.query_shape is None


@pytest.mark.asyncio
async def test_non_verbatim_semantic_evidence_fails_closed_after_one_repair() -> None:
    invalid = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("revenue",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="revenue"),
            SemanticEvidenceSpan(slot="measure", text="revenue"),
        ),
    )
    provider = _QueueProvider(invalid, invalid)

    with pytest.raises(SemanticInterpretationError):
        await LLMSemanticInterpreter(provider).interpret("销售额是多少")

    assert len(provider.calls) == 2
    assert all(call.task is LLMTask.UNDERSTANDING for call, _ in provider.calls)


@pytest.mark.asyncio
async def test_exact_evidence_repair_receives_specific_violation_and_recovers() -> None:
    invalid = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.TREND,
        measure_mentions=("销售额",),
        time_mentions=("今年",),
        time_intent=TimeIntentDraft(
            kind=TimeIntentKind.RELATIVE_YEAR,
            expression="今年",
            relative_offset=0,
        ),
        analysis_goal=AnalysisGoal.EXPLAIN_CHANGE,
        evidence_spans=(
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="time", text="今年"),
            SemanticEvidenceSpan(slot="query_shape", text="为什么下降"),
        ),
    )
    repaired = invalid.model_copy(
        update={
            "evidence_spans": (
                SemanticEvidenceSpan(slot="measure", text="销售额"),
                SemanticEvidenceSpan(slot="time", text="今年"),
                SemanticEvidenceSpan(slot="query_shape", text="下降"),
            )
        }
    )
    provider = _QueueProvider(invalid, repaired, _accept())

    frame = await LLMSemanticInterpreter(provider).interpret("为什么今年销售额下降？")

    assert frame.analysis_goal is AnalysisGoal.EXPLAIN_CHANGE
    repair_prompt = provider.calls[1][0].messages[0]["content"]
    assert "semantic_evidence_not_verbatim" in repair_prompt
    assert "为什么下降" in repair_prompt
    assert "contiguous verbatim substring" in repair_prompt
    assert "not a translation of the query_shape enum" in repair_prompt
    assert "observable change wording" in repair_prompt


@pytest.mark.parametrize(
    ("question", "measure", "time_text", "shape_evidence", "goal"),
    [
        ("为什么今年销售额下降？", "销售额", "今年", "下降", AnalysisGoal.EXPLAIN_CHANGE),
        ("为什么今年销量下降？", "销量", "今年", "下降", AnalysisGoal.EXPLAIN_CHANGE),
        ("今年销售额为什么下降？", "销售额", "今年", "为什么下降", AnalysisGoal.EXPLAIN_CHANGE),
        ("what caused sales to decline this year?", "sales", "this year", "decline", AnalysisGoal.EXPLAIN_CHANGE),
        ("why did sales fall this year?", "sales", "this year", "fall", AnalysisGoal.EXPLAIN_CHANGE),
        ("今年销售额下降了吗？", "销售额", "今年", "下降了吗", AnalysisGoal.COMPARE),
        ("销售额今年有没有下降？", "销售额", "今年", "有没有下降", AnalysisGoal.COMPARE),
    ],
)
def test_explain_change_evidence_matrix_uses_only_verbatim_anchors(
    question: str,
    measure: str,
    time_text: str,
    shape_evidence: str,
    goal: AnalysisGoal,
) -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.TREND,
        measure_mentions=(measure,),
        time_mentions=(time_text,),
        analysis_goal=goal,
        evidence_spans=(
            SemanticEvidenceSpan(slot="measure", text=measure),
            SemanticEvidenceSpan(slot="time", text=time_text),
            SemanticEvidenceSpan(slot="query_shape", text=shape_evidence),
        ),
    )

    LLMSemanticInterpreter._validate_evidence(frame, question)
    assert frame.analysis_goal is goal
    assert all(span.slot != "analysis_goal" for span in frame.evidence_spans)


@pytest.mark.parametrize(
    ("question", "forged_evidence"),
    [
        ("销售额下降", "销售额出现下降"),
        ("今年销售额下降", "今年的销售额下降"),
        ("sales declined", "sales decreased"),
    ],
)
def test_semantically_equivalent_non_verbatim_evidence_remains_rejected(
    question: str,
    forged_evidence: str,
) -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.TREND,
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text=forged_evidence),
        ),
    )

    with pytest.raises(SemanticInterpretationError) as captured:
        LLMSemanticInterpreter._validate_evidence(frame, question)

    assert captured.value.code == "semantic_evidence_not_verbatim"


def test_analysis_goal_legacy_evidence_is_removed_before_official_frame_validation() -> None:
    frame = SemanticFrame.model_validate(
        {
            "mode": "data",
            "query_shape": "trend",
            "measure_mentions": ["销售额"],
            "time_mentions": ["今年"],
            "analysis_goal": "EXPLAIN_CHANGE",
            "evidence_spans": [
                {"slot": "measure", "text": "销售额"},
                {"slot": "time", "text": "今年"},
                {"slot": "query_shape", "text": "变差"},
                {"slot": "analysis_goal", "text": "为什么变差"},
            ],
        }
    )

    assert frame.analysis_goal is AnalysisGoal.EXPLAIN_CHANGE
    assert [span.slot for span in frame.evidence_spans] == [
        "measure",
        "time",
        "query_shape",
    ]


@pytest.mark.asyncio
async def test_coverage_omission_vetoes_and_repairs_at_most_once() -> None:
    missing = SemanticCoverageDecision(
        decision="MISSING_SEMANTIC_SPAN",
        missing_span="华南",
    )
    provider = _QueueProvider(_scalar(), missing, _scalar(), missing)

    with pytest.raises(SemanticInterpretationError):
        await LLMSemanticInterpreter(provider).interpret("华南今年销售额")

    assert [request.task for request, _ in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]


@pytest.mark.asyncio
async def test_non_retryable_provider_failure_is_not_retried() -> None:
    provider = _QueueProvider(
        LLMProviderError(
            "secret response must not escape",
            provider="offline",
            retryable=False,
            error_category=LLMErrorCategory.AUTHENTICATION,
        )
    )

    with pytest.raises(SemanticInterpretationError) as captured:
        await LLMSemanticInterpreter(provider).interpret("销售额")

    assert len(provider.calls) == 1
    assert "secret response" not in str(captured.value)


@pytest.mark.asyncio
async def test_retryable_provider_failure_gets_one_bounded_repair() -> None:
    provider = _QueueProvider(
        LLMProviderError(
            "temporary",
            provider="offline",
            retryable=True,
            error_category=LLMErrorCategory.RESPONSE_VALIDATION,
        ),
        _general(),
    )

    frame = await LLMSemanticInterpreter(provider).interpret("聊两句")

    assert frame.mode is SemanticInterpretationMode.GENERAL
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_general_schema_root_violation_gets_one_specific_bounded_repair() -> None:
    try:
        SemanticFrame.model_validate(
            {
                "mode": "general",
                "general_fact_scope": "REQUIRES_CURRENT_EXTERNAL_FACTS",
                "general_answer": "无法核实当前信息。",
                "unresolved_mentions": ["工作餐"],
                "evidence_spans": [{"slot": "unresolved", "text": "工作餐"}],
            }
        )
    except ValidationError as cause:
        invalid = LLMValidationError(
            "invalid semantic frame",
            error_code="output_schema_invalid",
        )
        invalid.__cause__ = cause
    provider = _QueueProvider(invalid, _general("无法核实当前信息。"))

    frame = await LLMSemanticInterpreter(provider).interpret("推荐附近工作餐")

    assert frame.mode is SemanticInterpretationMode.GENERAL
    assert len(provider.calls) == 2
    repair_prompt = provider.calls[1][0].messages[0]["content"]
    assert "general_frame_business_slots_forbidden" in repair_prompt
    assert "all business slots and evidence_spans empty" in repair_prompt


@pytest.mark.asyncio
async def test_blank_input_and_mock_provider_are_rejected() -> None:
    provider = _QueueProvider(_general())
    with pytest.raises(SemanticInterpretationError):
        await LLMSemanticInterpreter(provider).interpret("   ")

    provider.is_mock = True
    with pytest.raises(SemanticInterpretationError):
        LLMSemanticInterpreter(provider)


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "general", "general_answer": ""},
        {"mode": "general", "general_answer": "ok", "measure_mentions": ["x"]},
        {"mode": "data", "general_answer": "invented fact"},
        {"mode": "report", "output_mode": "answer", "unresolved_mentions": ["x"]},
        {"mode": "data", "query_shape": "ninth_shape"},
    ],
)
def test_semantic_frame_strict_cross_field_contract(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SemanticFrame.model_validate(payload)


def test_semantic_frame_forbids_canonical_execution_and_fact_fields() -> None:
    with pytest.raises(ValidationError):
        SemanticFrame.model_validate({
            "mode": "data",
            "query_shape": "scalar",
            "canonical_object_id": "measure:Sales:TotalSales",
            "dax": "EVALUATE ...",
            "numeric_answer": 123,
        })
