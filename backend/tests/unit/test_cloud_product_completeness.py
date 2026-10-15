"""Cloud product must reject unknown completeness before the Frozen factual chain."""
import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.app.schemas.data_contracts import DAXRequest
from backend.tests.unit.test_fabric_iq_adapter import harness, MODEL, WORKSPACE, result  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("signals",[{}, {"truncated":False}, {"complete":True}])
async def test_product_wire_profile_is_proven_but_context_free_normalization_is_not(harness,signals):
    auth,session,transport,_=harness
    transport.query=result(**signals)
    adapter=FabricIQAdapterFactory(auth.settings,auth,transport_factory=lambda *args:transport).create_product(
        session.session_id,session.principal)
    ref=await adapter.bind_catalog_model(WORKSPACE,MODEL)
    request=DAXRequest(semantic_model_key=ref.server_model_key,dax='EVALUATE ROW("probe",1)',max_rows=10)
    normalized=await adapter.execute_dax(request)
    assert normalized.rows == [[1]] and not normalized.truncated
    calls=[args for name,args in transport.calls if name=='ExecuteQuery']
    assert calls[-1]['maxRows']==11
    # Alternate normalization entry cannot bypass the product guard either.
    with pytest.raises(PowerBIAdapterError,match="^CONTRACT_DRIFT$"):
        await adapter.normalize_result((transport.query,request))
    assert auth.require_session(session.session_id).principal == session.principal


@pytest.mark.asyncio
async def test_audit_normalization_without_wire_context_remains_incomplete(harness):
    _,_,transport,adapter=harness
    ref=await adapter.bind_catalog_model(WORKSPACE,MODEL)
    request=DAXRequest(semantic_model_key=ref.server_model_key,dax='EVALUATE ROW("probe",1)',max_rows=10)
    normalized=await adapter.normalize_result((transport.query,request))
    assert normalized.truncated and normalized.rows == [[1]]


@pytest.mark.asyncio
@pytest.mark.parametrize('rows,signals', [([[1]]*13,{}), ([[1]],{'hasMore':True}),
    ([[1]],{'complete':False}), ([[1]],{'totalRows':2})])
async def test_product_rejects_sentinel_and_provider_incomplete_before_facts(harness,rows,signals):
    auth,session,transport,_=harness
    transport.query=result(rows=rows,**signals)
    adapter=FabricIQAdapterFactory(auth.settings,auth,transport_factory=lambda *args:transport).create_product(
        session.session_id,session.principal)
    ref=await adapter.bind_catalog_model(WORKSPACE,MODEL)
    with pytest.raises(PowerBIAdapterError,match='^CONTRACT_DRIFT$'):
        await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,dax='EVALUATE ROW("probe",1)'))
