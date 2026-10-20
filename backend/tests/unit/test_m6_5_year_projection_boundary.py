"""Failure-first reproduction of integer Year being treated as a month date."""
from decimal import Decimal
import pytest

from backend.app.facts import VerifiedFactSetBuilder, FactBoundedAnswerBuilder
from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.formatter import PresentationFormatKind
from backend.app.query_plan.semantic_catalog import SemanticObjectType
from backend.app.schemas.data_contracts import QueryShape, TimeRangeSpec, TimeRangeMode
from datetime import date
from backend.tests.unit.test_presentation_contract import _plan, _result, _binding


def year_artifacts(numeric_type):
    plan = _plan(dimensions=['Year'])
    result = _result(['Year', 'Total Sales'], [
        [2009, numeric_type(825685)],
        [2010, numeric_type(10303952)],
        [2011, numeric_type(9842956)],
    ])
    facts = VerifiedFactSetBuilder().build(plan, result)
    bindings = dict([
        _binding('Year', 'Year', 'Year', object_type=SemanticObjectType.FIELD,
                 kind=PresentationFormatKind.INTEGER),
        _binding('Total Sales', 'Total Sales', 'Total Sales',
                 object_type=SemanticObjectType.MEASURE, kind=PresentationFormatKind.DECIMAL),
    ])
    return plan, result, facts, bindings


@pytest.mark.parametrize('numeric_type', [int, Decimal])
def test_verified_integer_year_group_does_not_become_month_date(numeric_type):
    plan, result, facts, bindings = year_artifacts(numeric_type)
    projected = StructuredPresentationBuilder.build_answer(
        plan, result, facts, 'verified projection', display_bindings=bindings)
    assert projected.datasets[0].display_fields[0].format_kind == 'integer'
    assert {row[0] for row in projected.datasets[0].rows} == {2009, 2010, 2011}
    assert {row[0] for row in projected.datasets[0].formatted_rows} == {'2009', '2010', '2011'}
    assert projected.blocks[-1].visual_type == 'bar'


@pytest.mark.parametrize('numeric_type', [int, Decimal])
def test_year_answer_preserves_verified_integer_dimension(numeric_type):
    plan, result, facts, bindings = year_artifacts(numeric_type)
    answer = FactBoundedAnswerBuilder().build(plan, result, facts, display_bindings=bindings)
    assert answer.fact_ids
    assert '2010' in answer.answer
    assert '2,010' not in answer.answer


@pytest.mark.parametrize('name', ['Month', 'Date', 'YearMonth', 'Fiscal Period'])
def test_numeric_category_name_does_not_prove_date_or_month(name):
    plan = _plan(dimensions=[name])
    result = _result([name, 'Total Sales'], [[2010, 10], [2011, 20]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    bindings = dict([
        _binding(name, name, name, object_type=SemanticObjectType.FIELD,
                 kind=PresentationFormatKind.INTEGER),
        _binding('Total Sales', 'Total Sales', 'Total Sales',
                 object_type=SemanticObjectType.MEASURE, kind=PresentationFormatKind.DECIMAL),
    ])
    projected = StructuredPresentationBuilder.build_answer(plan, result, facts, 'verified projection', display_bindings=bindings)
    assert projected.datasets[0].formatted_rows[0][0] in {'2010', '2011'}
    assert projected.blocks[-1].visual_type == 'bar'
    assert FactBoundedAnswerBuilder().build(plan, result, facts, display_bindings=bindings).fact_ids


@pytest.mark.parametrize('grain,kind,expected', [
    ('month', PresentationFormatKind.DATE, '2026年1月'),
    (None, PresentationFormatKind.DATE, '2026年1月2日'),
    (None, PresentationFormatKind.TEXT, '2026-01-02'),
])
def test_existing_binding_grain_controls_format_without_value_guess(grain, kind, expected):
    plan = _plan(dimensions=['Period'])
    result = _result(['Period', 'Total Sales'], [['2026-01-02', 10]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    bindings = dict([
        _binding('Period', 'Period', 'Period', object_type=SemanticObjectType.FIELD, kind=kind),
        _binding('Total Sales', 'Total Sales', 'Total Sales', object_type=SemanticObjectType.MEASURE,
                 kind=PresentationFormatKind.DECIMAL),
    ])
    bindings['Period'] = bindings['Period'].model_copy(update={'temporal_grain': grain})
    projected = StructuredPresentationBuilder.build_answer(plan, result, facts, 'verified projection', display_bindings=bindings)
    assert projected.datasets[0].formatted_rows[0][0] == expected
    answer = FactBoundedAnswerBuilder().build(plan, result, facts, display_bindings=bindings)
    assert expected in answer.answer
    assert result.rows == [['2026-01-02', 10]]


def test_existing_year_grain_is_line_category_without_month_format():
    plan,result,facts,bindings=year_artifacts(Decimal)
    bindings['Year']=bindings['Year'].model_copy(update={'temporal_grain':'year'})
    projected=StructuredPresentationBuilder.build_answer(plan,result,facts,'verified projection',display_bindings=bindings)
    assert projected.blocks[-1].visual_type=='line'
    assert projected.datasets[0].display_fields[0].format_kind=='integer'
    assert {row[0] for row in projected.datasets[0].formatted_rows}=={'2009','2010','2011'}


def test_grouped_date_time_filter_does_not_change_date_to_month_grain():
    plan=_plan(dimensions=['OccurredOn']).model_copy(update={
        'query_shape':QueryShape.GROUPED,'time_range':TimeRangeSpec(
            date_field='OccurredOn',start_date=date(2026,1,1),end_date=date(2026,2,28),
            mode=TimeRangeMode.EXPLICIT_RANGE,grain='month')})
    result=_result(['OccurredOn','Total Sales'],[['2026-01-02',10]])
    facts=VerifiedFactSetBuilder().build(plan,result)
    bindings=dict([
        _binding('OccurredOn','OccurredOn','OccurredOn',object_type=SemanticObjectType.FIELD,kind=PresentationFormatKind.DATE),
        _binding('Total Sales','Total Sales','Total Sales',object_type=SemanticObjectType.MEASURE,kind=PresentationFormatKind.DECIMAL),
    ])
    projected=StructuredPresentationBuilder.build_answer(plan,result,facts,'verified projection',display_bindings=bindings)
    assert projected.datasets[0].formatted_rows[0][0]=='2026年1月2日'
