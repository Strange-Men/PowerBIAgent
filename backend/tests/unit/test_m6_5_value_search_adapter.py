"""Actual V1 ValueSearch field shape with synthetic identities and literals."""
import json
import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_normalization import normalize_value_search
from backend.app.schemas.data_contracts import ColumnMembersRequest
from backend.app.application.cloud_literal_context import literal_scope, capture_frame
from backend.tests.unit.test_fabric_iq_adapter import harness, MODEL  # noqa: F401
from backend.tests.unit.test_m6_5_cloud_literal_context import frame


def response(literal='France', values=None, model=MODEL):
    candidates=values if values is not None else [{'Table':'Facts','Column':'Category','Value':literal,'Score':1}]
    body={'Results':{literal[0].lower()+literal[1:]:candidates},'DiagnosticMessages':None,'MWCRaid':model}
    return {'content':[{'type':'text','text':json.dumps(body)}],
        'structuredContent':{'artifact_citation':{'ArtifactId':model}},'isError':False,'resultType':'complete'}


def enable_search(transport):
    scope_entry={'type':'object','properties':{
        'tableName':{'type':['string','null']},
        'columnNames':{'type':['array','null'],'items':{'type':'string'}}}}
    transport.inventory.append({'name':'ValueSearch','inputSchema':{
        'type':'object','required':['artifactId','searchTerms'],'properties':{
            'artifactId':{'type':'string'},'searchTerms':{'type':'array','items':{'type':'string'}},
            'scope':{'type':'array','items':scope_entry}}}})
    transport._inventory={tool['name']:tool for tool in transport.inventory}


@pytest.mark.parametrize('literal',['France','Germany','United Kingdom','01234X'])
@pytest.mark.asyncio
async def test_scoped_lookup_uses_literal_and_column_no_enumeration(harness,literal):
    _,_,transport,adapter=harness
    enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    transport.query=response(literal)
    with literal_scope():
        capture_frame('查询 Category '+literal,frame(literal,'Category'))
        result=await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name='Facts',field_name='Category',limit=100))
    assert result.values==[literal] and result.truncated
    calls=[(name,args) for name,args in transport.calls if name in {'ValueSearch','ExecuteQuery'}]
    assert len(calls)==1 and calls[0][0]=='ValueSearch'
    assert calls[0][1]=={'artifactId':MODEL,'searchTerms':[literal],
        'scope':[{'tableName':'Facts','columnNames':['Category']}]}


@pytest.mark.parametrize('mutation', ['identity','diagnostic','incomplete','many','wrong-key','resource','score'])
def test_bad_search_contract_is_rejected(harness,mutation):
    _,_,_,adapter=harness
    from backend.tests.unit.test_fabric_iq_adapter import schema
    from backend.app.powerbi.fabric_iq_normalization import normalize_schema
    model=normalize_schema(schema(),MODEL,'bound',1)
    raw=response()
    body=json.loads(raw['content'][0]['text'])
    if mutation=='identity': raw['structuredContent']['artifact_citation']['ArtifactId']='00000000-0000-0000-0000-000000000099'
    if mutation=='diagnostic': body['DiagnosticMessages']=['index incomplete']
    if mutation=='incomplete': raw['resultType']='partial'
    if mutation=='many': body['Results']['france']*=13
    if mutation=='wrong-key': body['Results']={'germany':body['Results']['france']}
    if mutation=='resource': raw['content'].append({'type':'resource','resource':{'mimeType':'text/csv','text':'unsafe'}})
    if mutation=='score': body['Results']['france'][0]['Score']=True
    raw['content'][0]['text']=json.dumps(body)
    with pytest.raises(PowerBIAdapterError,match='CONTRACT_DRIFT'):
        normalize_value_search(raw,MODEL,model,'Facts','Category','France')


