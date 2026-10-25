"""Formatted IQ amounts never acquire numeric fact authority."""
from decimal import Decimal

import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_normalization import IQInlineEnvelope, normalize_query
from backend.app.schemas.data_contracts import (
    DAXRequest,
    ColumnSchema,
    SemanticModelSchema,
    TableSchema,
)
from backend.tests.unit.test_fabric_iq_adapter import MODEL, result


@pytest.mark.parametrize('value', [
    '¥20,972,594.568', '£20,972,594.568', '20972594.568',
    '20,972,594.568', '¥-1,526,667.86', 'NaN', 'Infinity', True,
    # Republished 0.0000 measures still arrived as strings in actual IQ V1.
    '20972594.5680', '-1526667.8600', '523.3075',
])
def test_decimal_descriptor_does_not_authorize_display_text(value):
    raw = result([[value]])
    raw['executionResult']['tables'][0]['columns'] = [
        {'name': 'Amount', 'type': 'Decimal'}]
    request = DAXRequest(semantic_model_key='synthetic', dax='EVALUATE fixture', max_rows=1)
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize_query(raw, MODEL, request, envelope=IQInlineEnvelope.for_request(request))


def test_numeric_decimal_payload_retains_existing_authority():
    raw = result([[20972594.568]])
    raw['executionResult']['tables'][0]['columns'] = [
        {'name': 'Amount', 'type': 'Decimal'}]
    request = DAXRequest(semantic_model_key='synthetic', dax='EVALUATE fixture', max_rows=1)
    normalized = normalize_query(raw, MODEL, request, envelope=IQInlineEnvelope.for_request(request))
    assert normalized.rows == [[20972594.568]]
    assert normalized.source_mode == 'real' and not normalized.truncated


def _numeric_schema(format_string):
    return SemanticModelSchema(
        name="Formatted numeric",
        key="synthetic",
        session_generation=1,
        metadata_source="fabric_iq",
        tables=[TableSchema(
            name="Sales",
            columns=[ColumnSchema(
                name="Amount",
                data_type="Decimal",
                format_string=format_string,
            )],
        )],
    )


def _normalize_formatted(value, format_string):
    raw = result([[value]])
    raw['executionResult']['tables'][0]['columns'] = [
        {'name': 'Amount', 'type': 'Decimal'}]
    request = DAXRequest(
        semantic_model_key='synthetic', dax='EVALUATE fixture', max_rows=1
    )
    return normalize_query(
        raw, MODEL, request, schema=_numeric_schema(format_string)
    )


@pytest.mark.parametrize('value,expected', [
    ('$12,345.67', Decimal('12345.67')),
    ('$1,234', Decimal('1234')),
    ('-$1,234.56', Decimal('-1234.56')),
    ('$-1,234.56', Decimal('-1234.56')),
    ('1,234.56 $', Decimal('1234.56')),
    ('20972594.5680', Decimal('20972594.5680')),
    ('523.3075', Decimal('523.3075')),
    ('1.234', Decimal('1.234')),
])
def test_proven_numeric_schema_accepts_strict_formatted_amounts(
    value, expected
):
    normalized = _normalize_formatted(value, '$#,##0.00')
    assert normalized.rows == [[expected]]
    assert type(normalized.rows[0][0]) is Decimal


def test_eu_format_is_parsed_only_from_its_own_evidence():
    normalized = _normalize_formatted('1.234,56', '#.##0,00')
    assert normalized.rows == [[Decimal('1234.56')]]
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        _normalize_formatted('1.234,56', '$#,##0.00')


@pytest.mark.parametrize('value', [
    '1,234',            # grouping needs format/symbol evidence
    '1.2345,67', '--1,234.56',
    '$1,234.56.7', '1,234.56%', '$1e3', 'NaN', 'Infinity',
    'USD 1,234.56', '$1 234.56', '$1,23,456.78', '$  ',
])
def test_ambiguous_or_malformed_formatted_amounts_fail_closed(value):
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        _normalize_formatted(value, None)


@pytest.mark.parametrize('value', ['1,23', '12,34', '1,2345', '1234,567'])
def test_malformed_grouping_fails_even_with_us_format(value):
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        _normalize_formatted(value, '$#,##0.00')
