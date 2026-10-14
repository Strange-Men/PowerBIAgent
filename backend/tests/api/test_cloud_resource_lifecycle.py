"""SYNTHETIC acceptance of the original resource contract under Entra ownership."""
from backend.tests.api.test_cloud_product_api import cloud_product
from backend.tests.api.test_auth_security import login
from uuid import UUID
import pytest


def seed(c, h, s, rid, report=False):
    response = c.post('/api/v1/cloud/chat', headers=h, json={
        'message':'生成销售分析报表' if report else '查询总销售额', 'request_id':rid,
        'expected_generation':s['generation'],
        'report_template_key':'sales_report' if report else None})
    assert response.status_code == 200
    assert response.json()['memory_commit']
    return response.json()


def mutate(c, h, s, kind, rid, action, title=None):
    body={'expected_generation':s['generation']}
    if title is not None: body['title']=title
    return c.request('DELETE' if action=='delete' else 'POST',
        f'/api/v1/cloud/{kind}/{rid}' + ('' if action=='delete' else '/'+action),
        headers=h,json=body)


def test_conversation_search_pagination_rename_archive_restore_delete(cloud_product):
    c,app,h,s,_=cloud_product
    seed(c,h,s,'first')
    first=s['conversation_id']
    renamed=mutate(c,h,s,'history',first,'rename','合成资源检索')
    assert renamed.status_code==200
    assert c.get('/api/v1/cloud/history?q=合成资源检索').json()['items'][0]['title']=='合成资源检索'
    archived=mutate(c,h,s,'history',first,'archive')
    assert archived.status_code==200
    s=archived.json()['workspace_status']
    assert s['conversation_id']!=first
    assert not c.get('/api/v1/cloud/history').json()['items']
    assert c.get('/api/v1/cloud/history?status=archived').json()['items'][0]['conversation_id']==first
    assert c.get('/api/v1/cloud/history/'+first).json()['items']
    assert mutate(c,h,s,'history',first,'unarchive').status_code==200
    seed(c,h,s,'second')
    page=c.get('/api/v1/cloud/history?limit=1').json()
    assert page['total_count']==2 and page['next_cursor']
    next_page=c.get('/api/v1/cloud/history',params={'limit':1,'cursor':page['next_cursor']}).json()
    assert len(next_page['items'])==1 and next_page['items'][0]!=page['items'][0]
    assert c.get('/api/v1/cloud/history',params={'status':'archived','cursor':page['next_cursor']}).status_code==422
    assert mutate(c,h,s,'history',first,'delete').status_code==200
    assert c.get('/api/v1/cloud/history/'+first).status_code in (403,404)


def test_report_lifecycle_independent_delete_tombstone(cloud_product):
    c,app,h,s,_=cloud_product
    report=seed(c,h,s,'report',report=True)['report']['report_id']
    assert mutate(c,h,s,'reports',report,'rename','合成报表标题').status_code==200
    assert c.get('/api/v1/cloud/reports').json()['items'][0]['display_title']=='合成报表标题'
    assert mutate(c,h,s,'reports',report,'archive').status_code==200
    assert not c.get('/api/v1/cloud/reports').json()['items']
    assert c.get('/api/v1/cloud/reports?status=archived').json()['items'][0]['report_id']==report
    assert c.get('/api/v1/cloud/reports/'+report+'/download').status_code==200
    assert mutate(c,h,s,'reports',report,'unarchive').status_code==200
    assert mutate(c,h,s,'reports',report,'delete').status_code==200
    assert c.get('/api/v1/cloud/reports/'+report+'/download').status_code==404
    page=c.get('/api/v1/cloud/history/'+s['conversation_id']).json()
    assert page['items'][0]['report']['availability_status']=='deleted'
    assert page['items'][0]['report']['download_reference']==''
    assert c.get('/api/v1/cloud/history').json()['items']


