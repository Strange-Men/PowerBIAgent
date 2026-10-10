"""M6.3 wire cell correctness; synthetic payloads, no Auth or Frozen Core changes."""
import json
from uuid import UUID

import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_normalization import normalize_query
from backend.app.schemas.data_contracts import DAXRequest
from backend.tests.unit.test_fabric_iq_adapter import harness  # noqa: F401

MODEL = str(UUID(int=10))
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1


def normalize(value, kind="Int64", *, csv_value=None):
    body = {"semanticModel": {"ArtifactId": MODEL}, "executionResult": {"tables": [
        {"columns": [{"name": "[probe]", "type": kind}], "rows": [[value]]}]}}
    if csv_value is not None:
        body = {"content": [{"type": "text", "text": json.dumps(body)},
            {"type": "resource", "resource": {"uri": "data:synthetic", "mimeType": "text/csv",
                "text": "[probe]\r\n" + csv_value + "\r\n"}}]}
    return normalize_query(body, MODEL, DAXRequest(semantic_model_key="synthetic", dax='EVALUATE ROW("probe",1)'))


@pytest.mark.parametrize("kind", ["Int64", "int64", "integer", "long"])
@pytest.mark.parametrize("value", [100, 0, -1, INT64_MIN, INT64_MAX, None])
def test_native_int64_is_preserved_exactly(kind, value):
    result = normalize(value, kind)
    assert result.rows == [[value]]
    assert type(result.rows[0][0]) is type(value)
    assert result.truncated is True  # A type fix cannot grant completeness.


@pytest.mark.parametrize("value", ["100", "0", str(INT64_MIN), str(INT64_MAX), "abc", True, False, 100.0, INT64_MIN - 1, INT64_MAX + 1,
    "1.0", "1e2", "+100", " 100", "100 ", "0100", "-0", "", "١٠٠", "１００",
    "9223372036854775808", "-9223372036854775809", {}, []])
def test_int64_wrong_types_and_ambiguous_strings_fail_closed(value):
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        normalize(value)


@pytest.mark.parametrize("value", [-(2**31), 2**31-1, 100, None])
def test_int32_has_its_declared_range(value):
    assert normalize(value, "Int32").rows == [[value]]


@pytest.mark.parametrize("value", [-(2**31)-1, 2**31, True, "100"])
def test_int32_wrong_type_and_overflow_rejected(value):
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        normalize(value, "Int32")


@pytest.mark.parametrize("kind", ["Double", "Decimal", "Float", "Currency"])
@pytest.mark.parametrize("value", [100, 100.25, None])
def test_native_numeric_values_remain_numeric(kind, value):
    assert type(normalize(value, kind).rows[0][0]) is type(value)


@pytest.mark.parametrize("kind", ["Boolean", "bool"])
@pytest.mark.parametrize("value", [True, False, None])
def test_boolean_native_values_preserved(kind, value):
    assert type(normalize(value, kind).rows[0][0]) is type(value)


@pytest.mark.parametrize("value", [100, 1, 0, "true", "false", "100", {}, []])
def test_boolean_rejects_non_boolean_json(value):
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        normalize(value, "Boolean")


@pytest.mark.parametrize("kind", ["String", "DateTime", "date", "time"])
@pytest.mark.parametrize("value", ["100", None])
def test_textual_columns_preserve_values_without_numeric_inference(kind, value):
    result = normalize(value, kind)
    assert result.rows == [[value]] and type(result.rows[0][0]) is type(value)


@pytest.mark.parametrize("kind,value", [("String", 100), ("String", True), ("DateTime", 100),
    ("Double", "100"), ("Double", True), ("Double", float("inf")), ("Double", float("nan")),
    ("Unsupported", None), (" Int64", 100)])
def test_declared_type_mismatch_and_unknown_type_fail_closed(kind, value):
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        normalize(value, kind)


@pytest.mark.parametrize("value,csv_value", [(100,"100"), (INT64_MIN,str(INT64_MIN)),
    (INT64_MAX,str(INT64_MAX)), (None,'""')])
def test_int64_csv_mirror_preserves_native_json(value, csv_value):
    result = normalize(value, csv_value=csv_value)
    assert result.rows == [[value]] and type(result.rows[0][0]) is type(value)


@pytest.mark.parametrize("value,csv_value", [(100,"101"), (100,"0100"), (100,"+100"),
    (100," 100"), (100,"100.0"), (100,"1e2"), (True,"1"),
    (INT64_MAX+1,str(INT64_MAX+1)), (None,"100"), (100,"١٠٠"), (0,"-0"),
    (100,"1"*10000), ("100","100"), (str(INT64_MAX),str(INT64_MAX))])
def test_int64_csv_mismatch_or_invalid_encoding_rejected(value, csv_value):
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        normalize(value, csv_value=csv_value)


@pytest.mark.parametrize("value,csv_value", [(True,"true"),(False,"false"),(None,'""')])
def test_boolean_csv_mirror_is_typed(value, csv_value):
    result = normalize(value,"Boolean",csv_value=csv_value)
    assert type(result.rows[0][0]) is type(value)


@pytest.mark.parametrize("value,csv_value", [(True,"1"),(False,"0"),(True,"false")])
def test_boolean_csv_does_not_accept_numeric_or_contradictory_values(value, csv_value):
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        normalize(value,"Boolean",csv_value=csv_value)


@pytest.mark.asyncio
async def test_string_rejection_keeps_native_session_and_model_binding(harness):
    from backend.tests.unit.test_fabric_iq_adapter import result
    auth, session, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = result([["100"]])
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
            dax='EVALUATE ROW("probe",1)'))
    assert auth.require_session(session.session_id).principal == session.principal
    assert adapter.binding_count == 1
    assert len([call for call in transport.calls if call[0] == "ExecuteQuery"]) == 1
    transport.query = result([[100]])
    assert (await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
        dax='EVALUATE ROW("probe",1)'))).rows == [[100]]
