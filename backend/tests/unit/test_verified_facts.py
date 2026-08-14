"""VerifiedFactSet and fact-bounded Answer/Report contracts."""

from datetime import date

from backend.app.facts import (
    FactBoundedAnswerBuilder,
    FactBoundedReportBuilder,
    FactOutputValidator,
    FactType,
    VerifiedFactSetBuilder,
)
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    CanonicalQueryPlan,
    QueryResult,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


def _plan(**updates):
    values = {
        "normalized_question": "query",
        "semantic_model_key": "model",
        "measures": ["Total Sales"],
    }
    values.update(updates)
    return CanonicalQueryPlan(**values)


def _result(columns=None, rows=None, **updates):
    columns = columns or ["[Total Sales]"]
    rows = [[100]] if rows is None else rows
    values = {
        "result_id": "result-1",
        "semantic_model_key": "model",
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "source_mode": "real",
    }
    values.update(updates)
    return QueryResult(**values)


def test_scalar_fact_has_direct_row_provenance():
    facts = VerifiedFactSetBuilder().build(_plan(), _result())
    metric = facts.by_type(FactType.SCALAR_METRIC)[0]
    assert metric.value == 100
    assert metric.measure == "Total Sales"
    assert metric.source_fields == ["[Total Sales]"]
    assert metric.source_rows == [0]
    assert metric.provenance.result_id == "result-1"
    assert metric.provenance.source_mode == "real"


def test_grouped_facts_and_result_set_extrema_are_deterministic():
    plan = _plan(dimensions=["Category"])
    result = _result(
        ["Sales[Category]", "[Total Sales]"],
        [["A", 10], ["B", 20]],
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    grouped = facts.by_type(FactType.GROUPED_METRIC)
    maximum = facts.by_type(FactType.MAXIMUM)[0]
    minimum = facts.by_type(FactType.MINIMUM)[0]
    assert [item.dimensions for item in grouped] == [
        {"Category": "A"}, {"Category": "B"}
    ]
    assert (maximum.value, maximum.source_rows) == (20, [1])
    assert (minimum.value, minimum.source_rows) == (10, [0])


def test_topn_ranking_preserves_query_result_order():
    plan = _plan(dimensions=["Category"], sort="desc", top_n=2)
    result = _result(
        ["[Category]", "[Total Sales]"], [["B", 20], ["A", 10]]
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    ranking = facts.by_type(FactType.RANKING)[0]
    assert ranking.value == {
        "top_n": 2, "direction": "desc", "measure": "Total Sales"
    }
    assert [item["position"] for item in ranking.values] == [1, 2]
    assert [item["value"] for item in ranking.values] == [20, 10]


def test_filter_time_and_metadata_provenance():
    time_range = TimeRangeSpec(
        date_field="OrderDate",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 8, 14),
        mode=TimeRangeMode.EXPLICIT_RANGE,
    )
    plan = _plan(
        filters=[StructuredFilter(field="Category", value="A")],
        time_range=time_range,
    )
    facts = VerifiedFactSetBuilder().build(plan, _result(truncated=True))
    assert facts.by_type(FactType.APPLIED_FILTER)[0].value["value"] == "A"
    assert facts.by_type(FactType.APPLIED_TIME_RANGE)[0].time_range == time_range
    metadata = facts.by_type(FactType.RESULT_METADATA)[0]
    assert metadata.value == {"row_count": 1, "truncated": True, "empty": False}


def test_truncated_grouped_result_does_not_claim_extrema():
    facts = VerifiedFactSetBuilder().build(
        _plan(dimensions=["Category"]),
        _result(["[Category]", "[Total Sales]"], [["A", 10]], truncated=True),
    )
    assert not facts.by_type(FactType.MAXIMUM)
    assert not facts.by_type(FactType.MINIMUM)


def test_empty_result_has_only_context_and_metadata_no_metric():
    facts = VerifiedFactSetBuilder().build(_plan(), _result(rows=[]))
    assert facts.empty is True
    assert not facts.by_type(FactType.SCALAR_METRIC)
    assert facts.by_type(FactType.RESULT_METADATA)


def test_factset_has_no_causal_fact_type():
    facts = VerifiedFactSetBuilder().build(_plan(), _result())
    assert all("caus" not in item.fact_type.value for item in facts.facts)


def test_fact_bounded_answer_is_accepted_and_invented_number_rejected():
    plan = _plan()
    result = _result()
    facts = VerifiedFactSetBuilder().build(plan, result)
    answer = FactBoundedAnswerBuilder().build(plan, result, facts)
    validator = FactOutputValidator()
    assert validator.validate_answer(answer, facts) == []
    invented = answer.model_copy(update={"answer": "Total Sales为999。"})
    assert "unverified_numeric_claim" in validator.validate_answer(invented, facts)


def test_invented_ranking_and_causal_claim_are_rejected():
    plan = _plan()
    result = _result()
    facts = VerifiedFactSetBuilder().build(plan, result)
    answer = FactBoundedAnswerBuilder().build(plan, result, facts)
    validator = FactOutputValidator()
    ranking = answer.model_copy(update={"answer": "A排名第一。"})
    causal = answer.model_copy(update={"answer": "因为库存不足导致销售变化。"})
    assert "unverified_ranking_claim" in validator.validate_answer(ranking, facts)
    assert "unverified_causal_claim" in validator.validate_answer(causal, facts)


def test_group_member_containing_ordinal_word_is_not_a_ranking_claim():
    plan = _plan(dimensions=["Product"])
    result = _result(
        ["Product", "[Total Sales]"], [["第一代产品", 10]]
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    answer = FactBoundedAnswerBuilder().build(plan, result, facts)

    assert FactOutputValidator().validate_answer(answer, facts) == []


def test_report_uses_verified_fields_and_full_query_result_projection():
    plan = _plan(dimensions=["Category"], requested_template="sales_weekly")
    result = _result(
        ["[Category]", "[Total Sales]"], [["A", 10], ["B", 20]]
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    report = FactBoundedReportBuilder().build(plan, result, facts)
    validator = FactOutputValidator()
    assert validator.validate_report(report, facts, result) == []
    assert report.tables[0].rows == result.rows
    assert report.charts[0].x_field == "[Category]"


def test_unverified_report_insight_and_incomplete_table_are_rejected():
    plan = _plan(dimensions=["Category"], requested_template="sales_weekly")
    result = _result(
        ["[Category]", "[Total Sales]"], [["A", 10], ["B", 20]]
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    report = FactBoundedReportBuilder().build(plan, result, facts)
    validator = FactOutputValidator()
    invented = report.model_copy(update={"insights": ["因为库存不足，销售下降999。"]})
    incomplete = report.model_copy(deep=True)
    incomplete.tables[0].rows = incomplete.tables[0].rows[:1]
    errors = validator.validate_report(invented, facts, result)
    assert "unverified_causal_claim" in errors
    assert "unverified_trend_claim" in errors
    assert "unverified_numeric_claim" in errors
    assert "report_table_not_full_query_result_projection" in validator.validate_report(
        incomplete, facts, result
    )