@pytest.mark.parametrize('kind',['history','reports'])
def test_interrupted_html_delete_retries_owned_intent(cloud_product,monkeypatch,kind):
    from pathlib import Path
    c,app,h,s,_=cloud_product
    rid=seed(c,h,s,'interrupted',report=True)['report']['report_id']
    original=Path.unlink
    def fail_html(path,*args,**kwargs):
        if path.name==rid+'.html': raise OSError('synthetic delete interruption')
        return original(path,*args,**kwargs)
    with monkeypatch.context() as blocked:
        blocked.setattr(Path,'unlink',fail_html)
        response=mutate(c,h,s,kind,s['conversation_id'] if kind=='history' else rid,'delete')
        assert response.status_code==503
    assert c.get('/api/v1/cloud/reports/'+rid+'/download').status_code==404
    current=c.get('/api/v1/cloud/status').json()
    if kind=='reports':
        context=next(iter(app.state.cloud_workspace_service._contexts.values()))
        context.adapter.allowed=False
        assert mutate(c,h,current,kind,rid,'delete').status_code==403
        context.adapter.allowed=True
        current=c.get('/api/v1/cloud/status').json()
    retry=mutate(c,h,current,kind,s['conversation_id'] if kind=='history' else rid,'delete')
    assert retry.status_code==200
    assert c.get('/api/v1/cloud/reports/'+rid+'/download').status_code==404


def test_mutation_requires_current_permission_generation_and_csrf(cloud_product):
    c,app,h,s,_=cloud_product
    seed(c,h,s,'protected')
    assert mutate(c,{},s,'history',s['conversation_id'],'rename','denied').status_code==403
    stale=dict(s,generation=s['generation']+1)
    assert mutate(c,h,stale,'history',s['conversation_id'],'delete').status_code==409
    context=next(iter(app.state.cloud_workspace_service._contexts.values()))
    context.adapter.allowed=False
    assert mutate(c,h,s,'history',s['conversation_id'],'delete').status_code==403


def test_other_principal_cursor_mutation_and_download_are_denied(cloud_product):
    c,app,h,s,identity=cloud_product
    rid=seed(c,h,s,'a-report',report=True)['report']['report_id']
    second=c.post('/api/v1/cloud/new-chat',headers=h,json={'expected_generation':s['generation']}).json()
    seed(c,h,second,'a-other')
    cursor=c.get('/api/v1/cloud/history?limit=1').json()['next_cursor']
    c.post('/auth/logout',headers=h)
    identity.claim_changes={'oid':str(UUID(int=4))}
    login(c)
    h['X-CSRF-Token']=c.get('/auth/session').json()['csrf_token']
    b=c.get('/api/v1/cloud/status').json()
    assert c.get('/api/v1/cloud/history',params={'cursor':cursor}).status_code==422
    assert mutate(c,h,b,'history',s['conversation_id'],'rename','forbidden').status_code==403
    assert mutate(c,h,b,'reports',rid,'delete').status_code==404
    assert c.get('/api/v1/cloud/reports/'+rid+'/download').status_code==404
    assert not c.get('/api/v1/cloud/history').json()['items']


@pytest.mark.parametrize('invalidate',['logout','permission','selection'])
def test_late_resource_write_rolls_back_before_commit(cloud_product,monkeypatch,invalidate):
    from backend.app.persistence.repositories.conversation_history import SQLiteConversationHistoryRepository
    c,app,h,s,identity=cloud_product
    seed(c,h,s,'late-write')
    context=next(iter(app.state.cloud_workspace_service._contexts.values()))
    original=SQLiteConversationHistoryRepository.rename
    async def intercepted(repo,*args):
        # Invalidate before the SQL call. Every SQL/flush/commit must use the
        # current ResourceLease; a historical owner is insufficient.
        if invalidate=='logout': app.state.auth_service.logout(context.adapter.sid,None)
        elif invalidate=='permission': context.adapter.allowed=False
        else: await app.state.cloud_workspace_service.new_chat(context.adapter.sid,context.principal,s['generation'])
        return await original(repo,*args)
    monkeypatch.setattr(SQLiteConversationHistoryRepository,'rename',intercepted)
    assert mutate(c,h,s,'history',s['conversation_id'],'rename','late-secret').status_code in (401,403)
    # Inspect only the newly created synthetic repository, with a current auth
    # lease, to prove the failed write never became a retained title.
    if invalidate=='logout': login(c)
    context.adapter.allowed=True
    page=c.get('/api/v1/cloud/history').json()
    assert all(item['title']!='late-secret' for item in page['items'])
