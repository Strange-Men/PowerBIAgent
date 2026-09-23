"""Frozen QueryShape contract under the unified Understanding Layer."""

import pytest
from pydantic import ValidationError

from backend.app.intent.question_router import QuestionRoute, QuestionRouter
from backend.app.intent.semantic_interpreter import (
    GeneralFactScope,
    RankingIntent,
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticInterpretationMode,
    UNDERSTANDING_SYSTEM_PROMPT,
)
from backend.app.schemas.data_contracts import QueryShape


def test_required_query_shape_set_is_unchanged() -> None:
    assert {item.value for item in QueryShape} == {
        "scalar",
        "entity_list",
        "grouped",
        "ranking",
        "member_set",
        "filtered_aggregation",
        "trend",
        "bounded_trend",
    }


def test_unknown_query_shape_is_rejected_by_frame_contract() -> None:
    with pytest.raises(ValidationError):
        SemanticFrame.model_validate({
            "mode": "data",
            "query_shape": "forecast",
            "measure_mentions": ["metric"],
            "evidence_spans": [
                {"slot": "query_shape", "text": "forecast"},
                {"slot": "measure", "text": "metric"},
            ],
        })


def test_ranking_frame_preserves_incomplete_structure_for_clarification() -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.RANKING,
        measure_mentions=("销售额",),
        dimension_mentions=("产品",),
        ranking_intent=RankingIntent(evidence_span="排一下"),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="排一下"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="dimension", text="产品"),
            SemanticEvidenceSpan(slot="ranking", text="排一下"),
        ),
    )

    assert frame.ranking_intent.direction is None
    assert frame.ranking_intent.top_n is None


def test_understanding_prompt_requires_literal_ranking_entity_evidence() -> None:
    assert "entities being ranked" in UNDERSTANDING_SYSTEM_PROMPT
    assert "dimension_mentions" in UNDERSTANDING_SYSTEM_PROMPT
    assert "exact dimension evidence span" in UNDERSTANDING_SYSTEM_PROMPT


@pytest.mark.parametrize(
    "question",
    [
        "2026年销售额情况",
        "各地区销售额",
        "销售额最高的三个产品",
        "最近6个月销售额趋势",
        "我公司在岗厦北，有什么推荐？",
    ],
)
def test_router_never_owns_business_query_shape(question: str) -> None:
    decision = QuestionRouter().route(question)
    assert decision.route is QuestionRoute.LLM_SEMANTIC_INTERPRETATION
    assert decision.query_shape is None


def test_general_frame_cannot_smuggle_business_slots() -> None:
    with pytest.raises(ValidationError):
        SemanticFrame(
            mode=SemanticInterpretationMode.GENERAL,
            general_fact_scope=GeneralFactScope.TIME_STABLE_OR_NONFACTUAL,
            general_answer="当然。",
            measure_mentions=("销售额",),
        )
