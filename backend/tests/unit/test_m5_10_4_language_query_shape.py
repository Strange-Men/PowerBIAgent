"""Failure-first contracts for bounded open-language QueryShape handling."""

from __future__ import annotations

import pytest

from backend.app.intent.models import (
    IntentSpec,
    IntentType,
    TimeIntentDraft,
    TimeIntentKind,
)
from backend.app.intent.prompt import SYSTEM_PROMPT as INTENT_SYSTEM_PROMPT
from backend.app.intent.question_router import QuestionRouter
from backend.app.llm.base import LLMProvider, LLMResponse, LLMTask
from backend.app.query_plan.completeness import (
    QueryShapeReconciliationPolicy,
    SemanticObligationCoverageGate,
    SemanticObligationKind,
    SemanticObligationStatus,
)
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector,
    CandidateSelection,
    GroundedSemanticDelta,
    GroundingStatus,
    ObjectGroundingResult,
    SemanticGroundingService,
)
from backend.app.query_plan.prompt import SYSTEM_PROMPT
from backend.app.query_plan.semantic_catalog import (
    SemanticCatalogBuilder,
    SemanticObjectType,
)
from backend.app.query_plan.turn_relation import TurnRelationEvidence
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    ColumnSchema,
    QueryPlan,
    QueryShape,
)
from backend.tests.fixtures.semantic_context_domains import domains
from backend.tests.unit.test_semantic_completeness import _catalog, _resolved_outcome


def test_query_plan_prompt_exposes_bounded_query_shape_contract() -> None:
    assert '"query_shape"' in SYSTEM_PROMPT
    for shape in QueryShape:
        assert shape.value in SYSTEM_PROMPT
    assert "语言理解" in SYSTEM_PROMPT
    assert "canonical" in SYSTEM_PROMPT.casefold()


def test_intent_prompt_forbids_inventing_vague_month_count() -> None:
    assert "最近几个月" in INTENT_SYSTEM_PROMPT
    assert "months=null" in INTENT_SYSTEM_PROMPT


def test_vague_recent_month_draft_is_representable_without_invented_bound() -> None:
    draft = TimeIntentDraft(
        kind=TimeIntentKind.RECENT_MONTHS,
        expression="最近几个月",
    )

    assert draft.months is None


def test_vague_recent_months_is_time_clarification_not_filter_residue() -> None:
    outcome = _resolved_outcome().model_copy(
        update={
            "delta": _resolved_outcome().delta.model_copy(
                update={
                    "query_shape": QueryShape.TREND,
                    "dimensions": ["Month"],
                }
            )
        }
    )
    report = SemanticObligationCoverageGate().inspect(
        user_input="最近几个月的运单数趋势",
        outcome=outcome,
        catalog=_catalog(),
        relation=TurnRelationEvidence.classify("最近几个月的运单数趋势"),
        language_evidence=("运单数",),
    )

    unresolved = [
        item
        for item in report.obligations
        if item.status == SemanticObligationStatus.NEEDS_CLARIFICATION
    ]
    assert [(item.kind, item.evidence) for item in unresolved] == [
        (SemanticObligationKind.TIME, "vague_recent_month_range")
    ]
    assert report.clarification_reason.value == "incomplete_time_range"


def test_bounded_recent_months_are_consumed_as_time_not_filter_residue() -> None:
    outcome = _resolved_outcome().model_copy(
        update={
            "delta": _resolved_outcome().delta.model_copy(
                update={
                    "query_shape": QueryShape.TREND,
                    "dimensions": ["Month"],
                }
            )
        }
    )
    report = SemanticObligationCoverageGate().inspect(
        user_input="最近6个月的运单数趋势",
        outcome=outcome,
        catalog=_catalog(),
        relation=TurnRelationEvidence.classify("最近6个月的运单数趋势"),
        language_evidence=("运单数",),
    )

    assert report.executable is True
    assert not any(
        item.evidence == "bounded_result_affecting_modifier_residue"
        for item in report.obligations
    )


def test_required_query_shape_set_is_unchanged() -> None:
    assert {shape.value for shape in QueryShape} == {
        "scalar",
        "entity_list",
        "grouped",
        "ranking",
        "member_set",
        "filtered_aggregation",
        "trend",
        "bounded_trend",
    }


def test_open_language_examples_reach_only_router_fallbacks() -> None:
    router = QuestionRouter()
    assert router.route("请给出 NetRevenue 领先的三项 AreaName").query_shape == QueryShape.SCALAR
    assert router.route("那么请给出 NetRevenue 领先的三项 AreaName").query_shape is None


@pytest.mark.parametrize(
    ("router_shape", "draft_shape", "evidence", "expected", "source"),
    [
        (QueryShape.SCALAR, QueryShape.GROUPED, "spread across", QueryShape.GROUPED, "current_llm_draft"),
        (None, QueryShape.RANKING, "领先的三项", QueryShape.RANKING, "current_llm_draft"),
        (QueryShape.GROUPED, QueryShape.RANKING, "前三", QueryShape.GROUPED, "router_high_confidence"),
        (QueryShape.SCALAR, None, None, QueryShape.SCALAR, "router_weak_fallback"),
    ],
)
def test_bounded_reconciliation_preserves_stronger_proven_shape(
    router_shape, draft_shape, evidence, expected, source
) -> None:
    message = f"NetRevenue {evidence or ''} AreaName"
    report = QueryShapeReconciliationPolicy.reconcile(
        user_input=message,
        router_shape=router_shape,
        draft_shape=draft_shape,
        draft_evidence=evidence,
    )

    assert report.effective_shape == expected
    assert report.source == source
    assert report.requires_clarification is False


