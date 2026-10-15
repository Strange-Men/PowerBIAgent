"""Round 1 boundaries: synthetic IDs/HTTP only; no external business calls."""
import copy
from types import SimpleNamespace
from uuid import UUID

import httpx2
import pytest
from fastapi.testclient import TestClient

from backend.app.application.cloud_catalog_service import CloudCatalogService
from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_test_policy import CloudTestAllowlist, CloudTestPolicy
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.cloud_catalog_transport import FabricCatalogTransport
from backend.app.powerbi.fabric_iq_contract import fail
from backend.tests.unit.test_cloud_test_isolation import native
from backend.tests.unit.test_cloud_workspace_service import workspace
from backend.tests.unit.test_fabric_iq_adapter import harness, MODEL, WORKSPACE  # noqa: F401

WS_B, MODEL_B, REPORT_A, REPORT_B, FOREIGN = (str(UUID(int=n)) for n in (801,802,803,804,899))


def approval():
    return CloudTestAllowlist(workspaces=[
        {'workspace_id':WORKSPACE,'models':[{'model_id':MODEL,'synthetic_only':True}],
         'reports':[{'report_id':REPORT_A,'model_id':MODEL,'synthetic_only':True}]},
        {'workspace_id':WS_B,'models':[{'model_id':MODEL_B,'synthetic_only':True}],
         'reports':[{'report_id':REPORT_B,'model_id':MODEL_B,'synthetic_only':True}]}])


def test_workspace_scope_requires_exact_iq_connection_context():
    policy=CloudTestPolicy(SimpleNamespace(fabric_test_mode=True,fabric_test_allowlist=approval()))
    for ws,model,report in ((WORKSPACE,MODEL,REPORT_A),(WS_B,MODEL_B,REPORT_B)):
        policy.model(ws,model); policy.report(ws,report)
        policy.iq_call('GetSemanticModelSchema',{'artifactId':model},resource=(ws,model))
        policy.iq_call('GetReportMetadata',{'artifactId':report},resource=(ws,report))
        with pytest.raises(PowerBIAdapterError):
            policy.iq_call('GetSemanticModelSchema',{'artifactId':MODEL_B if model==MODEL else MODEL},resource=(ws,model))
    for ws,model,report in ((FOREIGN,MODEL,REPORT_A),(FOREIGN,MODEL_B,REPORT_B)):
        with pytest.raises(PowerBIAdapterError): policy.model(ws,model)
        with pytest.raises(PowerBIAdapterError): policy.report(ws,report)


@pytest.mark.asyncio
@pytest.mark.parametrize('denied', [None,WORKSPACE,MODEL,REPORT_A])
async def test_targeted_catalog_isolates_denial_without_logout_or_other_workspace_loss(denied):
    auth,session,wire,adapter=native()
    auth.settings.fabric_test_allowlist=approval()
    requests=[]
    def respond(request):
        path=request.url.path.removeprefix('/v1')
        requests.append(path)
        key=path.split('/')[-1]
        if key==denied: return httpx2.Response(403)
        parts=path.split('/')
        body={'id':key,'displayName':'Synthetic '+key[-3:]}
        if len(parts)==4:
            is_model=parts[3]=='semanticModels'
            if denied==REPORT_A and parts[2]==WORKSPACE and not is_model: return httpx2.Response(403)
            item=(MODEL if parts[2]==WORKSPACE else MODEL_B) if is_model else (REPORT_A if parts[2]==WORKSPACE else REPORT_B)
            body={'value':[{'id':item,'displayName':'Synthetic '+item[-3:],
                'workspaceId':parts[2],'type':'SemanticModel' if is_model else 'Report'}]}
        return httpx2.Response(200,json=body)
    async def call(name,args):
        wire.calls.append((name,args))
        model=args['artifactId'] if 'artifactId' in args else args['fabricItemId'].split('/')[-2]
        if model==denied: raise fail('RESOURCE_NOT_ACCESSIBLE')
        if name=='ResolveFabricItem':
            return {'fabricItemId':model,'workspaceId':WORKSPACE if model==MODEL else WS_B,'itemType':'SemanticModel'}
        result=copy.deepcopy(wire.schema)
        result['semanticModel']['ArtifactId']=model
        return result
    wire.call=call
    try:
        async with FabricCatalogTransport(auth,session.session_id,session.principal,
                http_transport=httpx2.MockTransport(respond)) as rest:
            with pytest.raises(PowerBIAdapterError): await rest.list_models(FOREIGN)
            assert requests==[]
            catalog=await CloudCatalogService(auth,session.session_id,session.principal,rest,adapter).discover()
        assert len(catalog.items)==(1 if denied in (WORKSPACE,MODEL) else 2)
        assert catalog.inaccessible_count==(1 if denied in (WORKSPACE,MODEL) else 0)
        assert catalog.workspace_scope_complete==(denied in (None,MODEL))
        assert auth.require_session(session.session_id).principal==session.principal
        assert all(path.startswith(('/workspaces/'+WORKSPACE,'/workspaces/'+WS_B)) for path in requests)
        assert '/workspaces' not in requests
        assert not any(name=='ExecuteQuery' for name,_ in wire.calls)
        assert f'/workspaces/{WS_B}/semanticModels' in requests
        if denied==WORKSPACE: assert not any(path.startswith('/workspaces/'+WORKSPACE+'/') for path in requests)
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('code',['RESOURCE_NOT_ACCESSIBLE','AUTH_FORBIDDEN','SCHEMA_UNAVAILABLE','AUTH_EXPIRED','AUTH_REQUIRED'])
async def test_adapter_denial_invalidates_only_affected_resource_unless_auth_expired(harness,code):
    auth,session,wire,adapter=harness
    original=wire.call
    async def call(name,args):
        if name=='ResolveFabricItem' and WS_B in args['fabricItemId']:
            return {'fabricItemId':MODEL_B,'workspaceId':WS_B,'itemType':'SemanticModel'}
        if args.get('artifactId')==MODEL_B:
            result=copy.deepcopy(wire.schema); result['semanticModel']['ArtifactId']=MODEL_B
            return result
        return await original(name,args)
    wire.call=call
    a=await adapter.bind_catalog_model(WORKSPACE,MODEL)
    b=await adapter.bind_catalog_model(WS_B,MODEL_B)
    async def deny(name,args):
        if args.get('artifactId')==MODEL:
            if code.startswith('AUTH_'): raise AuthFailure(code,401 if code!='AUTH_FORBIDDEN' else 403)
            raise fail(code)
        return await call(name,args)
    wire.call=deny
    with pytest.raises((PowerBIAdapterError,AuthFailure)):
        await adapter.get_semantic_model_schema(a.server_model_key)
    if code in {'AUTH_EXPIRED','AUTH_REQUIRED'}:
        assert adapter.binding_count==0
        with pytest.raises(AuthFailure): auth.require_session(session.session_id)
    else:
        assert a.server_model_key not in adapter._bindings
        assert b.server_model_key in adapter._bindings
        assert auth.require_session(session.session_id).principal==session.principal
        assert (await adapter.get_semantic_model_schema(b.server_model_key)).key==b.server_model_key


