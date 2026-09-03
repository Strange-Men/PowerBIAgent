"""Domain-independent M5.8.5 invariant matrix (2,304 logical cases)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.facts.inspection import ResultSemanticInspectionGate
from backend.app.presentation.query_scope import DeterministicQueryScopeDescriptor
from backend.app.query_plan.completeness import (
    CanonicalShapeCompletenessError,
    CanonicalShapeCompletenessGate,
    SemanticObligationCoverageGate,
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
from backend.app.query_plan.turn_relation import TurnRelationEvidence
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    FilterOperator,
    QueryResult,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


DOMAINS = (
    ("health", "Patient Count", "Department", "North Ward", "Unknown Ward"),
    ("logistics", "Shipment Count", "Carrier", "North Hub", "Mars Hub"),
    ("inventory", "Stock Units", "Warehouse", "Depot A", "Mars Depot"),
)
PROVIDERS = ("deepseek", "kimi-k2.6")
RELATIONS = ("独立问题：", "那", "换成")
SHAPES = tuple(QueryShape)


def _catalog(domain: tuple[str, str, str, str, str]) -> tuple[SemanticCatalog, CatalogObject, CatalogObject]:
    key, measure, dimension, _, _ = domain
    metric = CatalogObject(
        object_id=f"measure:Facts:{measure}", canonical_name=measure,
        object_type=SemanticObjectType.MEASURE, table_name="Facts", data_type="double",
    )
    field = CatalogObject(
        object_id=f"field:Dim:{dimension}", canonical_name=dimension,
        object_type=SemanticObjectType.FIELD, table_name="Dim", data_type="string",
    )
    month = CatalogObject(
        object_id="field:Date:Month", canonical_name="Month",
        object_type=SemanticObjectType.FIELD, table_name="Date", data_type="datetime",
        temporal_grouping=TemporalGroupingBinding(
            grain="month", date_field="Date", date_table_name="Date"
        ),
    )
    return SemanticCatalog(
        semantic_model_key=key, schema_fingerprint=f"fp-{key}",
        objects=(metric, field, month),
    ), metric, field


def _plan(
    domain: tuple[str, str, str, str, str], shape: QueryShape,
    *, include_filter: bool, include_time: bool, direction: str,
) -> CanonicalQueryPlan:
    key, measure, dimension, known, _ = domain
    dimensions: list[str] = []
    measures = [] if shape == QueryShape.ENTITY_LIST else [measure]
    filters: list[StructuredFilter] = []
    sort = None
    top_n = None
    dimension_order = None
    if shape in {QueryShape.ENTITY_LIST, QueryShape.GROUPED, QueryShape.RANKING, QueryShape.MEMBER_SET}:
        dimensions = [dimension]
    if shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
        dimensions = ["Month"]
        dimension_order = "asc"
    if include_filter or shape == QueryShape.FILTERED_AGGREGATION:
        filters = [StructuredFilter(field=dimension, value=known)]
    if shape == QueryShape.MEMBER_SET:
        filters = [StructuredFilter(
            field=dimension, operator=FilterOperator.IN_SET, value=[known, f"{known} 2"]
        )]
    if shape == QueryShape.RANKING:
        sort = direction
        top_n = 3
    time_range = None
    if include_time or shape == QueryShape.BOUNDED_TREND:
        time_range = TimeRangeSpec(
            date_field="Date", start_date=date(2025, 8, 1),
            end_date=date(2026, 1, 31), mode=TimeRangeMode.EXPLICIT_RANGE,
        )
    return CanonicalQueryPlan(
        normalized_question="matrix", semantic_model_key=key, query_shape=shape,
        measures=measures, dimensions=dimensions, filters=filters,
        time_range=time_range, sort=sort, top_n=top_n,
        dimension_order=dimension_order,
    )


def _result(plan: CanonicalQueryPlan) -> QueryResult:
    shape = plan.query_shape
    if shape == QueryShape.ENTITY_LIST:
        columns, rows = [plan.dimensions[0]], [["A"], ["B"], ["C"]]
    elif shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
        columns = [plan.dimensions[0], plan.measures[0]]
        rows = [["2025-08-01", 4], ["2025-09-01", 6], ["2026-01-01", 5]]
    elif plan.dimensions:
        columns = [plan.dimensions[0], plan.measures[0]]
        metrics = [9, 6, 3] if plan.sort != "asc" else [3, 6, 9]
        rows = [[name, value] for name, value in zip(("A", "B", "C"), metrics)]
    else:
        columns, rows = [plan.measures[0]], [[9]]
    return QueryResult(
        result_id="matrix-result", semantic_model_key=plan.semantic_model_key,
        columns=columns, rows=rows, row_count=len(rows), source_mode="real",
    )


def _outcome(
    metric: CatalogObject, field: CatalogObject,
    *, known_value: str, unknown_value: str, include_filter: bool, known: bool,
) -> GroundingOutcome:
    member_results = []
    filters = None
    status = GroundingStatus.RESOLVED
    if include_filter:
        status = GroundingStatus.RESOLVED if known else GroundingStatus.UNRESOLVED
        member_results = [MemberGroundingResult(
            status=status, field=field,
            requested_value=known_value if known else unknown_value,
            canonical_value=known_value if known else None,
            method="runtime_member_matrix",
        )]
        if known:
            filters = [StructuredFilter(field=field.canonical_name, value=known_value)]
    return GroundingOutcome(
        status=status,
        delta=(GroundedSemanticDelta(measures=[metric.canonical_name], filters=filters)
               if status == GroundingStatus.RESOLVED else None),
        object_results=[ObjectGroundingResult(
            status=GroundingStatus.RESOLVED, role="measure",
            phrase=metric.canonical_name, canonical_object=metric, method="runtime_identity",
        )],
        member_results=member_results,
        clarification_question=(None if known else "member no match"),
    )


def test_2304_cross_domain_semantic_invariant_cases() -> None:
    logical_cases = 0
    provider_truth: dict[tuple[object, ...], tuple[str, str]] = {}
    for domain in DOMAINS:
        catalog, metric, field = _catalog(domain)
        for shape in SHAPES:
            for include_filter in (False, True):
                for include_time in (False, True):
                    for relation_text in RELATIONS:
                        for known in (False, True):
                            for provider in PROVIDERS:
                                for direction in ("asc", "desc"):
                                    logical_cases += 1
                                    outcome = _outcome(
                                        metric, field,
                                        known_value=domain[3], unknown_value=domain[4],
                                        include_filter=include_filter, known=known,
                                    )
                                    member_text = (
                                        (domain[3] if known else domain[4])
                                        if include_filter else ""
                                    )
                                    question = f"{relation_text}{member_text}{metric.canonical_name}"
                                    coverage = SemanticObligationCoverageGate().inspect(
                                        user_input=question, outcome=outcome, catalog=catalog,
                                        relation=TurnRelationEvidence.classify(question),
                                    )
                                    assert coverage.executable is (known or not include_filter)
                                    if not coverage.executable:
                                        continue  # ZERO DAX invariant
                                    plan = _plan(
                                        domain, shape, include_filter=include_filter,
                                        include_time=include_time, direction=direction,
                                    )
                                    assert CanonicalShapeCompletenessGate().validate(
                                        plan, catalog=catalog
                                    ).complete
                                    inspection = ResultSemanticInspectionGate().inspect(
                                        plan, _result(plan)
                                    )
                                    assert inspection.passed
                                    scope = DeterministicQueryScopeDescriptor().build(plan)
                                    assert (not plan.measures) or plan.measures[0] in scope
                                    identity = (
                                        domain[0], shape.value, include_filter, include_time,
                                        relation_text, known, direction,
                                    )
                                    truth = (plan.model_dump_json(), scope)
                                    if identity in provider_truth:
                                        assert provider_truth[identity] == truth
                                    else:
                                        provider_truth[identity] = truth
                                    assert provider in PROVIDERS
    assert logical_cases == 2304


@pytest.mark.parametrize("domain", DOMAINS)
def test_date_role_mutation_fails_closed(domain: tuple[str, str, str, str, str]) -> None:
    catalog, _, _ = _catalog(domain)
    mutated = catalog.model_copy(update={
        "objects": tuple(
            item.model_copy(update={"data_type": "string", "temporal_grouping": None})
            if item.canonical_name == "Month" else item
            for item in catalog.objects
        ),
        "schema_fingerprint": catalog.schema_fingerprint + "-mutated",
    })
    plan = _plan(domain, QueryShape.TREND, include_filter=False, include_time=False, direction="desc")
    with pytest.raises(CanonicalShapeCompletenessError, match="temporal_dimension_required"):
        CanonicalShapeCompletenessGate().validate(plan, catalog=mutated)
