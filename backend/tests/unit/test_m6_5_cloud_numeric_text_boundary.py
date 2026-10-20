"""Formatted IQ amounts never acquire numeric fact authority."""
import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_normalization import IQInlineEnvelope, normalize_query
from backend.app.schemas.data_contracts import DAXRequest
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