@pytest.mark.asyncio
async def test_access_execution_disclosure_and_persistence_are_independent(harness):
    auth,session,wire,_=harness
    service=workspace(harness)
    try:
        catalog=await service.catalog(session.session_id,session.principal)
        selected=await service.select(session.session_id,session.principal,catalog.items[0].key)
        before=len(wire.calls)
        service.require_resource_access(session.session_id,session.principal,selected.selected_model_key)
        for gate,reason in ((service.require_execution,'cloud_execution_blocked'),
                (service.require_disclosure,'cloud_disclosure_blocked'),(service.require_persistence,'cloud_persistence_blocked')):
            with pytest.raises(AuthFailure) as failure: gate(session.session_id,session.principal)
            assert failure.value.denial_reason==reason
            assert service.status(session.session_id,session.principal)==selected
        assert len(wire.calls)==before
        assert auth.require_session(session.session_id).principal==session.principal
    finally: await service.aclose()


def test_resource_403_preserves_auth_session_and_routes_do_not_use_execution_as_middleware_gate():
    from backend.tests.api.test_auth_security import config,FakeIdentity,login,ORIGIN
    from backend.app.main import create_app
    app=create_app(config(powerbi_mode='fabric_iq'),identity_client=FakeIdentity())
    with TestClient(app,base_url=ORIGIN) as client:
        login(client)
        headers={'Origin':ORIGIN,'X-CSRF-Token':client.get('/auth/session').json()['csrf_token']}
        called=[]
        async def denied(sid,principal,key,**kwargs):
            called.append(key); raise fail('RESOURCE_NOT_ACCESSIBLE')
        app.state.cloud_workspace_service.select=denied
        response=client.post('/api/v1/cloud/selection',json={'key':'synthetic-a','expected_generation':0},headers=headers)
        assert response.status_code==403 and response.json()['detail']['failure']['code']=='RESOURCE_NOT_ACCESSIBLE'
        assert client.get('/auth/session').json()['authenticated']
        async def allowed(sid,principal,key,**kwargs):
            called.append(key); return app.state.cloud_workspace_service.status(sid,principal)
        app.state.cloud_workspace_service.select=allowed
        assert client.post('/api/v1/cloud/selection',json={'key':'synthetic-b','expected_generation':0},headers=headers).status_code==200
        assert called==['synthetic-a','synthetic-b']
        async def service_denial(*args,**kwargs):
            called.append('product-service'); raise AuthFailure('AUTH_FORBIDDEN',403,denial_reason='cloud_persistence_blocked')
        app.state.cloud_product_services.list_history=service_denial
        denied=client.get('/api/v1/cloud/history')
        assert denied.status_code==403 and denied.json()['denial_reason']=='cloud_persistence_blocked'
        assert called[-1]=='product-service'
        assert client.get('/auth/session').json()['authenticated']
