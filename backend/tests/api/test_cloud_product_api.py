"""Formal ENTRA APIs with explicitly injected existing Mock BI and LLM."""
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.application.cloud_workspace_service import CloudWorkspaceService
from backend.app.application.cloud_product_services import CloudProductServiceFactory
from backend.app.persistence.database import create_engine, create_session_factory
from backend.app.persistence.models import Base
from backend.app.persistence.ownership import PrincipalScopedRepositoryFactory
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.powerbi.fabric_iq import CloudSemanticModelRef
from backend.app.auth.models import AuthFailure
from backend.app.llm.factory import build_llm_registry
from backend.tests.api.test_auth_security import config, FakeIdentity, login, ORIGIN
from backend.tests.unit.test_cloud_catalog_service import REST


class SyntheticAdapter(MockPowerBIAdapter):
    def __init__(self,auth,sid,principal):
        super().__init__(); self.auth,self.sid,self.principal=auth,sid,principal
        self.allowed=True
    def assert_session_binding(self,auth,sid,principal):
        if self.auth is not auth or self.sid!=sid or self.auth.require_session(sid).principal!=principal:
            raise AuthFailure('AUTH_FORBIDDEN',403)
    def bound_resource_identity(self,key):
        if key!='mock_sales_model' or not self.allowed: raise AuthFailure('AUTH_FORBIDDEN',403)
        return str(UUID(int=100)),str(UUID(int=200))
    async def bind_catalog_model(self,ws,model):
        self.assert_session_binding(self.auth,self.sid,self.principal)
        if not self.allowed: raise AuthFailure('AUTH_FORBIDDEN',403)
        return CloudSemanticModelRef('mock_sales_model',self.principal.tenant_id,self.principal.principal_id,
            str(UUID(int=100)),str(UUID(int=200)),'合成销售模型',self.principal.session_epoch,self.principal.authorization_epoch)
    async def restore_bound_model(self,ws,model,key):
        if (ws,model,key)!=(str(UUID(int=100)),str(UUID(int=200)),'mock_sales_model'):
            raise AuthFailure('AUTH_FORBIDDEN',403)
        return await self.bind_catalog_model(ws,model)
    async def get_semantic_model_schema(self,key):
        self.assert_session_binding(self.auth,self.sid,self.principal)
        if not self.allowed: raise AuthFailure('AUTH_FORBIDDEN',403)
        from backend.app.schemas.data_contracts import MeasureSchema
        schema=await super().get_semantic_model_schema(key)
        # Explicit synthetic canonical identity for template qualification;
        # keep all existing Mock scenario objects and numeric fixtures.
        table=schema.tables[0].model_copy(update={'measures':schema.tables[0].measures+[
            MeasureSchema(name='Total Sales',data_type='Double')]})
        return schema.model_copy(update={'tables':[table]})
    async def aclose(self): pass


class SyntheticREST(REST):
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass


@pytest.fixture
def cloud_product(tmp_path):
    settings=config(powerbi_mode='fabric_iq',fabric_test_mode=False)
    identity=FakeIdentity()
    async def runtime(auth):
        engine=create_engine(settings.model_copy(update={'persistence_database_path':str(tmp_path/'synthetic.db')}))
        async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
        factory=SimpleNamespace(create_product=lambda sid,p:SyntheticAdapter(auth,sid,p))
        workspace=CloudWorkspaceService(auth,factory,rest_factory=lambda *args:SyntheticREST(),synthetic_product=True)
        repos=PrincipalScopedRepositoryFactory(create_session_factory(engine),tmp_path/'reports')
        registry=build_llm_registry(settings)
        products=CloudProductServiceFactory(auth,workspace,repos,registry,registry)
        return SimpleNamespace(workspace=workspace,products=products,registry=registry,close=engine.dispose)
    app=create_app(settings,identity_client=identity,cloud_runtime_factory=runtime)
    with TestClient(app,base_url=ORIGIN) as client:
        login(client)
        headers={'Origin':ORIGIN,'X-CSRF-Token':client.get('/auth/session').json()['csrf_token']}
        catalog=client.get('/api/v1/cloud/catalog').json()
        selection=client.post('/api/v1/cloud/selection',json={'key':catalog['items'][0]['key'],'expected_generation':0},headers=headers).json()
        yield client,app,headers,selection,identity


