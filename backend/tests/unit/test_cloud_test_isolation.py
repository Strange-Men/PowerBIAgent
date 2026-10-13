"""P0 test resource boundary: synthetic identities, no real network or data."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import AsyncMock

import httpx2
import pytest

from backend.app.auth.models import AuthFailure
from backend.app.auth.service import AuthService
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.cloud_catalog_transport import FabricCatalogTransport
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.app.schemas.data_contracts import DAXRequest, ColumnMembersRequest
from backend.tests.unit.test_fabric_iq_adapter import (
    Identity, Transport, settings, principal, MODEL, WORKSPACE, URL,
)

FOREIGN = str(UUID(int=901))
REPORT = str(UUID(int=15))


def scoped_settings(**changes):
    return settings(powerbi_mode='fabric_iq', fabric_test_mode=True,
        fabric_test_allowlist={'workspace_id':WORKSPACE,
            'models':[{'model_id':MODEL,'synthetic_only':True}],
            'reports':[{'report_id':REPORT, 'model_id':MODEL,'synthetic_only':True}]}, **changes)


def native(config=None):
    auth = AuthService(config or scoped_settings(), Identity())
    session = auth.sessions.create(principal(), object(), 3600)
    transport = Transport()
    adapter = FabricIQAdapterFactory(auth.settings, auth, bootstrap_urls={'fixture':URL},
        transport_factory=lambda *args:transport).create(session.session_id, session.principal)
    return auth, session, transport, adapter


@pytest.mark.asyncio
async def test_missing_test_allowlist_denies_before_any_iq_operation():
    auth, session, wire, adapter = native(settings(powerbi_mode='fabric_iq', fabric_test_mode=True))
    try:
        with pytest.raises(PowerBIAdapterError, match='^RESOURCE_NOT_ACCESSIBLE$'):
            await adapter.resolve_bootstrap('fixture')
        assert wire.calls == []
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('workspace_id,model_id', [(FOREIGN,MODEL),(WORKSPACE,FOREIGN)])
async def test_foreign_catalog_candidate_never_reaches_iq(workspace_id, model_id):
    auth, session, wire, adapter = native()
    try:
        with pytest.raises(PowerBIAdapterError, match='^RESOURCE_NOT_ACCESSIBLE$'):
            await adapter.bind_catalog_model(workspace_id,model_id)
        assert wire.calls == []
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('workspace_id,model_id', [(FOREIGN,MODEL),(WORKSPACE,FOREIGN)])
async def test_persisted_restoration_cannot_bypass_exact_allowlist(workspace_id,model_id):
    auth,session,wire,adapter=native()
    try:
        with pytest.raises(PowerBIAdapterError,match='^RESOURCE_NOT_ACCESSIBLE$'):
            await adapter.restore_bound_model(workspace_id,model_id,'fabric_iq:synthetic-old')
        assert wire.calls==[]
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
async def test_native_restore_revalidates_resolve_schema_and_current_principal():
    auth,session,wire,adapter=native()
    try:
        restored=await adapter.restore_bound_model(WORKSPACE,MODEL,'fabric_iq:synthetic-old')
        assert restored.server_model_key=='fabric_iq:synthetic-old'
        assert [name for name,_ in wire.calls]==['ResolveFabricItem','GetSemanticModelSchema']
        assert adapter.bound_resource_identity(restored.server_model_key)==(WORKSPACE,MODEL)
        auth.logout(session.session_id,None)
        before=len(wire.calls)
        with pytest.raises(AuthFailure):
            await adapter.restore_bound_model(WORKSPACE,MODEL,restored.server_model_key)
        assert len(wire.calls)==before
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['schema','query','members','normalize'])
async def test_same_principal_forged_or_old_binding_is_denied(operation):
    auth, session, wire, adapter = native()
    try:
        ref = await adapter.resolve_bootstrap('fixture')
        adapter._bindings[ref.server_model_key] = replace(ref, workspace_id=FOREIGN)
        before = len(wire.calls)
        request = DAXRequest(semantic_model_key=ref.server_model_key, dax='EVALUATE ROW("probe",1)')
        with pytest.raises(PowerBIAdapterError, match='^RESOURCE_NOT_ACCESSIBLE$'):
            if operation == 'schema': await adapter.get_semantic_model_schema(ref.server_model_key)
            elif operation == 'query': await adapter.execute_dax(request)
            elif operation == 'normalize': await adapter.normalize_result((wire.query,request))
            else: await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
                table_name='Facts',field_name='Category',limit=2))
        assert len(wire.calls) == before
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
async def test_test_catalog_only_fetches_exact_approved_resource_paths():
    auth, session, wire, adapter = native()
    paths=[]
    from backend.app.auth.identity import CATALOG_SCOPES, DELEGATED_SCOPES
    from unittest.mock import Mock
    original=auth.get_delegated_token
    auth.get_delegated_token=Mock(wraps=original)
    def respond(request):
        paths.append(request.url.path)
        if request.url.path == f'/v1/workspaces/{WORKSPACE}':
            body={'id':WORKSPACE,'displayName':'Synthetic Workspace'}
        else:
            is_model = '/semanticModels/' in request.url.path
            body={'id':MODEL if is_model else REPORT,'workspaceId':WORKSPACE,
                'displayName':'Synthetic Model' if is_model else 'Synthetic Report',
                'type':'SemanticModel' if is_model else 'Report'}
        return httpx2.Response(200,json=body)
    from backend.app.application.cloud_catalog_service import CloudCatalogService
    try:
        async with FabricCatalogTransport(auth,session.session_id,session.principal,
                http_transport=httpx2.MockTransport(respond)) as rest:
            catalog=await CloudCatalogService(auth,session.session_id,session.principal,rest,adapter).discover()
        assert len(catalog.items)==1
        assert paths == [f'/v1/workspaces/{WORKSPACE}',
            f'/v1/workspaces/{WORKSPACE}/semanticModels/{MODEL}',
            f'/v1/workspaces/{WORKSPACE}/reports/{REPORT}']
        assert catalog.coverage_scope == 'approved_test_resources'
        assert catalog.individual_share_coverage == 'not_applicable_test_scope'
        assert [call.args[2] for call in auth.get_delegated_token.call_args_list] == [
            CATALOG_SCOPES, DELEGATED_SCOPES, DELEGATED_SCOPES]
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/workspaces',f'/workspaces/{FOREIGN}',
    f'/workspaces/{FOREIGN}/semanticModels/{MODEL}',f'/workspaces/{WORKSPACE}/semanticModels/{FOREIGN}',
    f'/workspaces/{WORKSPACE}/reports/{FOREIGN}',f'/workspaces/{WORKSPACE}/reports'])
async def test_direct_rest_path_denied_before_token_or_http(path):
    auth,session,wire,adapter=native()
    from unittest.mock import Mock
    auth.get_delegated_token=Mock(side_effect=AssertionError('must not acquire token'))
    try:
        async with FabricCatalogTransport(auth,session.session_id,session.principal,
                http_transport=httpx2.MockTransport(lambda _:pytest.fail('must not send'))) as rest:
            with pytest.raises(PowerBIAdapterError,match='^RESOURCE_NOT_ACCESSIBLE$'):
                await rest._get(path,{})
        auth.get_delegated_token.assert_not_called()
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('name,args', [
    ('ResolveFabricItem',{'fabricItemId':f'https://app.powerbi.com/groups/{FOREIGN}/datasets/{MODEL}/details'}),
    ('GetSemanticModelSchema',{'artifactId':FOREIGN}),
    ('ValueSearch',{'artifactId':FOREIGN}),
    ('ExecuteQuery',{'artifactId':FOREIGN}),
    ('GetReportMetadata',{'artifactId':FOREIGN}),
    ('DiscoverArtifacts',{'searchText':'synthetic'}),
])
async def test_direct_iq_connection_denies_unapproved_tools_and_ids(name,args):
    from backend.app.config.cloud_test_policy import CloudTestPolicy
    from backend.app.powerbi.fabric_iq_transport import FabricIQConnection
    upstream=SimpleNamespace(call_tool=AsyncMock(side_effect=AssertionError('must not call')))
    connection=FabricIQConnection(upstream,[],lambda:None,CloudTestPolicy(scoped_settings()))
    with pytest.raises(PowerBIAdapterError,match='^RESOURCE_NOT_ACCESSIBLE$'):
        await connection.call(name,args)
    upstream.call_tool.assert_not_awaited()


def test_approved_iq_scope_does_not_authorize_discovery_or_enterprise_disclosure():
    from backend.app.config.cloud_test_policy import CloudTestPolicy
    policy=CloudTestPolicy(scoped_settings())
    for name,args in [('ResolveFabricItem',{'fabricItemId':URL}),
        ('GetSemanticModelSchema',{'artifactId':MODEL}),('ValueSearch',{'artifactId':MODEL}),
        ('ExecuteQuery',{'artifactId':MODEL}),('GetReportMetadata',{'artifactId':REPORT})]:
        policy.iq_call(name,args)
    with pytest.raises(PowerBIAdapterError): policy.iq_call('DiscoverArtifacts',{})


@pytest.mark.asyncio
async def test_cross_scope_seed_rejected_before_rest_or_iq():
    from backend.app.application.cloud_catalog_service import CloudCatalogService
    from backend.app.config.cloud_catalog import SharedModelSeed
    from backend.tests.unit.test_cloud_catalog_service import REST
    auth,session,wire,adapter=native()
    rest=REST()
    rest.list_workspaces=AsyncMock(side_effect=AssertionError('must not enumerate'))
    seed=SharedModelSeed(workspace_id=FOREIGN,model_id=MODEL,workspace_display_name='Synthetic Foreign')
    try:
        service=CloudCatalogService(auth,session.session_id,session.principal,rest,adapter,shared_seeds=[seed])
        with pytest.raises(PowerBIAdapterError): await service.discover()
        rest.list_workspaces.assert_not_awaited()
        assert wire.calls==[]
    finally:
        await adapter.aclose(); auth.close()


def test_default_test_configuration_is_closed_and_not_in_public_settings():
    config=settings(powerbi_mode='fabric_iq',fabric_test_mode=True)
    assert config.fabric_test_allowlist is None
    assert 'fabric_test_allowlist' not in config.safe_repr()


@pytest.mark.asyncio
async def test_wrong_resource_response_never_reaches_catalog_or_frontend():
    auth,session,wire,adapter=native()
    try:
        async with FabricCatalogTransport(auth,session.session_id,session.principal,
            http_transport=httpx2.MockTransport(lambda _:httpx2.Response(200,json={
                'id':FOREIGN,'displayName':'SYNTHETIC_PRIVATE_NAME'}))) as rest:
            with pytest.raises(PowerBIAdapterError,match='^CONTRACT_DRIFT$'):
                await rest.list_workspaces()
        assert wire.calls==[]
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
async def test_allowlist_revoked_during_schema_await_drops_response_and_cache():
    auth,session,wire,adapter=native()
    try:
        ref=await adapter.resolve_bootstrap('fixture')
        original=wire.call
        async def revoke(name,args):
            result=await original(name,args)
            auth.settings.fabric_test_allowlist=None
            return result
        wire.call=revoke
        with pytest.raises(PowerBIAdapterError,match='^RESOURCE_NOT_ACCESSIBLE$'):
            await adapter.get_semantic_model_schema(ref.server_model_key)
        assert adapter._bindings == {} and adapter._schemas == {}
        before=len(wire.calls)
        with pytest.raises(PowerBIAdapterError):
            await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
                dax='EVALUATE ROW("probe",1)'))
        assert len(wire.calls)==before
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
async def test_test_scope_never_allows_foreign_principal_copy_of_approved_binding():
    auth,a,wire,adapter=native()
    b=auth.sessions.create(principal(4),object(),3600)
    other=FabricIQAdapterFactory(auth.settings,auth,transport_factory=lambda *args:wire).create(
        b.session_id,b.principal)
    try:
        ref=await adapter.resolve_bootstrap('fixture')
        other._bindings[ref.server_model_key]=ref
        other._schemas[ref.server_model_key]=adapter._schemas[ref.server_model_key]
        before=len(wire.calls)
        with pytest.raises(PowerBIAdapterError): await other.get_semantic_model_schema(ref.server_model_key)
        assert len(wire.calls)==before
    finally:
        await adapter.aclose(); await other.aclose(); auth.close()


def test_native_api_missing_scope_and_forged_ids_never_acquire_resource_token(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.tests.api.test_auth_security import FakeIdentity, login, ORIGIN
    from unittest.mock import Mock
    app=create_app(settings(powerbi_mode='fabric_iq',fabric_test_mode=True),identity_client=FakeIdentity())
    with TestClient(app,base_url=ORIGIN) as client:
        login(client)
        tokens=Mock(side_effect=AssertionError('no resource token'))
        monkeypatch.setattr(app.state.auth_service,'get_delegated_token',tokens)
        response=client.get('/api/v1/cloud/catalog')
        assert response.status_code==503
        assert 'RESOURCE_NOT_ACCESSIBLE' in response.text
        assert WORKSPACE not in response.text and MODEL not in response.text
        for path in [f'/api/v1/cloud/catalog?workspace_id={FOREIGN}',
            f'/api/v1/cloud/catalog?model_id={FOREIGN}']:
            assert client.get(path).status_code==422
        headers={'Origin':ORIGIN,'X-CSRF-Token':client.get('/auth/session').json()['csrf_token']}
        for key in [FOREIGN,'fabric_iq:synthetic-old']:
            assert client.post('/api/v1/cloud/selection',json={'key':key,'expected_generation':0},
                headers=headers).status_code==403
        for path in [f'/api/v1/cloud/models/{FOREIGN}/schema',
            f'/api/v1/cloud/reports/{FOREIGN}',f'/api/v1/conversations/{FOREIGN}']:
            assert client.get(path).status_code==403
        tokens.assert_not_called()
        assert app.state._persistence_engine is None


@pytest.mark.asyncio
async def test_enterprise_model_without_company_approval_denied():
    config=scoped_settings()
    config.fabric_test_allowlist=config.fabric_test_allowlist.model_copy(update={
        'models':(config.fabric_test_allowlist.models[0].model_copy(update={'synthetic_only':False}),)})
    auth,session,wire,adapter=native(config)
    try:
        with pytest.raises(PowerBIAdapterError,match='^RESOURCE_NOT_ACCESSIBLE$'):
            await adapter.resolve_bootstrap('fixture')
        assert wire.calls==[]
    finally:
        await adapter.aclose(); auth.close()


def test_unmarked_origin_is_not_synthetic_and_requires_company_approval():
    from backend.app.config.cloud_test_policy import CloudTestAllowlist, CloudTestPolicy
    config=scoped_settings()
    config.fabric_test_allowlist=CloudTestAllowlist(workspace_id=WORKSPACE,models=[{'model_id':MODEL}])
    with pytest.raises(PowerBIAdapterError): CloudTestPolicy(config).model(WORKSPACE,MODEL)


def test_access_log_does_not_persist_forged_resource_ids_or_query_strings():
    import logging
    from backend.app.auth.boundary import AuthLogRedaction
    record=logging.LogRecord('uvicorn.access',logging.INFO,'synthetic',1,'%s %s %s %s %s',
        ('synthetic-client','GET',f'/api/v1/cloud/models/{FOREIGN}?cookie=SYNTHETIC_PRIVATE','HTTP/1.1',403),None)
    AuthLogRedaction().filter(record)
    assert FOREIGN not in record.getMessage() and 'SYNTHETIC_PRIVATE' not in record.getMessage()


@pytest.mark.asyncio
async def test_test_history_report_and_external_llm_preparation_deny_before_storage():
    from backend.app.application.cloud_product_services import CloudProductServiceFactory
    auth,session,wire,adapter=native()
    repositories=SimpleNamespace(for_session=AsyncMock(side_effect=AssertionError('storage must not open')))
    services=CloudProductServiceFactory(auth, None, repositories, None, None)
    try:
        for operation in [services.list_history(session.session_id,session.principal,limit=10),
            services.read_history(session.session_id,session.principal,'synthetic-old',limit=10),
            services.read_report(session.session_id,session.principal,'synthetic-old'),
            services.prepare(session.session_id,session.principal)]:
            with pytest.raises(AuthFailure,match='^AUTH_FORBIDDEN$'): await operation
        repositories.for_session.assert_not_awaited()
        assert wire.calls==[]
    finally:
        await adapter.aclose(); auth.close()
