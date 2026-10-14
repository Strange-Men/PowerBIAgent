"""Use native IQ Adapter and ToolGateway with synthetic protocol responses."""
import pytest

from backend.app.application.cloud_catalog_service import CloudCatalogService
from backend.app.auth.models import AuthFailure
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.tests.unit.test_cloud_catalog_service import REST
from backend.tests.unit.test_fabric_iq_adapter import harness, MODEL, WORKSPACE, principal  # noqa: F401


@pytest.mark.asyncio
async def test_catalog_native_adapter_schema_before_bind_and_session_key_stability(harness):
    auth,session,transport,adapter = harness
    service = CloudCatalogService(auth,session.session_id,session.principal,REST(),adapter)
    first = await service.discover()
    second = await service.discover()
    assert len(first.items) == 1 and second.items[0].key == first.items[0].key
    assert adapter.binding_count == 1
    assert [c[0] for c in transport.calls] == ["ResolveFabricItem","GetSemanticModelSchema"]*2
    auth.logout(session.session_id,None)
    with pytest.raises(AuthFailure): await service.discover()
    assert adapter.binding_count == 1  # Native Adapter purges on the next bound operation.
    with pytest.raises(AuthFailure): await adapter.get_semantic_model_schema(first.items[0].key)
    assert adapter.binding_count == 0


@pytest.mark.asyncio
async def test_native_permission_denial_discards_whole_catalog(harness):
    auth,session,transport,adapter = harness
    original_schema = transport.schema
    transport.schema = {"Error":{"HttpStatusCode":403}}
    service = CloudCatalogService(auth,session.session_id,session.principal,REST(),adapter)
    denied = await service.discover()
    assert denied.items == [] and denied.inaccessible_count == 1
    assert adapter.binding_count == 0
    assert auth.require_session(session.session_id).principal == session.principal
    transport.schema = original_schema
    assert len((await service.discover()).items) == 1


@pytest.mark.asyncio
async def test_native_same_resource_different_principal_never_reuses_key(harness):
    auth,session,transport,adapter = harness
    a = await CloudCatalogService(auth,session.session_id,session.principal,REST(),adapter).discover()
    session_b = auth.sessions.create(principal(4),object(),3600)
    b_adapter = FabricIQAdapterFactory(auth.settings,auth,transport_factory=lambda *args:transport).create(
        session_b.session_id,session_b.principal)
    b = await CloudCatalogService(auth,session_b.session_id,session_b.principal,REST(),b_adapter).discover()
    assert a.items[0].key != b.items[0].key


@pytest.mark.asyncio
async def test_service_rejects_another_valid_users_adapter_at_construction(harness):
    auth,session,transport,adapter = harness
    session_b = auth.sessions.create(principal(4),object(),3600)
    with pytest.raises(AuthFailure,match="^AUTH_FORBIDDEN$"):
        CloudCatalogService(auth,session_b.session_id,session_b.principal,REST(),adapter)
    assert transport.calls == []