def test_unverifiable_llm_shape_evidence_keeps_obligation_but_clarifies() -> None:
    report = QueryShapeReconciliationPolicy.reconcile(
        user_input="NetRevenue leaderboard AreaName",
        router_shape=QueryShape.SCALAR,
        draft_shape=QueryShape.RANKING,
        draft_evidence="top three",
    )

    assert report.effective_shape == QueryShape.RANKING
    assert report.source == "current_llm_draft"
    assert report.draft_evidence is None
    assert report.requires_clarification is True


def test_one_llm_phrase_cannot_prove_both_shape_and_measure() -> None:
    catalog = _catalog()
    measure = catalog.objects[0]
    outcome = _resolved_outcome().model_copy(update={
        "delta": GroundedSemanticDelta(
            query_shape=QueryShape.RANKING,
            measures=[measure.canonical_name],
            dimensions=["Carrier"],
            sort="desc",
            sort_specified=True,
            top_n=3,
            top_n_specified=True,
        ),
        "object_results": [ObjectGroundingResult(
            status=GroundingStatus.RESOLVED,
            role="measure",
            phrase="最挣钱",
            canonical_object=measure,
            method="bounded_llm",
        )],
    })
    reconciliation = QueryShapeReconciliationPolicy.reconcile(
        user_input="哪三个承运商最挣钱",
        router_shape=QueryShape.SCALAR,
        draft_shape=QueryShape.RANKING,
        draft_evidence="最挣钱",
    )

    report = SemanticObligationCoverageGate().inspect(
        user_input="哪三个承运商最挣钱",
        outcome=outcome,
        catalog=catalog,
        relation=TurnRelationEvidence.classify("哪三个承运商最挣钱"),
        shape_reconciliation=reconciliation,
    )

    assert report.executable is False
    assert report.clarification_reason.value == "measure_unresolved"
    assert any(
        item.evidence == "shared_llm_shape_measure_evidence"
        for item in report.obligations
    )


@pytest.mark.parametrize(
    "message",
    [
        "NetRevenue 领先的三项 AreaName",
        "按 NetRevenue 把 AreaName 排前三！",
        "AreaName 按 NetRevenue 前3",
        "top 3 AreaName by NetRevenue",
        "three leading AreaName for NetRevenue",
    ],
)
def test_ranking_bound_evidence_is_bounded_and_word_order_invariant(
    message: str,
) -> None:
    assert SemanticGroundingService._draft_top_n_has_current_evidence(message, 3)


class _SameNameSelectionProvider(LLMProvider):
    provider_name = "same-name-selection"
    is_mock = False

    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id
        self.calls = 0

    async def generate(self, request, output_type):
        assert request.task == LLMTask.SEMANTIC_SELECTION
        self.calls += 1
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(
                outcome="RESOLVED",
                candidate_id=self.candidate_id,
                matched_phrase="AreaName",
            ),
            model="same-name-selection",
        )


@pytest.mark.asyncio
async def test_same_name_runtime_candidates_use_bounded_owner_selection() -> None:
    domain = domains()[0]
    schema = domain.schema.model_copy(deep=True)
    schema.tables[0].columns.append(
        ColumnSchema(name=domain.dimension, data_type="String")
    )
    catalog = SemanticCatalogBuilder().build(schema)
    provider = _SameNameSelectionProvider("field:Areas:AreaName")

    async def no_members(field, limit):
        return ColumnMembersResult(
            semantic_model_key=schema.key,
            table_name=field.table_name,
            field_name=field.canonical_name,
            values=[],
            source_mode="real",
        )

    # The plural form bypasses exact mention matching; the weak draft still
    # names a duplicated runtime field and must be restricted to those IDs.
    message = "three leading AreaNames for NetRevenue"
    outcome = await SemanticGroundingService(
        catalog,
        selector=BoundedLLMObjectSelector(provider),
    ).ground(
        message,
        IntentSpec(
            intent=IntentType.DATA_QUESTION,
            confidence=1,
            normalized_question=message,
            detected_measures=[domain.measure],
            detected_dimensions=[domain.dimension],
        ),
        QueryPlan(
            normalized_question=message,
            semantic_model_key=schema.key,
            query_shape=QueryShape.RANKING,
            query_shape_evidence="three leading",
            measures=[domain.measure],
            dimensions=[domain.dimension],
            sort="desc",
            top_n=3,
        ),
        None,
        no_members,
        query_shape=QueryShape.RANKING,
    )

    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.dimensions == ["AreaName"]
    assert outcome.delta.dimension_tables == {"AreaName": "Areas"}
    assert provider.calls == 1
