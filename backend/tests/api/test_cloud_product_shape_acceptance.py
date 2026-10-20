"""SYNTHETIC product matrix, reusing existing language/schema/shape fixtures.

Artificial values never constitute native Fabric IQ Real evidence. The same
Cloud Auth, catalog binding, formal factual callbacks, owner storage and APIs
are used; no alternate production planner/provider is introduced.
"""
import json

import pytest

from backend.tests.api.test_cloud_factual_e2e import factual_product
from backend.tests.api.test_model_semantic_context import LanguageDraft,RuntimeAdapter
from backend.tests.fixtures.semantic_context_domains import domains
from backend.app.schemas.data_contracts import QueryShape,ColumnMembersResult
from backend.app.intent.semantic_interpreter import SemanticFrame,SemanticEvidenceSpan,SemanticFilterMention
from backend.app.llm.base import LLMResponse
from backend.app.intent.models import TurnRelation


@pytest.mark.parametrize('shape',list(QueryShape))
def test_eight_shapes_in_formal_cloud_chain(factual_product,monkeypatch,shape):
    c,app,h,s,identity,facts,llm,results=factual_product
    domain=domains()[1]  # Non-Sales model, no invented Sales template eligibility.
    domain.schema=domain.schema.model_copy(update={'key':'mock_sales_model'})
    message={
        QueryShape.SCALAR:'PassRatio是多少',QueryShape.ENTITY_LIST:'有哪些ProgramTitle',
        QueryShape.GROUPED:'各ProgramTitle的PassRatio',QueryShape.RANKING:'PassRatio最高的是哪个ProgramTitle',
        QueryShape.MEMBER_SET:'甲站和乙站的PassRatio分别是多少',
        QueryShape.FILTERED_AGGREGATION:'甲站和乙站的PassRatio加起来多少',
        QueryShape.TREND:'每月PassRatio趋势',
        QueryShape.BOUNDED_TREND:'2025年1月到2025年3月每月PassRatio趋势',
    }[shape]
    language=LanguageDraft(domain,message,shape)
    original=llm.generate
    async def generate(request,output_type):
        if output_type is SemanticFrame and shape in {QueryShape.MEMBER_SET,QueryShape.FILTERED_AGGREGATION}:
            frame=SemanticFrame(mode='data',query_shape=shape,measure_mentions=('PassRatio',),
                member_mentions=('甲站','乙站'),filter_mentions=tuple(SemanticFilterMention(
                    member_mention=value,evidence_span=value) for value in ('甲站','乙站')),
                evidence_spans=(SemanticEvidenceSpan(slot='measure',text='PassRatio'),
                    SemanticEvidenceSpan(slot='query_shape',text=message),
                    *tuple(SemanticEvidenceSpan(slot=slot,text=value) for slot in ('member','filter') for value in ('甲站','乙站'))))
            return LLMResponse(content='{}',structured=frame,model='mock-llm')
        if request.task.value in {'understanding','understanding_coverage','semantic_selection','semantic_equivalence_veto','display_translation'}:
            return await language.generate(request,output_type)
        return await original(request,output_type)
    monkeypatch.setattr(llm,'generate',generate)
    adapter=next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    runtime=RuntimeAdapter(domain,QueryShape.SCALAR if shape==QueryShape.FILTERED_AGGREGATION else shape)
    async def schema(key):
        adapter.assert_session_binding(adapter.auth,adapter.sid,adapter.principal)
        return domain.schema.model_copy(deep=True)
    async def members(request):
        return ColumnMembersResult(semantic_model_key=request.semantic_model_key,table_name=request.table_name,
            field_name=request.field_name,values=['甲站','乙站'],source_mode='mock')
    async def execute(request):
        adapter.assert_session_binding(adapter.auth,adapter.sid,adapter.principal)
        result=await runtime.execute_dax(request)
        if shape==QueryShape.MEMBER_SET:
            result=result.model_copy(update={'rows':[['甲站',12.5],['乙站',14.0]],'row_count':2})
        return result.model_copy(update={'source_mode':'mock'})
    monkeypatch.setattr(adapter,'get_semantic_model_schema',schema)
    monkeypatch.setattr(adapter,'get_column_members',members)
    monkeypatch.setattr(adapter,'execute_dax',execute)
    assert c.get('/api/v1/cloud/report-templates').json()['items']==[]
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':message,
        'request_id':'shape-'+shape.value,'expected_generation':s['generation']})
    assert response.status_code==200
    body=response.json()
    assert body['terminal_state']=='completed',json.dumps(results[-1],default=str,ensure_ascii=False)
    assert body['memory_commit'] and body['is_mock'] and body['source_mode']=='mock'
    assert results[-1]['execution_audit']['canonical_query_plan']['query_shape']==shape.value
    assert facts and all(f.source_mode=='mock' for f in facts)
    assert c.get('/api/v1/cloud/history/'+s['conversation_id']).json()['items'][0]['answer']==body['answer']

    # Locale is presentation-only. Block every factual boundary after the one
    # successful analysis, then project its persisted recipe in both languages.
    async def forbidden(*args,**kwargs):
        raise AssertionError('locale_reentered_factual_chain')
    for method in ['get_semantic_model_schema','get_column_members','execute_dax','restore_bound_model']:
        monkeypatch.setattr(adapter,method,forbidden)
    monkeypatch.setattr(llm,'generate',forbidden)
    projections=[]
    for locale in ['zh-CN','en-US']:
        from backend.app.presentation.recipe import project_recipe
        c.portal.call(project_recipe,results[-1]['presentation_recipe'],locale)
        projection=c.post('/api/v1/cloud/presentations/'+body['request_id'],headers=h,
            json={'locale':locale,'expected_generation':s['generation']})
        assert projection.status_code==200,projection.text
        projections.append(projection.json())
    assert projections[0]['factual_hash']==projections[1]['factual_hash']
    assert projections[0]['presentation']['datasets'][0]['rows']==projections[1]['presentation']['datasets'][0]['rows']


