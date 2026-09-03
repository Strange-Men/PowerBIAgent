from __future__ import annotations

from datetime import date

import pytest

from backend.app.query_plan.completeness import (
    CanonicalShapeCompletenessError,
    CanonicalShapeCompletenessGate,
    SemanticObligationCoverageGate,
    SemanticObligationStatus,
)
from backend.app.query_plan.grounding import (
    GroundedSemanticDelta,
    GroundingOutcome,
    GroundingStatus,
    MemberGroundingResult,
    ObjectGroundingResult,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
    TemporalGroupingBinding,
)
from backend.app.query_plan.turn_relation import TurnRelationEvidence, TurnRelationKind
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    FilterOperator,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


def _object(name: str, object_type: SemanticObjectType, table: str = "Facts") -> CatalogObject:
    return CatalogObject(
        object_id=f"{object_type.value}:{table}:{name}",
        canonical_name=name,
        object_type=object_type,
        table_name=table,
        data_type="double" if object_type == SemanticObjectType.MEASURE else "string",
        aliases=("运单数",) if name == "Shipment Count" else (),
        member_suffixes=("枢纽",) if name == "Hub" else (),
        temporal_grouping=(
            TemporalGroupingBinding(
                grain="month", date_field="Ship Date", date_table_name="DimDate"
            )
            if name == "Month" else None
        ),
    )


def _catalog() -> SemanticCatalog:
    return SemanticCatalog(
        semantic_model_key="logistics",
        schema_fingerprint="fp",
        objects=(
            _object("Shipment Count", SemanticObjectType.MEASURE),
            _object("Package Count", SemanticObjectType.MEASURE),
            _object("Carrier", SemanticObjectType.FIELD, "DimCarrier"),
            _object("Hub", SemanticObjectType.FIELD, "DimHub"),
            _object("Month", SemanticObjectType.FIELD, "DimDate"),
        ),
    )


def _resolved_outcome(*, member: str | None = None) -> GroundingOutcome:
    measure = _catalog().objects[0]
    hub = _catalog().objects[3]
    members = []
    filters = None
    if member is not None:
        members = [MemberGroundingResult(
            status=GroundingStatus.RESOLVED,
            field=hub,
            requested_value=member,
            canonical_value=member,
            method="runtime_exact",
        )]
        filters = [StructuredFilter(field="Hub", value=member)]
    return GroundingOutcome(
        status=GroundingStatus.RESOLVED,
        delta=GroundedSemanticDelta(
            query_shape=QueryShape.SCALAR,
            measures=["Shipment Count"],
            filters=filters,
        ),
        object_results=[ObjectGroundingResult(
            status=GroundingStatus.RESOLVED,
            role="measure",
            phrase="运单数",
            canonical_object=measure,
            method="exact_alias",
        )],
        member_results=members,
    )


def _plan(shape: QueryShape, **updates: object) -> CanonicalQueryPlan:
    values: dict[str, object] = {
        "normalized_question": "test",
        "semantic_model_key": "logistics",
        "query_shape": shape,
        "measures": ["Shipment Count"],
        "dimensions": [],
    }
    values.update(updates)
    return CanonicalQueryPlan.model_validate(values)


def test_unknown_explicit_modifier_is_not_silently_dropped() -> None:
    report = SemanticObligationCoverageGate().inspect(
        user_input="地球运单数多少？",
        outcome=_resolved_outcome(),
        catalog=_catalog(),
        relation=TurnRelationEvidence.classify("地球运单数多少？"),
    )
    assert not report.executable
    unresolved = [item for item in report.obligations if item.status == SemanticObligationStatus.NEEDS_CLARIFICATION]
    assert [(item.kind.value, item.phrase) for item in unresolved] == [("explicit_filter_member", "地球")]


def test_unknown_modifier_on_entity_list_is_not_silently_dropped() -> None:
    carrier = _catalog().objects[2]
    outcome = GroundingOutcome(
        status=GroundingStatus.RESOLVED,
        delta=GroundedSemanticDelta(
            query_shape=QueryShape.ENTITY_LIST,
            dimensions=["Carrier"],
        ),
        object_results=[ObjectGroundingResult(
            status=GroundingStatus.RESOLVED,
            role="dimension",
            phrase="承运商",
            canonical_object=carrier,
            method="bounded_llm",
        )],
    )
    report = SemanticObligationCoverageGate().inspect(
        user_input="地球有哪些承运商？",
        outcome=outcome,
        catalog=_catalog(),
        relation=TurnRelationEvidence.classify("地球有哪些承运商？"),
    )
    assert report.unresolved_phrases == ["地球"]


def test_bounded_language_head_is_consumed_without_hiding_unknown_modifier() -> None:
    base = _resolved_outcome()
    outcome = base.model_copy(update={
        "object_results": [
            base.object_results[0].model_copy(update={"phrase": "2025年5月运单数是多少？"})
        ]
    })
    normal = SemanticObligationCoverageGate().inspect(
        user_input="2025年5月运单数是多少？",
        outcome=outcome,
        catalog=_catalog(),
        relation=TurnRelationEvidence.classify("2025年5月运单数是多少？"),
        language_evidence=("运单数",),
    )
    assert normal.executable

    unknown = SemanticObligationCoverageGate().inspect(
        user_input="地球运单数是多少？",
        outcome=outcome,
        catalog=_catalog(),
        relation=TurnRelationEvidence.classify("地球运单数是多少？"),
        language_evidence=("运单数",),
    )
    assert unknown.unresolved_phrases == ["地球"]


