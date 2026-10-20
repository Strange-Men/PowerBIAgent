"""Verified numeric representation compatibility, without coercion or authority changes."""
from decimal import Decimal

import pytest

from backend.app.facts import (
    FactBoundedAnswerBuilder, FactBoundedReportBuilder, FactOutputValidator,
    VerifiedFactSetBuilder,
)
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.presentation.models import is_presentation_number
from backend.app.schemas.data_contracts import KPISpec
from backend.app.report.assembly import KpiValue, TrendPoint, GroupedValue, TopNValue
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.executive import ExecutiveSalesReportRenderer
from backend.tests.unit.test_verified_facts import _plan, _result


GOOD = [Decimal('20972594.5680'), Decimal('-1526667.8600'),
        Decimal('523.3075'), 42, 523.3075]
BAD = [Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'),
       Decimal('-Infinity'), float('nan'), float('inf'), True,
       '523.3075', '£10', object()]


def artifacts(value):
    plan, result = _plan(requested_template='sales_report'), _result(rows=[[value]])
    facts = VerifiedFactSetBuilder().build(plan, result)
    answer = FactBoundedAnswerBuilder().build(plan, result, facts)
    report = FactBoundedReportBuilder().build(plan, result, facts)
    return result, facts, answer, report


@pytest.mark.parametrize('value', GOOD)
def test_verified_answer_report_and_projection_preserve_numeric_value(value):
    result, facts, answer, report = artifacts(value)
    assert answer.metrics['Total Sales'] is value
    assert report.kpis[0].value is value
    assert not ValidationService._validate_answer_metrics_strict(answer, result)
    assert not ValidationService._validate_kpis_strict(
        report.kpis, result.columns, result.rows, False)
    assert not FactOutputValidator().validate_answer(answer, facts)
    assert not FactOutputValidator().validate_report(report, facts, result)
    assert is_presentation_number(value)


@pytest.mark.parametrize('value', BAD)
def test_invalid_numeric_claims_rejected_by_all_consuming_gates(value):
    result, facts, answer, report = artifacts(Decimal('523.3075'))
    answer = answer.model_copy(update={'metrics': {'Total Sales': value}})
    report = report.model_copy(update={'kpis': [
        KPISpec(name='Total Sales', field=result.columns[0], value=value)]})
    assert ValidationService._validate_answer_metrics_strict(answer, result)
    assert ValidationService._validate_kpis_strict(report.kpis, result.columns, result.rows, False)
    assert FactOutputValidator().validate_answer(answer, facts)
    assert FactOutputValidator().validate_report(report, facts, result)
    assert not is_presentation_number(value)


def test_bool_cannot_equal_verified_integer_and_string_cannot_equal_decimal_kpi():
    result, facts, answer, report = artifacts(1)
    answer = answer.model_copy(update={'metrics': {'Total Sales': True}})
    assert FactOutputValidator().validate_answer(answer, facts)
    result, facts, answer, report = artifacts(Decimal('523.3075'))
    report.kpis[0].value = '523.3075'
    assert FactOutputValidator().validate_report(report, facts, result)


@pytest.mark.parametrize('value', GOOD)
def test_numeric_without_provenance_or_fact_binding_remains_rejected(value):
    result, facts, answer, report = artifacts(value)
    assert ValidationService._validate_answer_metrics_strict(
        answer.model_copy(update={'evidence': {}}), result)
    assert FactOutputValidator().validate_answer(
        answer.model_copy(update={'fact_ids': [], 'verified_fact_set_id': ''}), facts)
    assert FactOutputValidator().validate_report(
        report.model_copy(update={'fact_ids': [], 'verified_fact_set_id': ''}), facts, result)


@pytest.mark.parametrize('value', [True, '523.3075', Decimal('NaN'), Decimal('Infinity')])
def test_invalid_source_number_cannot_prove_answer(value):
    result, facts, answer, report = artifacts(Decimal('523.3075'))
    result = result.model_copy(update={'rows': [[value]]})
    assert ValidationService._validate_answer_metrics_strict(answer, result)


def test_decimal_provenance_does_not_convert_to_float_or_round():
    class NoFloatDecimal(Decimal):
        def __float__(self):
            raise AssertionError('verified Decimal must not be converted to float')
    value = NoFloatDecimal('20972594.568012345678901234')
    result, facts, answer, report = artifacts(value)
    assert not ValidationService._validate_answer_metrics_strict(answer, result)
    assert not ValidationService._validate_kpis_strict(report.kpis, result.columns, result.rows, False)
    assert answer.metrics['Total Sales'].as_tuple() == value.as_tuple()


@pytest.mark.parametrize('value', [Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'), '523.3075', True])
def test_invalid_verified_numeric_representation_rejected_without_exception(value):
    result, facts, answer, report = artifacts(Decimal('523.3075'))
    altered = [item.model_copy(update={'value': value})
               if item.measure == 'Total Sales' else item for item in facts.facts]
    facts = facts.model_copy(update={'facts': altered})
    assert FactOutputValidator().validate_answer(answer, facts)
    assert FactOutputValidator().validate_report(report, facts, result)


@pytest.mark.parametrize('model,kwargs', [
    (KpiValue, {'requirement_key': 'total_sales', 'label': 'Sales', 'measure': 'Total Sales', 'format': 'number'}),
    (TrendPoint, {'period': '2011-01'}), (GroupedValue, {'label': 'France'}),
    (TopNValue, {'result_position': 1, 'label': 'France'}),
])
@pytest.mark.parametrize('value', [True, '523.3075', Decimal('NaN'), Decimal('Infinity')])
def test_report_verified_value_gate_rejects_coercion(model, kwargs, value):
    with pytest.raises(ValueError):
        model(value=value, **kwargs)


@pytest.mark.parametrize('renderer', [SalesReportRenderer, ExecutiveSalesReportRenderer])
@pytest.mark.parametrize('value', BAD)
def test_renderer_numeric_gate_never_parses_untyped_values(renderer, value):
    with pytest.raises(ValueError):
        renderer._decimal(value)


@pytest.mark.parametrize('renderer', [SalesReportRenderer, ExecutiveSalesReportRenderer])
@pytest.mark.parametrize('value', GOOD)
def test_renderer_accepts_existing_finite_numeric_types(renderer, value):
    normalized = renderer._decimal(value)
    assert normalized == (value if isinstance(value, Decimal) else Decimal(str(value)))


@pytest.mark.parametrize('aggregation,value', [
    ('sum', Decimal('30.5000')), ('avg', Decimal('15.2500')),
    ('min', Decimal('10.2500')), ('max', Decimal('20.2500')), ('count', 2),
])
def test_existing_aggregations_accept_decimal_sources(aggregation, value):
    result, facts, answer, report = artifacts(value)
    result = result.model_copy(update={'rows': [[Decimal('10.2500')], [Decimal('20.2500')]], 'row_count': 2})
    answer.evidence['metric_provenance']['Total Sales']['aggregation'] = aggregation
    assert not ValidationService._validate_answer_metrics_strict(answer, result)