def test_formal_followup_inherits_only_verified_scope(factual_product,monkeypatch):
    c,app,h,s,identity,facts,llm,results=factual_product
    original=llm.generate
    async def followup(request,output_type):
        if request.task.value=='semantic_selection':
            from backend.app.query_plan.grounding import CandidateSelection
            content=request.messages[-1]['content']
            if content.startswith('{'):
                payload=json.loads(content)
                candidate=next(item for item in payload['candidates'] if item['value']==payload['requested_value'])
                selection=CandidateSelection(outcome='RESOLVED',candidate_id=candidate['candidate_id'],matched_phrase=payload['requested_value'])
            else:
                phrase=content.partition('当前短语：')[2].partition('\n当前输入：')[0]
                selection=CandidateSelection(outcome='RESOLVED',candidate_id='field:Sales:Category',matched_phrase=phrase)
            return LLMResponse(content='{}',model='mock-llm',structured=selection)
        if request.task.value=='semantic_equivalence_veto':
            from backend.app.query_plan.grounding import SemanticEquivalenceVeto
            return LLMResponse(content='{}',model='mock-llm',structured=SemanticEquivalenceVeto(decision='ACCEPT',mismatch='NONE'))
        if output_type is SemanticFrame and '那办公用品呢' in request.messages[-1]['content']:
            return LLMResponse(content='{}',model='mock-llm',structured=SemanticFrame(mode='data',
                relation=TurnRelation.FOLLOW_UP,query_shape=QueryShape.SCALAR,
                referenced_context_slots=('measure',),
                filter_mentions=(SemanticFilterMention(field_mention=None,member_mention='办公用品',evidence_span='办公用品'),),
                evidence_spans=(SemanticEvidenceSpan(slot='query_shape',text='那办公用品呢'),
                    SemanticEvidenceSpan(slot='filter',text='办公用品'))))
        return await original(request,output_type)
    monkeypatch.setattr(llm,'generate',followup)
    adapter=next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    async def members(request):
        return ColumnMembersResult(semantic_model_key=request.semantic_model_key,table_name=request.table_name,
            field_name=request.field_name,values=['办公用品','家具'] if request.field_name=='Category' else [],source_mode='mock')
    original_execute=adapter.execute_dax
    async def execute(request):
        if '办公用品' in request.dax:
            from backend.app.schemas.data_contracts import QueryResult
            return QueryResult(semantic_model_key=request.semantic_model_key,columns=['[Total Sales]'],
                rows=[[700.25]],row_count=1,source_mode='mock',request_id=request.request_id)
        return await original_execute(request)
    monkeypatch.setattr(adapter,'get_column_members',members)
    monkeypatch.setattr(adapter,'execute_dax',execute)
    for rid,message in [('first','查询 Total Sales'),('follow','那办公用品呢')]:
        body=c.post('/api/v1/cloud/chat',headers=h,json={'message':message,'request_id':rid,
            'expected_generation':s['generation']}).json()
        assert body['memory_commit'],json.dumps(results[-1],default=str,ensure_ascii=False)
        assert body['is_mock']
    assert results[-1]['execution_audit']['canonical_query_plan']['measures']==['Total Sales']
    assert results[-1]['execution_audit']['canonical_query_plan']['filters'][0]['value']=='办公用品'


