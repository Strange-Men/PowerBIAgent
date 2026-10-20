"""Year representation needs the existing fresh, exact semantic authority."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from backend.app.facts.inspection import ResultSemanticInspectionGate, ResultSemanticInspectionError
from backend.app.schemas.data_contracts import QueryResult
from backend.tests.unit.test_m6_5_operator_temporal_binding import schema, registry, build, trend_plan


def inspect(values, field='FiscalYear', *, current=None, catalog=None):
    current = current or schema()
    catalog = catalog or build(current, registry(current))
    result = QueryResult(semantic_model_key=current.key, columns=[field, 'Amount'],
                         rows=[[value, Decimal('1.2500')] for value in values],
                         row_count=len(values), source_mode='real')
    original = result.model_dump()
    proof = ResultSemanticInspectionGate().inspect(trend_plan(field), result,
                                                   catalog=catalog, schema=current)
    assert result.model_dump() == original
    return proof


def test_proven_year_integer_axis_preserves_values_and_order():
    assert inspect([2009, 2010, 2011]).passed
    with pytest.raises(ResultSemanticInspectionError, match='order_mismatch'):
        inspect([2011, 2009])


@pytest.mark.parametrize('value', [True, False, 0, -1, 10000, 2009.0,
                                   Decimal('2009'), '2009', 'FY2009', None, object()])
def test_year_authority_rejects_illegal_representation(value):
    with pytest.raises(ResultSemanticInspectionError):
        inspect([value])


def test_integer_without_year_authority_stays_closed():
    current = schema()
    missing = build(current, {'version': 2, 'overrides': []})
    with pytest.raises(ResultSemanticInspectionError):
        inspect([2009], catalog=missing)
    with pytest.raises(ResultSemanticInspectionError):
        inspect([2009], field='Period')
    with pytest.raises(ResultSemanticInspectionError):
        inspect([2009], field='Day')


@pytest.mark.parametrize('mismatch', ['model', 'fingerprint', 'table', 'column', 'runtime', 'generation'])
def test_fresh_exact_binding_required_at_inspection(mismatch):
    current = schema()
    catalog = build(current, registry(current))
    if mismatch == 'model': current = current.model_copy(update={'key': 'another'})
    elif mismatch == 'fingerprint': current.tables[0].columns[0].description = 'drift'
    elif mismatch == 'table': current.tables[0].name = 'Another'
    elif mismatch == 'column': current.tables[0].columns[2].name = 'Another'
    elif mismatch == 'runtime': current.runtime_identity = 'another'
    else: current.session_generation = 8
    with pytest.raises(ResultSemanticInspectionError):
        inspect([2009], current=current, catalog=catalog)


@pytest.mark.parametrize('values', [['2011-01', '2011-02'],
                                  [date(2011, 1, 1), date(2011, 2, 1)],
                                  [datetime(2011, 1, 1), datetime(2011, 2, 1)]])
def test_proven_month_axis_retains_existing_date_contract(values):
    assert inspect(values, field='Period').passed


def test_proven_day_axis_retains_existing_date_contract():
    assert inspect([date(2011, 1, 2), date(2011, 1, 3)], field='Day').passed


def test_legacy_date_axis_does_not_require_new_year_authority():
    current = schema()
    catalog = build(current, registry(current)).model_copy(update={'context': None})
    assert inspect([date(2011, 1, 1)], field='Period', catalog=catalog).passed
    with pytest.raises(ResultSemanticInspectionError):
        inspect([2011], catalog=catalog)


def test_missing_catalog_or_schema_cannot_accept_integer_axis():
    current = schema()
    result = QueryResult(semantic_model_key=current.key, columns=['FiscalYear', 'Amount'],
                         rows=[[2009, 1]], row_count=1, source_mode='real')
    for kwargs in ({}, {'schema': current}, {'catalog': build(current, registry(current))}):
        with pytest.raises(ResultSemanticInspectionError):
            ResultSemanticInspectionGate().inspect(trend_plan('FiscalYear'), result, **kwargs)