def test_known_member_consumes_modifier_obligation() -> None:
    report = SemanticObligationCoverageGate().inspect(
        user_input="North Hub 运单数多少？",
        outcome=_resolved_outcome(member="North Hub"),
        catalog=_catalog(),
        relation=TurnRelationEvidence.classify("North Hub 运单数多少？"),
    )
    assert report.executable


def test_generic_ranking_modifier_is_consumed_by_resolved_ranking_obligation() -> None:
    catalog = _catalog()
    outcome = GroundingOutcome(
        status=GroundingStatus.RESOLVED,
        delta=GroundedSemanticDelta(
            query_shape=QueryShape.RANKING,
            measures=["Shipment Count"],
            dimensions=["Carrier"],
            sort="desc",
            sort_specified=True,
            top_n=1,
            top_n_specified=True,
        ),
        object_results=[
            ObjectGroundingResult(
                status=GroundingStatus.RESOLVED,
                role="measure",
                phrase="延误",
                canonical_object=catalog.objects[0],
                method="bounded_llm",
            ),
            ObjectGroundingResult(
                status=GroundingStatus.RESOLVED,
                role="ranking_dimension",
                phrase="承运商",
                canonical_object=catalog.objects[2],
                method="bounded_llm",
            ),
        ],
    )
    report = SemanticObligationCoverageGate().inspect(
        user_input="哪个承运商延误最严重？",
        outcome=outcome,
        catalog=catalog,
        relation=TurnRelationEvidence.classify("哪个承运商延误最严重？"),
    )

    assert report.executable
    assert not report.unresolved_phrases
    assert not report.unresolved_phrases


@pytest.mark.parametrize("cue", ["独立问题", "新问题", "重新开始", "忽略之前", "单独问", "重新分析"])
def test_explicit_fresh_cues_are_shared_structured_evidence(cue: str) -> None:
    evidence = TurnRelationEvidence.classify(f"{cue}：2026年1月平均延误小时数")
    assert evidence.kind == TurnRelationKind.FRESH
    assert evidence.explicit
    assert evidence.matched_cue == cue


@pytest.mark.parametrize(
    ("shape", "updates", "code"),
    [
        (QueryShape.GROUPED, {}, "canonical_shape_grouped_dimension_required"),
        (QueryShape.RANKING, {"sort": "desc", "top_n": 3}, "canonical_shape_ranking_dimension_required"),
        (QueryShape.RANKING, {"dimensions": ["Carrier"], "top_n": 3}, "canonical_shape_ranking_sort_required"),
        (QueryShape.RANKING, {"dimensions": ["Carrier"], "sort": "desc"}, "canonical_shape_ranking_top_n_required"),
        (QueryShape.FILTERED_AGGREGATION, {}, "canonical_shape_filtered_filter_required"),
        (QueryShape.TREND, {}, "canonical_shape_trend_temporal_dimension_required"),
        (QueryShape.BOUNDED_TREND, {"dimensions": ["Month"], "dimension_order": "asc"}, "canonical_shape_bounded_trend_time_required"),
    ],
)
def test_incomplete_canonical_shapes_fail_closed(shape: QueryShape, updates: dict[str, object], code: str) -> None:
    with pytest.raises(CanonicalShapeCompletenessError, match=code):
        CanonicalShapeCompletenessGate().validate(_plan(shape, **updates), catalog=_catalog())


def test_complete_ranking_and_bounded_trend_pass() -> None:
    ranking = _plan(QueryShape.RANKING, dimensions=["Carrier"], sort="desc", top_n=3)
    bounded = _plan(
        QueryShape.BOUNDED_TREND,
        dimensions=["Month"],
        dimension_order="asc",
        time_range=TimeRangeSpec(
            mode=TimeRangeMode.EXPLICIT_RANGE,
            start_date=date(2025, 8, 1),
            end_date=date(2026, 1, 31),
            date_field="Month",
        ),
    )
    assert CanonicalShapeCompletenessGate().validate(ranking, catalog=_catalog()).complete
    assert CanonicalShapeCompletenessGate().validate(bounded, catalog=_catalog()).complete


def test_member_set_requires_one_authoritative_field_and_complete_values() -> None:
    valid = _plan(
        QueryShape.MEMBER_SET,
        dimensions=["Hub"],
        filters=[StructuredFilter(field="Hub", operator=FilterOperator.IN_SET, value=["North Hub", "South Hub"])],
    )
    assert CanonicalShapeCompletenessGate().validate(valid, catalog=_catalog()).complete
    invalid = valid.model_copy(update={"filters": [StructuredFilter(field="Hub", operator=FilterOperator.IN_SET, value=[])]})
    with pytest.raises(CanonicalShapeCompletenessError, match="canonical_shape_member_set_values_required"):
        CanonicalShapeCompletenessGate().validate(invalid, catalog=_catalog())
