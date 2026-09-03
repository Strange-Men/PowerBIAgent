from __future__ import annotations

from datetime import date

from backend.app.facts.verified import FactBoundedAnswerBuilder, VerifiedFactSetBuilder
from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.query_scope import DeterministicQueryScopeDescriptor
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
        "measures": ["Package Count"],
        "dimensions": [],
    }
    values.update(updates)
    return CanonicalQueryPlan.model_validate(values)


def _result(rows: list[list[object]], columns: list[str]) -> QueryResult:
    return QueryResult(
        result_id="r1", semantic_model_key="model", columns=columns,
        rows=rows, row_count=len(rows), source_mode="real",
    )


def test_scope_descriptor_is_plan_owned_and_answer_cannot_omit_it() -> None:
    plan = _plan(
        QueryShape.FILTERED_AGGREGATION,
        filters=[StructuredFilter(field="Hub", value="North Hub")],
        time_range=TimeRangeSpec(
            mode=TimeRangeMode.EXPLICIT_RANGE,
            start_date=date(2025, 5, 1),
            end_date=date(2025, 5, 31),
            date_field="Ship Date",
        ),
    )
    result = _result([[125]], ["Package Count"])
    facts = VerifiedFactSetBuilder().build(plan, result)
    scope = DeterministicQueryScopeDescriptor().build(plan)
    answer = FactBoundedAnswerBuilder().build(plan, result, facts, effective_scope=scope)
    assert scope == "2025年5月 · North Hub · Package Count"
    assert answer.answer.startswith(scope + "：")
    assert answer.evidence["effective_scope"] == scope


def test_grouped_display_projection_sorts_metric_desc_without_mutating_facts() -> None:
    plan = _plan(QueryShape.GROUPED, dimensions=["Carrier"])
    result = _result(
        [["A", 4], ["B", 9], ["C", 6]],
        ["DimCarrier[Carrier]", "[Package Count]"],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    envelope = StructuredPresentationBuilder.build_answer(plan, result, facts, "answer")
    assert result.rows == [["A", 4], ["B", 9], ["C", 6]]
    assert envelope.datasets[0].rows == [["B", 9], ["C", 6], ["A", 4]]
    assert [fact.source_rows for fact in facts.by_type(facts.facts[0].fact_type)][:1] == [[0]]


def test_explicit_ranking_order_is_preserved_for_table_and_chart_dataset() -> None:
    plan = _plan(QueryShape.RANKING, dimensions=["Carrier"], sort="desc", top_n=3)
    result = _result([["B", 9], ["C", 6], ["A", 4]], ["Carrier", "Package Count"])
    facts = VerifiedFactSetBuilder().build(plan, result)
    envelope = StructuredPresentationBuilder.build_answer(plan, result, facts, "answer")
    assert envelope.datasets[0].rows == result.rows


def test_trend_display_projection_sorts_calendar_values_asc_without_mutating_facts() -> None:
    plan = _plan(QueryShape.TREND, dimensions=["YearMonth"])
    result = _result(
        [["2025年10月", 4], ["2025年2月", 9], ["2025年8月", 6]],
        ["DimDate[YearMonth]", "[Package Count]"],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    envelope = StructuredPresentationBuilder.build_answer(plan, result, facts, "answer")

    assert result.rows == [["2025年10月", 4], ["2025年2月", 9], ["2025年8月", 6]]
    assert envelope.datasets[0].rows == [
        ["2025年2月", 9], ["2025年8月", 6], ["2025年10月", 4],
    ]