def test_formal_chat_history_new_chat_and_exact_restore(cloud_product):
    c,app,h,selection,_=cloud_product
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询总销售额','request_id':'synthetic-chat',
        'expected_generation':selection['generation']})
    assert response.status_code==200,response.text
    body=response.json();assert body['source_mode']=='mock' and body['is_mock']
    assert body['memory_commit'] and body['answer']
    history=c.get('/api/v1/cloud/history').json()
    assert history['items'][0]['conversation_id']==selection['conversation_id']
    page=c.get('/api/v1/cloud/history/'+selection['conversation_id']).json()
    assert page['items'][0]['answer']==body['answer']
    new=c.post('/api/v1/cloud/new-chat',headers=h,json={'expected_generation':selection['generation']}).json()
    assert new['conversation_id']!=selection['conversation_id']
    restored=c.post('/api/v1/cloud/restore',headers=h,json={'conversation_id':selection['conversation_id'],
        'expected_generation':new['generation']})
    assert restored.status_code==200,restored.text
    assert restored.json()['conversation_id']==selection['conversation_id']
    assert c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询总销售额','request_id':'stale',
        'expected_generation':selection['generation']}).status_code==409


def test_revoke_blocks_history_and_discards_selection(cloud_product):
    c,app,h,s,_=cloud_product
    assert c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询总销售额','request_id':'synthetic-revoke',
        'expected_generation':s['generation']}).status_code==200
    context=next(iter(app.state.cloud_workspace_service._contexts.values()))
    context.adapter.allowed=False
    assert c.get('/api/v1/cloud/history/'+s['conversation_id']).status_code==403
    assert app.state.cloud_workspace_service.status(context.adapter.sid,context.principal).selected_model_key is None


def test_forged_identity_model_and_extra_fields_rejected(cloud_product):
    c,_,h,s,_=cloud_product
    for extra in [{'model_key':'forged'},{'principal_id':'forged'},{'conversation_id':'forged'}]:
        assert c.post('/api/v1/cloud/chat',headers=h,json={'message':'synthetic','request_id':'synthetic',
            'expected_generation':s['generation'],**extra}).status_code==422
    assert c.post('/api/v1/cloud/restore',headers=h,json={'conversation_id':'foreign',
        'expected_generation':s['generation']}).status_code==403


def test_report_template_generation_view_download_and_owner_relogin(cloud_product):
    c,app,h,s,identity=cloud_product
    templates=c.get('/api/v1/cloud/report-templates').json()
    assert any(x['template_key']=='sales_report' and x['selectable'] for x in templates['items'])
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'生成销售报告','request_id':'synthetic-report',
        'report_template_key':'sales_report','expected_generation':s['generation']})
    assert response.status_code==200,response.text
    report=response.json()['report'];assert report and response.json()['is_mock'], response.text
    rid=report['report_id']
    assert report['view_reference']=='/api/v1/cloud/reports/'+rid
    assert report['download_reference']=='/api/v1/cloud/reports/'+rid+'/download'
    view=c.get('/api/v1/cloud/reports/'+rid)
    download=c.get('/api/v1/cloud/reports/'+rid+'/download')
    assert view.status_code==download.status_code==200
    assert view.content==download.content
    assert 'sandbox' in view.headers['content-security-policy']
    assert c.get('/api/v1/cloud/reports').json()['items'][0]['report_id']==rid
    assert c.post('/auth/logout',headers=h).status_code==200
    identity.claim_changes={'oid':str(UUID(int=999))}
    login(c)
    assert c.get('/api/v1/cloud/history').json()['items']==[]
    assert c.get('/api/v1/cloud/reports/'+rid).status_code==404
    hb={'Origin':ORIGIN,'X-CSRF-Token':c.get('/auth/session').json()['csrf_token']}
    assert c.post('/auth/logout',headers=hb).status_code==200
    identity.claim_changes={};login(c)
    ha={'Origin':ORIGIN,'X-CSRF-Token':c.get('/auth/session').json()['csrf_token']}
    current=c.get('/api/v1/cloud/status').json()
    assert current['selected_model_key'] is None
    restored=c.post('/api/v1/cloud/restore',headers=ha,json={'conversation_id':s['conversation_id'],
        'expected_generation':current['generation']})
    assert restored.status_code==200,restored.text
    assert c.get('/api/v1/cloud/reports/'+rid).status_code==200


@pytest.mark.parametrize('route',['/api/v1/cloud/history','/api/v1/cloud/reports'])
def test_get_payload_duplicate_query_and_safe_storage_failure(cloud_product,monkeypatch,route):
    c,app,*_=cloud_product
    assert c.request('GET',route,content=b'{}').status_code==422
    assert c.get(route+'?limit=1&limit=2').status_code==422
    async def failure(*args,**kwargs): raise RuntimeError('SYNTHETIC_PRIVATE_DATABASE_DETAIL')
    method='list_history' if route.endswith('history') else 'list_reports'
    monkeypatch.setattr(app.state.cloud_product_services,method,failure)
    response=c.get(route)
    assert response.status_code==503
    assert 'SYNTHETIC_PRIVATE_DATABASE_DETAIL' not in response.text


