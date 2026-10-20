"""Failure-first: exact runtime numeric lineage is required for Decimal text."""
from decimal import Decimal

import pytest

from backend.app.facts.inspection import ResultSemanticInspectionGate
from backend.app.facts.verified import VerifiedFactSetBuilder
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_normalization import (
    IQInlineEnvelope, normalize_query, normalize_schema,
)
from backend.app.schemas.data_contracts import CanonicalQueryPlan, DAXRequest, QueryShape
from backend.tests.unit.test_fabric_iq_adapter import MODEL, result, schema


def bound_schema(kind='Decimal'):
    raw = schema()
    raw['schema']['Tables'][0]['Measures'] = [{'Name': 'Amount', 'Type': kind}]
    return normalize_schema(raw, MODEL, 'synthetic', 3)


def normalize(value, *, model=None, label='Amount', wire_type='Decimal'):
    raw = result([[value]])
    raw['executionResult']['tables'][0]['columns'] = [{'name': label, 'type': wire_type}]
    request = DAXRequest(semantic_model_key='synthetic', dax='EVALUATE fixture', max_rows=1)
    return normalize_query(raw, MODEL, request,
        envelope=IQInlineEnvelope.for_request(request), schema=model)


@pytest.mark.parametrize('text', ['20972594.5680', '-1526667.8600', '523.3075', '42', '0', '-0.0000'])
def test_exact_numeric_schema_lineage_normalizes_directly_to_decimal(text):
    actual = normalize(text, model=bound_schema())
    value = actual.rows[0][0]
    assert type(value) is Decimal
    assert value.as_tuple() == Decimal(text).as_tuple()  # Includes wire scale; no float or rounding.
    assert actual.source_mode == 'real' and not actual.truncated
    plan = CanonicalQueryPlan(semantic_model_key='synthetic', query_shape=QueryShape.SCALAR,
        normalized_question='Synthetic amount', measures=['Amount'])
    ResultSemanticInspectionGate().inspect(plan, actual)
    facts = VerifiedFactSetBuilder().build(plan, actual)
    assert any(type(f.value) is Decimal and f.value == value for f in facts.facts)


@pytest.mark.parametrize('text', [
    '¥20,972,594.5680', '20,972,594.5680', '£10', '$10', '12,34',
    'NaN', 'Infinity', '-Infinity', 'amount', '10 GBP', ' 10', '10 ',
    '+10', '.5', '10.', '１0', '10\n', '1e3', '1E-4', '0'*65,
])
def test_invalid_lexical_values_never_produce_query_result(text):
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize(text, model=bound_schema())


@pytest.mark.parametrize('kind', ['String', 'DateTime', 'Boolean', None, 'Unknown'])
def test_numeric_looking_text_without_numeric_schema_fails(kind):
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize('10.0000', model=bound_schema(kind))


@pytest.mark.parametrize('label', ['Unknown', 'Facts Amount', '[Amount]', 'amount'])
def test_nonexact_measure_lineage_fails(label):
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize('10.0000', model=bound_schema(), label=label)


def test_missing_schema_or_wrong_model_fails():
    with pytest.raises(PowerBIAdapterError):
        normalize('10.0000')
    model = bound_schema().model_copy(update={'key': 'other'})
    with pytest.raises(PowerBIAdapterError):
        normalize('10.0000', model=model)


def test_unknown_wire_type_and_ambiguous_lineage_fail():
    with pytest.raises(PowerBIAdapterError):
        normalize('10', model=bound_schema(), wire_type='Unknown')
    model = bound_schema()
    model.tables.append(model.tables[0].model_copy(update={'name': 'Other'}))
    with pytest.raises(PowerBIAdapterError):
        normalize('10', model=model)


def test_real_text_field_stays_text_and_does_not_gain_numeric_authority():
    model = bound_schema()
    actual = normalize('123', model=model, label='Category', wire_type='String')
    assert type(actual.rows[0][0]) is str


def test_exact_numeric_column_lineage_supported():
    model = bound_schema()
    model.tables[0].columns[0] = model.tables[0].columns[0].model_copy(update={'data_type': 'Decimal'})
    actual = normalize('12.3400', model=model, label='Facts Category')
    assert actual.columns == ['Category'] and actual.rows == [[Decimal('12.3400')]]


@pytest.mark.parametrize('changes', [
    {'metadata_source': 'mock'}, {'session_generation': None},
])
def test_unproven_runtime_schema_does_not_authorize_numeric_text(changes):
    with pytest.raises(PowerBIAdapterError):
        normalize('10.0000', model=bound_schema().model_copy(update=changes))