@pytest.mark.asyncio
async def test_logout_after_value_search_never_returns_proof(harness):
    auth,session,transport,adapter=harness
    enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    original=transport.call
    async def late(name,args):
        result=await original(name,args)
        if name=='ValueSearch': auth.logout(session.session_id,None)
        return result
    transport.call=late
    transport.query=response()
    with literal_scope():
        capture_frame('查询 Category France',frame('France','Category'))
        with pytest.raises(Exception):
            await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
                table_name='Facts',field_name='Category'))
    assert adapter.binding_count==0


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['nonexact','unknown','exact'])
async def test_multiple_literals_each_require_independent_exact_proof(harness,outcome):
    from backend.app.intent.semantic_interpreter import SemanticFrame, SemanticFilterMention
    from backend.app.query_plan.grounding import MemberGrounder, GroundingStatus
    from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    _,_,transport,adapter=harness
    enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    transport.query=response('France')
    original=transport.call
    second='france' if outcome=='nonexact' else 'Germany'
    async def search(name,args):
        if name=='ValueSearch':
            literal=args['searchTerms'][0]
            values=[{'Table':'Facts','Column':'Category','Value':literal,'Score':1}]
            if literal==second and outcome=='nonexact': values[0]['Value']='France'
            if literal==second and outcome=='unknown': values=[]
            return response(literal, values=values)
        return await original(name,args)
    transport.call=search
    draft=SemanticFrame(relation="fresh_question", changed_slots=(), referenced_context_slots=(), mode='data',query_shape='member_set',filter_mentions=(
        SemanticFilterMention(field_mention='Category',member_mention='France',evidence_span='France'),
        SemanticFilterMention(field_mention='Category',member_mention=second,evidence_span=second)))
    with literal_scope():
        capture_frame('查询 Category France 和 '+second,draft)
        result=await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name='Facts',field_name='Category'))
    catalog=SemanticCatalogBuilder().build_from_context(
        ModelSemanticContextBuilder().build(adapter._schemas[ref.server_model_key]))
    field=next(obj for obj in catalog.objects if obj.canonical_name=='Category')
    grounded=MemberGrounder.resolve(field,second,result)
    assert grounded.status==(GroundingStatus.RESOLVED if outcome=='exact' else GroundingStatus.UNRESOLVED)
    assert result.values==(['France','Germany'] if outcome=='exact' else [])
    assert result.truncated


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['exact','unknown','ambiguous','wrong_column','fuzzy'])
async def test_existing_grounding_consumes_targeted_runtime_proof(harness,outcome):
    from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    from backend.app.query_plan.grounding import SemanticGroundingService, GroundingStatus
    from backend.app.intent.semantic_interpreter import SemanticFrame, SemanticEvidenceSpan, SemanticFilterMention
    auth,_,transport,adapter=harness
    enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    model=adapter._schemas[ref.server_model_key]
    catalog=SemanticCatalogBuilder().build_from_context(ModelSemanticContextBuilder().build(model))
    candidates=[{'Table':'Facts','Column':'Category','Value':'France','Score':1}]
    if outcome=='unknown': candidates=[]
    if outcome=='ambiguous': candidates*=2
    if outcome=='wrong_column': candidates[0]['Column']='Other'
    if outcome=='fuzzy': candidates[0]['Value']='France extended'
    transport.query=response(values=candidates)
    message='查询 Count，Category France'
    draft=SemanticFrame(relation="fresh_question", changed_slots=(), referenced_context_slots=(), mode='data',query_shape='scalar',measure_mentions=('Count',),
        filter_mentions=(SemanticFilterMention(field_mention='Category',member_mention='France',evidence_span='France'),),
        evidence_spans=(SemanticEvidenceSpan(slot='measure',text='Count'),
            SemanticEvidenceSpan(slot='filter',text='France'),SemanticEvidenceSpan(slot='query_shape',text='查询')))
    async def lookup(field,limit):
        return await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name=field.table_name,field_name=field.canonical_name,limit=limit))
    with literal_scope():
        capture_frame(message,draft)
        grounded=await SemanticGroundingService(catalog).ground_frame(message,draft,None,lookup)
    assert grounded.status==(GroundingStatus.RESOLVED if outcome=='exact' else
        GroundingStatus.AMBIGUOUS if outcome=='ambiguous' else GroundingStatus.UNRESOLVED)
    if outcome=='exact':
        assert grounded.delta.filters[0].value=='France'
    assert not any(name=='ExecuteQuery' for name,_ in transport.calls)
