"""Failure-first Cloud-only IQ bounds; all payloads are synthetic."""
import copy
import json

import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi import fabric_iq_normalization as normalization
from backend.app.schemas.data_contracts import DAXRequest
from backend.tests.unit.test_fabric_iq_adapter import MODEL, harness, result  # noqa: F401


def request(limit=1000):
    return DAXRequest(semantic_model_key="synthetic", dax='EVALUATE ROW("probe",1)', max_rows=limit)


def proven(raw, limit=1000):
    return normalization.normalize_query(raw, MODEL, request(limit),
        envelope=normalization.IQInlineEnvelope.for_request(request(limit)))


@pytest.mark.parametrize("value", ["0", "1", "-1", "9007199254740991", "9007199254740992",
    "9007199254740993", "-9223372036854775808", "9223372036854775807"])
def test_declared_integer_canonical_string_has_exact_python_value(value):
    normalized = normalization.normalize_query(result([[value]]), MODEL, request())
    assert type(normalized.rows[0][0]) is int
    assert normalized.rows[0][0] == int(value)
    assert normalized.truncated  # Integer correctness alone grants no completeness.


@pytest.mark.parametrize("count", [0, 1, 12])
def test_proven_inline_rows_below_sentinel_are_complete(count):
    normalized = proven(result([[i] for i in range(count)]))
    assert normalized.rows == [[i] for i in range(count)]
    assert normalized.row_count == count and normalized.truncated is False


def test_sentinel_is_incomplete_and_never_leaks_as_business_row():
    normalized = proven(result([[i] for i in range(13)]))
    assert normalized.truncated and normalized.row_count == 12
    assert normalized.rows == [[i] for i in range(12)]


@pytest.mark.parametrize("limit", [1, 2, 12, 1000])
def test_internal_business_and_wire_limits_preserve_public_request(limit):
    req = request(limit)
    envelope = normalization.IQInlineEnvelope.for_request(req)
    assert envelope.business_limit == min(limit, 12)
    assert envelope.wire_limit == min(limit, 12) + 1
    assert req.max_rows == limit


@pytest.mark.parametrize("change", ["too_many_rows", "too_many_columns", "long_name", "long_cell",
    "escaped_cell", "csv", "metadata_error", "metadata_incomplete", "metadata_contradiction"])
def test_profile_drift_and_incomplete_signals_fail_closed(change):
    raw = result([[1]])
    table = raw["executionResult"]["tables"][0]
    if change == "too_many_rows": table["rows"] = [[1]] * 14
    if change == "too_many_columns":
        table["columns"] = [{"name": f"c{i}", "type": "Int64"} for i in range(9)]
        table["rows"] = [[1] * 9]
    if change == "long_name": table["columns"][0]["name"] = "x" * 65
    if change in {"long_cell", "escaped_cell"}:
        table["columns"][0]["type"] = "String"
        table["rows"] = [["x" * 65 if change == "long_cell" else "\n" * 64]]
    if change == "csv":
        raw = {"content": [{"type": "text", "text": json.dumps(raw)},
            {"type": "resource", "resource": {"mimeType": "text/csv", "text": "[probe]\r\n1\r\n"}}]}
    if change == "metadata_error": table["error"] = {"status": 500}
    if change == "metadata_incomplete": table["hasMore"] = True
    if change == "metadata_contradiction": table.update(rowCount=2)
    code = "QUERY_REJECTED" if change == "metadata_error" else "CONTRACT_DRIFT"
    with pytest.raises(PowerBIAdapterError, match=f"^{code}$"):
        proven(raw)


@pytest.mark.asyncio
async def test_real_provider_sends_sentinel_limit_without_changing_request(harness):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = result([[1]])
    req = request().model_copy(update={"semantic_model_key": ref.server_model_key})
    normalized = await adapter.execute_dax(req)
    assert normalized.truncated is False and normalized.rows == [[1]]
    calls = [args for name, args in transport.calls if name == "ExecuteQuery"]
    assert len(calls) == 1 and calls[0]["maxRows"] == 13
    assert req.max_rows == 1000


def test_no_envelope_context_cannot_grant_completeness_from_success_flags():
    raw = copy.deepcopy(result([[1]], complete=True, truncated=False))
    assert normalization.normalize_query(raw, MODEL, request()).truncated
