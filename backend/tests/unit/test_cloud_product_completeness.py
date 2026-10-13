"""Cloud product must reject unknown completeness before the Frozen factual chain."""
import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.app.schemas.data_contracts import DAXRequest
from backend.tests.unit.test_fabric_iq_adapter import harness, MODEL, WORKSPACE, result  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("signals",[{}, {"truncated":False}, {"complete":True}])
async def test_product_factory_rejects_unknown_completeness_before_facts(harness,signals):
    auth,session,transport,_=harness
    transport.query=result(**signals)
    adapter=FabricIQAdapterFactory(auth.settings,auth,transport_factory=lambda *args:transport).create_product(
        session.session_id,session.principal)
    ref=await adapter.bind_catalog_model(WORKSPACE,MODEL)
    request=DAXRequest(semantic_model_key=ref.server_model_key,dax='EVALUATE ROW("probe",1)',max_rows=10)
    with pytest.raises(PowerBIAdapterError,match="^CONTRACT_DRIFT$"):
        await adapter.execute_dax(request)
    # Alternate normalization entry cannot bypass the product guard either.
    with pytest.raises(PowerBIAdapterError,match="^CONTRACT_DRIFT$"):
        await adapter.normalize_result((transport.query,request))
    assert auth.require_session(session.session_id).principal == session.principal


@pytest.mark.asyncio
async def test_audit_adapter_retains_explicit_incomplete_result_without_granting_product_authority(harness):
    _,_,_,adapter=harness
    ref=await adapter.bind_catalog_model(WORKSPACE,MODEL)
    normalized=await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
        dax='EVALUATE ROW("probe",1)',max_rows=10))
    assert normalized.truncated and normalized.rows == [[1]]