@pytest.mark.parametrize('template',['sales_report','sales_executive_report'])
def test_two_registered_fixed_renderers_through_cloud_resources(factual_product,monkeypatch,template):
    # Legacy formal callback hardcodes LOCAL_MCP. Correct only this artificial
    # host's source metadata before the unchanged snapshot validator runs.
    # This test is explicitly not native Cloud/Real template attestation.
    from backend.app.report.reading_context import ReportDataSnapshotBuilder
    from backend.app.schemas.report_context import ReportDataSourceKind
    original_snapshot=ReportDataSnapshotBuilder.build
    def synthetic_snapshot(builder,**kwargs):
        kwargs.update(source_kind=ReportDataSourceKind.TEST_FIXTURE,source_display_name='Synthetic fixture')
        return original_snapshot(builder,**kwargs)
    monkeypatch.setattr(ReportDataSnapshotBuilder,'build',synthetic_snapshot)
    from backend.tests.unit.test_report_generation import _RichRealReportAdapter
    from backend.app.report.registry import build_report_dispatcher
    from backend.app.report.fixed import SalesReportRenderer
    from backend.app.report.executive import ExecutiveSalesReportRenderer
    c,app,h,s,identity,facts,llm,results=factual_product
    adapter=next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    artificial=_RichRealReportAdapter()
    async def schema(key): return (await artificial.get_semantic_model_schema('local_desktop_model')).model_copy(update={'key':key})
    async def execute(request):
        result=await artificial.execute_dax(request)
        return result.model_copy(update={'semantic_model_key':request.semantic_model_key,'source_mode':'mock'})
    monkeypatch.setattr(adapter,'get_semantic_model_schema',schema)
    monkeypatch.setattr(adapter,'execute_dax',execute)
    factory=app.state.cloud_product_services
    def create(**kwargs):
        from backend.tests.api.test_cloud_factual_e2e import SyntheticFactualTurn
        return SyntheticFactualTurn(**kwargs,llm=llm,results=results,
            renderer=build_report_dispatcher(SalesReportRenderer(),ExecutiveSalesReportRenderer()))
    monkeypatch.setattr(factory,'_synthetic_turn_factory',create)
    templates=c.get('/api/v1/cloud/report-templates').json()['items']
    assert any(item['template_key']==template and item['selectable'] for item in templates)
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'生成销售分析报表','request_id':'two-'+template,
        'report_template_key':template,'expected_generation':s['generation']})
    assert response.status_code==200
    body=response.json()
    assert body['memory_commit'],json.dumps(results[-1],default=str,ensure_ascii=False)
    rid=body['report']['report_id']
    view=c.get('/api/v1/cloud/reports/'+rid)
    assert view.status_code==200 and view.content==c.get('/api/v1/cloud/reports/'+rid+'/download').content
    assert body['report']['template_key']==template and body['is_mock']
    before_spec=results[-1]['presentation_recipe'].report_spec.model_dump(mode='json')
    async def no_factual_call(*args,**kwargs):
        raise AssertionError('report_locale_called_factual_boundary')
    with monkeypatch.context() as projection:
        for method in ['get_semantic_model_schema','get_column_members','execute_dax','restore_bound_model']:
            projection.setattr(adapter,method,no_factual_call)
        projection.setattr(llm,'generate',no_factual_call)
        localized=[]
        for locale in ['zh-CN','en-US']:
            response=c.get('/api/v1/cloud/reports/'+rid+'?locale='+locale)
            assert response.status_code==200,response.text
            assert response.content==c.get('/api/v1/cloud/reports/'+rid+'/download?locale='+locale).content
            assert ('lang="'+locale+'"') in response.text
            localized.append(response.content)
        assert localized[0]!=localized[1]
        assert results[-1]['presentation_recipe'].report_spec.model_dump(mode='json')==before_spec
    assert c.request('DELETE','/api/v1/cloud/reports/'+rid,headers=h,json={'expected_generation':s['generation']}).status_code==200
    assert c.get('/api/v1/cloud/reports/'+rid+'/download').status_code==404


@pytest.mark.parametrize('failure',['provider','int64'])
def test_formal_failure_is_safe_without_factual_commit(factual_product,monkeypatch,failure):
    c,app,h,s,identity,facts,llm,results=factual_product
    adapter=next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    if failure=='provider':
        from backend.app.llm.base import LLMProviderError
        original=llm.generate
        async def fail(*args): raise LLMProviderError('SYNTHETIC_PRIVATE_PROVIDER_ERROR')
        monkeypatch.setattr(llm,'generate',fail)
    else:
        from backend.app.powerbi.fabric_iq_normalization import normalize_query
        from backend.tests.unit.test_fabric_iq_adapter import result,MODEL
        async def fail(request): return normalize_query(result(rows=[['9007199254740993']]),MODEL,request)
        monkeypatch.setattr(adapter,'execute_dax',fail)
    body=c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询 Total Sales','request_id':'failure',
        'expected_generation':s['generation']})
    assert body.status_code in (200,503)
    if body.status_code==200: assert not body.json()['memory_commit'] and not body.json()['answer']
    assert 'SYNTHETIC_PRIVATE_PROVIDER_ERROR' not in body.text
    assert not facts and not c.get('/api/v1/cloud/reports').json()['items']
