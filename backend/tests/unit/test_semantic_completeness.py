"""Canonical completeness tests after language coverage moved to Understanding."""

from datetime import date

import pytest

from backend.app.query_plan.completeness import (
    CanonicalShapeCompletenessError,
    CanonicalShapeCompletenessGate,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    FilterOperator,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


def _plan(shape: QueryShape, **updates) -> CanonicalQueryPlan:
    values = {
        "normalized_question": "query",
        "semantic_model_key": "model",
        "query_shape": shape,
        "measures": ["Metric"],
    }
    values.update(updates)
    return CanonicalQueryPlan(**values)


@pytest.mark.parametrize(
    ("shape", "updates", "code"),
    [
        (QueryShape.SCALAR, {"measures": []}, "canonical_shape_measure_required"),
        (QueryShape.ENTITY_LIST, {"measures": [], "dimensions": []}, "canonical_shape_entity_list_dimension_required"),
        (QueryShape.GROUPED, {"dimensions": []}, "canonical_shape_grouped_dimension_required"),
        (QueryShape.RANKING, {"dimensions": [], "sort": "desc", "top_n": 3}, "canonical_shape_ranking_dimension_required"),
        (QueryShape.RANKING, {"dimensions": ["Entity"], "top_n": 3}, "canonical_shape_ranking_sort_required"),
        (QueryShape.RANKING, {"dimensions": ["Entity"], "sort": "desc"}, "canonical_shape_ranking_top_n_required"),
        (QueryShape.FILTERED_AGGREGATION, {"filters": []}, "canonical_shape_filtered_filter_required"),
        (QueryShape.BOUNDED_TREND, {"dimensions": ["Month"], "dimension_order": "asc"}, "canonical_shape_bounded_trend_time_required"),
    ],
)
def test_incomplete_canonical_shapes_fail_closed(shape, updates, code) -> None:
    with pytest.raises(CanonicalShapeCompletenessError, match=code):
        CanonicalShapeCompletenessGate().validate(_plan(shape, **updates))


def test_complete_ranking_and_bounded_trend_pass() -> None:
    ranking = _plan(
        QueryShape.RANKING,
        dimensions=["Entity"],
        sort="desc",
        top_n=3,
    )
    trend = _plan(
        QueryShape.BOUNDED_TREND,
        dimensions=["Month"],
        dimension_order="asc",
        time_range=TimeRangeSpec(
            date_field="Date",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30),
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month",
        ),
    )

    assert CanonicalShapeCompletenessGate().validate(ranking).complete
    assert CanonicalShapeCompletenessGate().validate(trend).complete


def test_request_scoped_runtime_month_proof_satisfies_temporal_completeness() -> None:
    catalog = SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="0" * 64,
        objects=(
            CatalogObject(
                object_id="field:Date:YearMonth",
                canonical_name="YearMonth",
                object_type=SemanticObjectType.FIELD,
                table_name="Date",
                data_type="datetime",
            ),
        ),
    )
    trend = _plan(
        QueryShape.TREND,
        dimensions=["YearMonth"],
        dimension_tables={"YearMonth": "Date"},
        dimension_order="asc",
    )

    with pytest.raises(
        CanonicalShapeCompletenessError,
        match="canonical_shape_trend_temporal_dimension_required",
    ):
        CanonicalShapeCompletenessGate().validate(trend, catalog=catalog)

    report = CanonicalShapeCompletenessGate().validate(
        trend,
        catalog=catalog,
        runtime_temporal_grouping_ids=("field:Date:YearMonth",),
    )
    assert report.complete


def test_member_set_requires_one_runtime_bound_field_and_complete_values() -> None:
    complete = _plan(
        QueryShape.MEMBER_SET,
        filters=[
            StructuredFilter(
                field="Region",
                operator=FilterOperator.IN_SET,
                value=["North", "South"],
            )
        ],
    )
    assert CanonicalShapeCompletenessGate().validate(complete).complete

    incomplete = complete.model_copy(update={
        "filters": [StructuredFilter(field="Region", value="North")]
    })
    with pytest.raises(
        CanonicalShapeCompletenessError,
        match="canonical_shape_member_set_operator_required",
    ):
        CanonicalShapeCompletenessGate().validate(incomplete)


def test_expected_shape_cannot_be_changed_after_understanding() -> None:
    plan = _plan(QueryShape.SCALAR)
    with pytest.raises(
        CanonicalShapeCompletenessError,
        match="canonical_shape_obligation_mismatch",
    ):
        CanonicalShapeCompletenessGate().validate(
            plan, expected_shape=QueryShape.RANKING
        )
