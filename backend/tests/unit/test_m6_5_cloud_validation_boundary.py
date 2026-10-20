"""Failure-first M6.5 audit fixtures, not UCI Real evidence or new capabilities."""
import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.app.schemas.data_contracts import ColumnMembersRequest
from backend.tests.unit.test_fabric_iq_adapter import harness, MODEL, WORKSPACE, result  # noqa: F401
from scripts.profile_online_retail_ii import external_path, price_units, identifier


@pytest.mark.asyncio
@pytest.mark.parametrize("cardinality", [13, 25, 43, 5000])
async def test_high_cardinality_member_snapshot_is_not_usable_for_cloud_grounding(harness, cardinality):
    auth, session, transport, _ = harness
    adapter = FabricIQAdapterFactory(auth.settings, auth,
        transport_factory=lambda *args: transport).create_product(session.session_id, session.principal)
    ref = await adapter.bind_catalog_model(WORKSPACE, MODEL)
    # Emulate a conforming upstream maxRows=13 sentinel response.
    transport.query = result([[f"member-{n:05d}"] for n in range(min(cardinality, 13))])
    transport.query["executionResult"]["tables"][0]["columns"] = [{"name": "__member", "type": "String"}]
    with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
        await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name="Facts", field_name="Category", limit=100))
    queries = [args for name,args in transport.calls if name == "ExecuteQuery"]
    assert len(queries) == 1 and queries[0]["maxRows"] == 13
    assert "TOPN(101" in queries[0]["daxQueries"][0]
    assert auth.require_session(session.session_id).principal == session.principal


@pytest.mark.parametrize("value, expected", [(2.1,21000), (0.001,10), (-1.25,-12500), (0,0)])
def test_offline_oracle_retains_price_sign_and_subcent_precision(value, expected):
    assert price_units(value) == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "0.00001"])
def test_offline_oracle_does_not_round_invalid_or_excess_precision_price(value):
    with pytest.raises(ValueError):
        price_units(value)


def test_identifiers_preserve_cancel_prefix_and_missing_customer():
    assert identifier("C123456") == "C123456"
    assert identifier(12345.0) == "12345"
    assert identifier("") is None
    with pytest.raises(ValueError):
        identifier(12345.1)


def test_profile_output_cannot_enter_repository_or_parent():
    for target in [".", "..", "D:/AAA_Workfile/M6.5/Profile"]:
        with pytest.raises(ValueError):
            external_path(target)
