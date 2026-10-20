"""Synthetic formal API proof: presentation never repeats factual work."""
from backend.tests.api.test_cloud_factual_e2e import factual_product  # noqa: F401


def test_projection_preserves_auth_generation_memory_and_facts(factual_product,monkeypatch):
    c,app,h,selection,identity,facts,llm,results=factual_product
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询 Total Sales',
        'request_id':'localization-once','expected_generation':selection['generation']})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['memory_commit'] and body['presentation_available']
    ws=app.state.cloud_workspace_service
    sid,current=next(iter(ws._contexts.items()))
    factory=app.state.cloud_product_services
    repos=c.portal.call(factory._repositories.for_session,app.state.auth_service,sid,current.principal)
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.persistence.serialization import domain_to_json
    snapshot=c.portal.call(repos.snapshots.get,'localization-once',RuntimeDataMode.MOCK)
    binding=c.portal.call(repos.cloud_bindings.get,selection['conversation_id'])
    assert snapshot.source_mode == binding.source_mode
    assert snapshot.presentation_recipe.result.source_mode == binding.source_mode
    assert snapshot.presentation_recipe.schema_fingerprint == binding.schema_fingerprint
    memory=c.portal.call(repos.memory.get_latest_committed,selection['conversation_id'],RuntimeDataMode.MOCK)
    before=(domain_to_json(snapshot),domain_to_json(memory),list(current.adapter.dax),list(llm.tasks),len(facts))
    async def forbidden(*args,**kwargs): raise AssertionError('presentation_called_factual_boundary')
    for method in ['get_semantic_model_schema','get_column_members','execute_dax','restore_bound_model']:
        monkeypatch.setattr(current.adapter,method,forbidden)
    monkeypatch.setattr(llm,'generate',forbidden)
    outputs=[]
    for locale in ['zh-CN','en-US','zh-CN','en-US','unsupported']:
        projected=c.post('/api/v1/cloud/presentations/localization-once',headers=h,
            json={'locale':locale,'expected_generation':selection['generation']})
        assert projected.status_code==200,projected.text
        outputs.append(projected.json())
    assert outputs[0]['answer']!=outputs[1]['answer']
    assert outputs[0]==outputs[2]==outputs[4]
    assert outputs[1]==outputs[3]
    assert {o['factual_hash'] for o in outputs}=={snapshot.presentation_recipe.factual_hash}
    after_snapshot=c.portal.call(repos.snapshots.get,'localization-once',RuntimeDataMode.MOCK)
    after_memory=c.portal.call(repos.memory.get_latest_committed,selection['conversation_id'],RuntimeDataMode.MOCK)
    assert before==(domain_to_json(after_snapshot),domain_to_json(after_memory),list(current.adapter.dax),list(llm.tasks),len(facts))
    assert ws.status(sid,current.principal).generation==selection['generation']
    assert c.post('/api/v1/cloud/presentations/localization-once',headers=h,
        json={'locale':'en-US','expected_generation':selection['generation']+1}).status_code==409
    assert c.post('/api/v1/cloud/presentations/localization-once',headers={'Origin':h['Origin']},
        json={'locale':'en-US','expected_generation':selection['generation']}).status_code==403
    current.adapter.allowed=False
    assert c.post('/api/v1/cloud/presentations/localization-once',headers=h,
        json={'locale':'en-US','expected_generation':selection['generation']}).status_code==403


def test_old_snapshot_and_unknown_id_cannot_trigger_analysis(factual_product,monkeypatch):
    c,app,h,selection,identity,facts,llm,results=factual_product
    for rid in ['not-owned','unknown']:
        response=c.post('/api/v1/cloud/presentations/'+rid,headers=h,
            json={'locale':'en-US','expected_generation':selection['generation']})
        assert response.status_code==404
    assert facts==[] and results==[] and llm.tasks==[]


def test_projection_rejects_schema_mismatch_without_refreshing_metadata(factual_product,monkeypatch):
    c,app,h,selection,identity,facts,llm,results=factual_product
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询 Total Sales',
        'request_id':'schema-mismatch','expected_generation':selection['generation']})
    assert response.status_code==200 and response.json()['memory_commit']
    sid,current=next(iter(app.state.cloud_workspace_service._contexts.items()))
    repos=c.portal.call(app.state.cloud_product_services._repositories.for_session,
        app.state.auth_service,sid,current.principal)
    from backend.app.memory.models import RuntimeDataMode
    snapshot=c.portal.call(repos.snapshots.get,'schema-mismatch',RuntimeDataMode.MOCK)
    changed=snapshot.model_copy(update={'presentation_recipe':snapshot.presentation_recipe.model_copy(
        update={'schema_fingerprint':'0'*64})})
    c.portal.call(repos.snapshots.save,changed,RuntimeDataMode.MOCK)
    before=(list(current.adapter.dax),list(llm.tasks),len(facts))
    async def forbidden(*args,**kwargs):raise AssertionError('projection_refreshed_metadata')
    for method in ['get_semantic_model_schema','get_column_members','execute_dax','restore_bound_model']:
        monkeypatch.setattr(current.adapter,method,forbidden)
    monkeypatch.setattr(llm,'generate',forbidden)
    rejected=c.post('/api/v1/cloud/presentations/schema-mismatch',headers=h,
        json={'locale':'en-US','expected_generation':selection['generation']})
    assert rejected.status_code==403
    assert before==(list(current.adapter.dax),list(llm.tasks),len(facts))


def test_saved_result_uses_its_own_existing_access_witness_after_selection_changes(factual_product,monkeypatch):
    c,app,h,selection,identity,facts,llm,results=factual_product
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询 Total Sales',
        'request_id':'past-result','expected_generation':selection['generation']})
    assert response.status_code==200 and response.json()['memory_commit']
    sid,current=next(iter(app.state.cloud_workspace_service._contexts.items()))
    # Simulate a later, independent selection. This does not grant access to
    # the old result: its owner/binding/policy and exact original witness remain required.
    current.keys.add('another-model');current.selected='another-model';current.generation+=1
    current.conversation_id='another-conversation'
    before=(current.selected,current.generation,current.conversation_id,list(current.adapter.dax),list(llm.tasks))
    async def forbidden(*args,**kwargs):raise AssertionError('projection_changed_factual_selection')
    for method in ['get_semantic_model_schema','get_column_members','execute_dax','restore_bound_model']:
        monkeypatch.setattr(current.adapter,method,forbidden)
    monkeypatch.setattr(llm,'generate',forbidden)
    hashes=[]
    for locale in ['zh-CN','en-US']:
        projected=c.post('/api/v1/cloud/presentations/past-result',headers=h,
            json={'locale':locale,'expected_generation':current.generation})
        assert projected.status_code==200,projected.text
        hashes.append(projected.json()['factual_hash'])
    assert hashes[0]==hashes[1]
    assert before==(current.selected,current.generation,current.conversation_id,list(current.adapter.dax),list(llm.tasks))
    current.adapter.allowed=False
    assert c.post('/api/v1/cloud/presentations/past-result',headers=h,
        json={'locale':'en-US','expected_generation':current.generation}).status_code==403
