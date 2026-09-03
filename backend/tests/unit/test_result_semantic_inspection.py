from __future__ import annotations

from datetime import date

import pytest

from backend.app.facts.inspection import (
    ResultSemanticInspectionError,
    ResultSemanticInspectionGate,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    QueryResult,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


def _plan(shape: QueryShape, **updates: object) -> CanonicalQueryPlan:
    values: dict[str, object] = {
        "normalized_question": "test",
        "semantic_model_key": "model",
        "query_shape": shape,
        "measures": ["Metric"],
        "dimensions": ["Entity"],
    }
    values.update(updates)
    return CanonicalQueryPlan.model_validate(values)


def _result(rows: list[list[object]], columns: list[str] | None = None) -> QueryResult:
    return QueryResult(
        result_id="result-1",
        semantic_model_key="model",
        columns=columns or ["Entity", "Metric"],
        rows=rows,
        row_count=len(rows),
        source_mode="real",
    )


def test_ranking_topn_row_count_and_descending_order_are_inspected() -> None:
    plan = _plan(QueryShape.RANKING, sort="desc", top_n=3)
    passed = ResultSemanticInspectionGate().inspect(plan, _result([["A", 9], ["B", 7], ["C", 7]]))
    assert passed.passed and passed.canonical_order_preserved

    with pytest.raises(ResultSemanticInspectionError, match="result_ranking_row_count_exceeds_top_n"):
        ResultSemanticInspectionGate().inspect(plan, _result([["A", 9], ["B", 8], ["C", 7], ["D", 6]]))
    with pytest.raises(ResultSemanticInspectionError, match="result_ranking_order_mismatch"):
        ResultSemanticInspectionGate().inspect(plan, _result([["A", 9], ["B", 10]]))
    with pytest.raises(
        ResultSemanticInspectionError,
        match="result_ranking_tiebreak_order_mismatch",
    ):
        ResultSemanticInspectionGate().inspect(
            plan,
            _result([["A", 9], ["C", 7], ["B", 7]]),
        )


def test_top1_requires_exactly_one_row() -> None:
    plan = _plan(QueryShape.RANKING, sort="asc", top_n=1)
    with pytest.raises(ResultSemanticInspectionError, match="result_ranking_top1_row_count_invalid"):
        ResultSemanticInspectionGate().inspect(plan, _result([]))


def test_trend_requires_temporal_ascending_and_range_containment() -> None:
    plan = _plan(
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
    columns = ["Month", "Metric"]
    assert ResultSemanticInspectionGate().inspect(
        plan, _result([["2025-08-01", 1], ["2026-01-01", 2]], columns)
    ).passed
    with pytest.raises(ResultSemanticInspectionError, match="result_trend_order_mismatch"):
        ResultSemanticInspectionGate().inspect(
            plan, _result([["2026-01-01", 2], ["2025-08-01", 1]], columns)
        )
    with pytest.raises(ResultSemanticInspectionError, match="result_trend_outside_requested_range"):
        ResultSemanticInspectionGate().inspect(
            plan, _result([["2025-07-01", 1]], columns)
        )


def test_entity_list_distinct_semantics_and_scope_lineage() -> None:
    entity_plan = _plan(QueryShape.ENTITY_LIST, measures=[])
    with pytest.raises(ResultSemanticInspectionError, match="result_entity_list_duplicate"):
        ResultSemanticInspectionGate().inspect(entity_plan, _result([["A", 1], ["A", 2]]))

    filtered = _plan(
        QueryShape.FILTERED_AGGREGATION,
        dimensions=[],
        filters=[StructuredFilter(field="Region", value="North")],
    )
    inspection = ResultSemanticInspectionGate().inspect(filtered, _result([[5]], ["Metric"]))
    assert inspection.scope_lineage_hash
    assert inspection.filters_preserved
