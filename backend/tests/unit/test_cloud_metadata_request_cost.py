"""Request-local authorization proofs; no principal/global access cache."""
import pytest
from uuid import UUID

from backend.app.auth.models import AuthFailure
from backend.app.persistence.cloud_bindings import CloudConversationBinding
from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
from backend.tests.unit.test_cloud_workspace_service import workspace
from backend.tests.unit.test_fabric_iq_adapter import harness  # noqa: F401
from backend.tests.api.test_cloud_product_api import cloud_product  # noqa: F401


@pytest.mark.asyncio
async def test_restore_uses_one_fresh_resolve_schema_proof(harness):
    auth,session,transport,_=harness
    service=workspace(harness)
    try:
        catalog=await service.catalog(session.session_id,session.principal)
        selected=await service.select(session.session_id,session.principal,catalog.items[0].key)
        adapter=service._context(session.session_id,session.principal).adapter
        ws,model=adapter.bound_resource_identity(selected.selected_model_key)
        binding=CloudConversationBinding(conversation_id=selected.conversation_id,model_key=selected.selected_model_key,
            workspace_id=ws,model_id=model,schema_fingerprint=compute_schema_fingerprint(adapter._schemas[selected.selected_model_key]),source_mode='real')
        transport.calls.clear()
        await service.revalidate_binding(session.session_id,session.principal,binding)
        assert [name for name,_ in transport.calls]==['ResolveFabricItem','GetSemanticModelSchema']
    finally: await service.aclose()


@pytest.mark.asyncio
async def test_fresh_restore_schema_rejects_expired_principal(harness):
    auth,session,_,adapter=harness
    ref=await adapter.resolve_bootstrap('fixture')
    auth.logout(session.session_id,None)
    with pytest.raises(AuthFailure):
        await adapter.restore_bound_schema(ref.workspace_id,ref.semantic_model_id,ref.server_model_key)


def _two_owned_histories(cloud_product):
    client,app,headers,selected,_=cloud_product
    for index in range(2):
        if index:
            selected=client.post('/api/v1/cloud/new-chat',headers=headers,json={
                'expected_generation':selected['generation']}).json()
        response=client.post('/api/v1/cloud/chat',headers=headers,json={
            'message':'查询总销售额','request_id':f'cost-synthetic-{index}',
            'expected_generation':selected['generation']})
        assert response.status_code==200 and response.json()['memory_commit']
    return client,app


def test_history_access_proof_is_unique_per_model_and_fresh_per_http_request(cloud_product,monkeypatch):
    client,app=_two_owned_histories(cloud_product)
    service=app.state.cloud_workspace_service
    original=service.revalidate_binding
    calls=[]
    async def count(*args,**kwargs):
        calls.append(args[2].conversation_id)
        return await original(*args,**kwargs)
    monkeypatch.setattr(service,'revalidate_binding',count)
    for expected in (1,2):
        response=client.get('/api/v1/cloud/history')
        assert response.status_code==200 and len(response.json()['items'])==2
        assert len(calls)==expected


def test_request_local_access_proof_does_not_survive_logout(cloud_product,monkeypatch):
    client,app=_two_owned_histories(cloud_product)
    service=app.state.cloud_workspace_service
    original=service.revalidate_binding
    async def logout_after_proof(sid,principal,binding,**kwargs):
        result=await original(sid,principal,binding,**kwargs)
        app.state.auth_service.logout(sid,None)
        return result
    monkeypatch.setattr(service,'revalidate_binding',logout_after_proof)
    response=client.get('/api/v1/cloud/history')
    assert response.status_code==401 and 'cost-synthetic' not in response.text


@pytest.mark.parametrize('change',[
    {'schema_fingerprint':'f'*64}, {'model_id':UUID(int=201)},
    {'workspace_id':UUID(int=101)}, {'source_mode':'real'},
])
def test_different_exact_binding_cannot_reuse_first_rows_proof(cloud_product,monkeypatch,change):
    from backend.app.persistence.cloud_bindings import CloudBindingRepository
    client,app=_two_owned_histories(cloud_product)
    original=CloudBindingRepository.get
    seen=[]
    async def altered(repo,conversation_id):
        binding=await original(repo,conversation_id)
        seen.append(conversation_id)
        return binding.model_copy(update=change) if len(seen)==2 else binding
    monkeypatch.setattr(CloudBindingRepository,'get',altered)
    response=client.get('/api/v1/cloud/history')
    assert response.status_code==403 and 'cost-synthetic' not in response.text


def test_policy_change_after_first_proof_prevents_list_return(cloud_product,monkeypatch):
    client,app=_two_owned_histories(cloud_product)
    service=app.state.cloud_workspace_service
    original=service.revalidate_binding
    async def revoked(sid,principal,binding,**kwargs):
        result=await original(sid,principal,binding,**kwargs)
        service._product_policy._settings.fabric_test_mode=True
        return result
    monkeypatch.setattr(service,'revalidate_binding',revoked)
    response=client.get('/api/v1/cloud/history')
    assert response.status_code==403 and 'cost-synthetic' not in response.text


def test_post_write_rate_limit_never_replays_product_mutation(cloud_product,monkeypatch):
    from backend.app.application.conversation_history_service import ConversationHistoryService
    from backend.app.powerbi.fabric_iq_contract import fail
    client,app,headers,selected,_=cloud_product
    assert client.post('/api/v1/cloud/chat',headers=headers,json={
        'message':'查询总销售额','request_id':'mutation-once',
        'expected_generation':selected['generation']}).json()['memory_commit']
    service=app.state.cloud_workspace_service
    authorize=service.revalidate_binding
    calls=[]
    async def second_rate(*args,**kwargs):
        calls.append('metadata')
        if len(calls)==2: raise fail('RATE_LIMITED')
        return await authorize(*args,**kwargs)
    rename=ConversationHistoryService.rename
    writes=[]
    async def counted(*args,**kwargs):
        writes.append('rename')
        return await rename(*args,**kwargs)
    monkeypatch.setattr(service,'revalidate_binding',second_rate)
    monkeypatch.setattr(ConversationHistoryService,'rename',counted)
    response=client.post('/api/v1/cloud/history/'+selected['conversation_id']+'/rename',headers=headers,
        json={'expected_generation':selected['generation'],'title':'synthetic acknowledged title'})
    assert response.status_code==503 and response.json()['detail']['failure']['code']=='RATE_LIMITED'
    assert writes==['rename'] and len(calls)==2
    assert client.get('/auth/session').json()['authenticated']
