"""Focused unit contracts for M5.10.3 semantic/state safety."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.app.memory.models import MemoryStatus, StructuredWorkMemory
from backend.app.query_plan.completeness import (
    CanonicalShapeCompletenessError,
    CanonicalShapeCompletenessGate,
)
from backend.app.query_plan.grounding import GroundedSemanticDelta
from backend.app.query_plan.state_transition import (
    FilterTransition,
    InheritanceMode,
    StateTransitionService,
)
from backend.app.query_plan.turn_relation import TurnRelationEvidence, TurnRelationKind
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    QueryPlan,
    QueryShape,
    StructuredFilter,
)


MANUAL_CORPUS_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "m5_10_3_manual_semantic_regressions.yaml"
)


def test_manual_regression_corpus_preserves_all_reported_phrases_and_boundaries() -> None:
    payload = yaml.safe_load(MANUAL_CORPUS_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert [case["user_expression"] for case in cases] == [
        "哪三个产品最挣钱",
        "销售额最高的三个产品",
        "各产品销售额是多少？",
        "销售额按区域排一下",
        "最近几个月的运单趋势",
        "Top 5 客户按 Sales",
        "Product 按销售额排前三",
        "top 3 products by sales",
        "华南 region 的 sales",
        "不是销售额，是销售数量",
        "也不是华南，是华北",
    ]
    required = {
        "previous_committed",
        "pending_context",
        "expected_shape_or_clarification",
        "current_slots",
        "inherited_slots",
        "replaced_slots",
        "cleared_slots",
        "terminal_state",
        "dax_executed",
        "memory_committed",
    }
    assert all(required.issubset(case) for case in cases)


@pytest.mark.parametrize(
    ("message", "semantic_input"),
    [
        ("不是销售额，是销售数量", "销售数量"),
        ("也不是华南，是华北", "华北"),
        ("不是产品，而是类别", "类别"),
        ("不是 OnHandUnits, 是 ReservedUnits", "ReservedUnits"),
    ],
)
def test_correction_relation_extracts_only_positive_replacement(
    message: str, semantic_input: str
) -> None:
    evidence = TurnRelationEvidence.classify(message)

    assert evidence.kind == TurnRelationKind.REPLACE
    assert evidence.explicit is True
    assert evidence.source == "deterministic_correction_cue"
    assert evidence.semantic_input == semantic_input


@pytest.mark.parametrize(
    "message",
    ["华南不是最高的区域", "销售额不是负数", "库存不是空的"],
)
def test_plain_negation_is_not_misclassified_as_replacement(message: str) -> None:
    assert TurnRelationEvidence.classify(message).kind == TurnRelationKind.UNSPECIFIED


def _committed() -> StructuredWorkMemory:
    return StructuredWorkMemory(
        state_status=MemoryStatus.COMMITTED,
        measures=["Revenue"],
        dimensions=["Product"],
        filters=[
            {"field": "Region", "operator": "eq", "value": "South"},
            {"field": "Channel", "operator": "eq", "value": "Retail"},
        ],
        sort="desc",
        top_n=3,
        last_query_plan={
            "dimension_tables": {
                "Product": "Facts",
                "Region": "Regions",
                "Channel": "Channels",
            }
        },
    )


def _draft() -> QueryPlan:
    return QueryPlan(
        normalized_question="query",
        semantic_model_key="model",
        query_shape=QueryShape.RANKING,
    )


@pytest.mark.parametrize("shape", [QueryShape.GROUPED, QueryShape.RANKING])
def test_current_grouping_or_ranking_dimension_removes_only_same_field_historical_filter(
    shape: QueryShape,
) -> None:
    ranking = shape == QueryShape.RANKING
    result = StateTransitionService().merge(
        _draft(),
        GroundedSemanticDelta(
            query_shape=shape,
            dimensions=["Region"],
            dimension_tables={"Region": "Regions"},
            sort="desc" if ranking else None,
            sort_specified=ranking,
            top_n=1 if ranking else None,
            top_n_specified=ranking,
        ),
        _committed(),
        inheritance_mode=InheritanceMode.FOLLOW_UP,
        current_dimension_fields={"Region"},
    )

    assert result.query_plan.filters == [
        StructuredFilter(field="Channel", value="Retail")
    ]
    assert result.transitions.filters == [FilterTransition.REMOVE]


@pytest.mark.parametrize(
    "field",
    ["Region", "Course", "Warehouse", "Carrier", "StationCode"],
    ids=["retail", "education", "operations", "logistics", "unknown-holdout"],
)
def test_field_role_transition_is_domain_independent(field: str) -> None:
    committed = StructuredWorkMemory(
        state_status=MemoryStatus.COMMITTED,
        measures=["Metric"],
        filters=[{"field": field, "operator": "eq", "value": "Old"}],
    )
    result = StateTransitionService().merge(
        QueryPlan(
            normalized_question="rank",
            semantic_model_key="model",
            query_shape=QueryShape.RANKING,
        ),
        GroundedSemanticDelta(
            query_shape=QueryShape.RANKING,
            dimensions=[field],
            sort="desc",
            sort_specified=True,
            top_n=3,
            top_n_specified=True,
        ),
        committed,
        current_dimension_fields={field},
    )

    assert result.query_plan.filters == []
    assert result.transitions.filters == [FilterTransition.REMOVE]


def test_current_same_field_member_is_retained_when_explicitly_reexpressed() -> None:
    result = StateTransitionService().merge(
        _draft(),
        GroundedSemanticDelta(
            query_shape=QueryShape.RANKING,
            dimensions=["Region"],
            dimension_tables={"Region": "Regions"},
            filters=[StructuredFilter(field="Region", value="North")],
            sort="desc",
            sort_specified=True,
            top_n=1,
            top_n_specified=True,
        ),
        _committed(),
        inheritance_mode=InheritanceMode.FOLLOW_UP,
        current_dimension_fields={"Region"},
    )

    assert result.query_plan.filters == [
        StructuredFilter(field="Channel", value="Retail"),
        StructuredFilter(field="Region", value="North"),
    ]
    assert result.transitions.filters == [FilterTransition.REPLACE_SAME_FIELD]


def test_inherited_ranking_dimension_keeps_compatible_same_field_filter() -> None:
    result = StateTransitionService().merge(
        _draft(),
        GroundedSemanticDelta(
            query_shape=QueryShape.RANKING,
            dimensions=["Product"],
        ),
        _committed(),
        inheritance_mode=InheritanceMode.FOLLOW_UP,
        current_dimension_fields=set(),
    )

    assert {item.field for item in result.query_plan.filters} == {
        "Region", "Channel"
    }
    assert result.transitions.filters == [FilterTransition.KEEP]


def test_shape_obligation_firewall_rejects_canonical_downgrade() -> None:
    plan = CanonicalQueryPlan(
        normalized_question="three best entities",
        semantic_model_key="model",
        query_shape=QueryShape.SCALAR,
        measures=["Revenue"],
    )

    with pytest.raises(
        CanonicalShapeCompletenessError,
        match="canonical_shape_obligation_mismatch",
    ):
        CanonicalShapeCompletenessGate().validate(
            plan, expected_shape=QueryShape.RANKING
        )