def test_schema_drift_and_revoked_restore_refuse_all_metadata(cloud_product,monkeypatch):
    from backend.app.schemas.data_contracts import MeasureSchema
    c,app,h,s,_=cloud_product
    assert c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询总销售额','request_id':'drift',
        'expected_generation':s['generation']}).status_code==200
    adapter=next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    original=adapter.get_semantic_model_schema
    async def drift(key):
        schema=await original(key)
        table=schema.tables[0].model_copy(update={'measures':schema.tables[0].measures+[
            MeasureSchema(name='Synthetic drift',data_type='Double')]})
        return schema.model_copy(update={'tables':[table]})
    monkeypatch.setattr(adapter,'get_semantic_model_schema',drift)
    response=c.get('/api/v1/cloud/history')
    assert response.status_code==403 and 'drift' not in response.text
    now=c.get('/api/v1/cloud/status').json()
    assert now['selected_model_key'] is None
    adapter.allowed=False
    assert c.post('/api/v1/cloud/restore',headers=h,json={'conversation_id':s['conversation_id'],
        'expected_generation':now['generation']}).status_code==403


def test_history_response_after_new_chat_is_discarded(cloud_product,monkeypatch):
    from backend.app.application.conversation_history_service import ConversationHistoryService
    c,app,h,s,_=cloud_product
    assert c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询总销售额','request_id':'late-history',
        'expected_generation':s['generation']}).status_code==200
    original=ConversationHistoryService.get_history
    async def late(service,*args,**kwargs):
        page=await original(service,*args,**kwargs)
        context=next(iter(app.state.cloud_workspace_service._contexts.values()))
        await app.state.cloud_workspace_service.new_chat(context.adapter.sid,context.principal,s['generation'])
        return page
    monkeypatch.setattr(ConversationHistoryService,'get_history',late)
    response=c.get('/api/v1/cloud/history/'+s['conversation_id'])
    assert response.status_code==403 and 'late-history' not in response.text


def test_unqualified_template_and_late_report_bytes_are_refused(cloud_product,monkeypatch):
    from backend.app.persistence.scoped_reports import PrincipalReportRepository
    c,app,h,s,_=cloud_product
    assert c.post('/api/v1/cloud/chat',headers=h,json={'message':'生成报告','request_id':'unknown-template',
        'report_template_key':'synthetic-unknown','expected_generation':s['generation']}).status_code==403
    assert c.get('/api/v1/cloud/history').json()['items']==[]
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'生成销售报告','request_id':'late-report',
        'report_template_key':'sales_report','expected_generation':s['generation']})
    rid=response.json()['report']['report_id']
    original=PrincipalReportRepository.read_html
    async def late(repository,*args,**kwargs):
        result=await original(repository,*args,**kwargs)
        context=next(iter(app.state.cloud_workspace_service._contexts.values()))
        await app.state.cloud_workspace_service.new_chat(context.adapter.sid,context.principal,s['generation'])
        return result
    monkeypatch.setattr(PrincipalReportRepository,'read_html',late)
    view=c.get('/api/v1/cloud/reports/'+rid)
    assert view.status_code==403 and '<html' not in view.text.lower()


def test_owned_history_without_exact_binding_is_refused(cloud_product,monkeypatch):
    from backend.app.persistence.cloud_bindings import CloudBindingRepository
    c,_,h,s,_=cloud_product
    assert c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询总销售额','request_id':'legacy-binding',
        'expected_generation':s['generation']}).status_code==200
    async def absent(*args): return None
    monkeypatch.setattr(CloudBindingRepository,'get',absent)
    response=c.get('/api/v1/cloud/history/'+s['conversation_id'])
    assert response.status_code==403 and 'legacy-binding' not in response.text


def test_late_chat_response_after_new_chat_cannot_commit(cloud_product,monkeypatch):
    from backend.app.application.mock_turn_service import MockTurnService
    c,app,h,s,_=cloud_product
    original=MockTurnService.execute
    async def switch(service,*args,**kwargs):
        context=next(iter(app.state.cloud_workspace_service._contexts.values()))
        await app.state.cloud_workspace_service.new_chat(context.adapter.sid,context.principal,s['generation'])
        return await original(service,*args,**kwargs)
    monkeypatch.setattr(MockTurnService,'execute',switch)
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询总销售额','request_id':'synthetic-late',
        'expected_generation':s['generation']})
    assert response.status_code==403
    assert c.get('/api/v1/cloud/history').json()['items']==[]
