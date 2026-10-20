"""Failure-first runtime-declared identity; no UCI identity lookup."""
import json
import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.schemas.data_contracts import ColumnMembersRequest
from backend.app.application.cloud_literal_context import literal_scope, capture_frame
from backend.tests.unit.test_fabric_iq_adapter import harness  # noqa: F401
from backend.tests.unit.test_m6_5_value_search_adapter import enable_search, response
from backend.tests.unit.test_m6_5_cloud_literal_context import frame


PREFIX = 'PBIAGENT_MEMBER_IDENTITY_V1:'


def declare(transport, rule='TRAILING_SPACE_UPPER_INVARIANT_ASCII_V1'):
    transport.schema['schema']['Tables'][0]['Columns'] = [
        {'Name': 'SourceCode', 'Type': 'String', 'Description': PREFIX + json.dumps({'role':'provenance_only'})},
        {'Name': 'Category', 'Type': 'String', 'Description': PREFIX + json.dumps({
            'role':'canonical','rule':rule,'source_field':'SourceCode','input_name':'Code'})}]


@pytest.mark.parametrize('literal,canonical', [('15056BL','15056BL'),('15056bl','15056BL'),
    ('47503J ','47503J'),('abc-12_+','ABC-12_+'),(' aB ',' AB')])
@pytest.mark.asyncio
async def test_declared_literal_normalizes_before_exact_runtime_proof(harness,literal,canonical):
    _,_,transport,adapter=harness
    declare(transport);enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    transport.query=response(canonical)
    with literal_scope():
        capture_frame('查询 Code '+literal,frame(literal,'Code'))
        proof=await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name='Facts',field_name='Category'))
    assert proof.values==[canonical] and proof.truncated
    calls=[args for name,args in transport.calls if name=='ValueSearch']
    assert len(calls)==1 and calls[0]['searchTerms']==[canonical]
    assert not any(name=='ExecuteQuery' for name,_ in transport.calls)


@pytest.mark.parametrize('value', ['UNKNOWN','15056BX','15056bl'])
@pytest.mark.asyncio
async def test_non_equivalent_candidate_never_becomes_canonical(harness,value):
    _,_,transport,adapter=harness
    declare(transport);enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    transport.query=response('15056BL',values=[{'Table':'Facts','Column':'Category','Value':value,'Score':1}])
    with literal_scope():
        capture_frame('查询 Code 15056bl',frame('15056bl','Code'))
        proof=await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name='Facts',field_name='Category'))
    assert proof.values==[]
    assert not any(name=='ExecuteQuery' for name,_ in transport.calls)


@pytest.mark.asyncio
async def test_provenance_column_is_not_a_product_field(harness):
    from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    _,_,transport,adapter=harness
    declare(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    catalog=SemanticCatalogBuilder().build_from_context(ModelSemanticContextBuilder().build(adapter._schemas[ref.server_model_key]))
    assert not any(obj.canonical_name=='SourceCode' for obj in catalog.objects)


@pytest.mark.asyncio
async def test_unknown_declared_rule_fails_closed(harness):
    _,_,transport,adapter=harness
    declare(transport,rule='FUZZY')
    with pytest.raises(PowerBIAdapterError):
        await adapter.resolve_bootstrap('fixture')


@pytest.mark.parametrize('literal', ['15056BL','15056bl','15056BL '])
@pytest.mark.asyncio
async def test_existing_grounding_consumes_normalized_literal_without_core_change(harness,literal):
    from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    from backend.app.query_plan.grounding import SemanticGroundingService, GroundingStatus
    _,_,transport,adapter=harness
    declare(transport);enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    transport.query=response('15056BL')
    catalog=SemanticCatalogBuilder().build_from_context(ModelSemanticContextBuilder().build(adapter._schemas[ref.server_model_key]))
    from backend.app.intent.semantic_interpreter import SemanticFrame, SemanticFilterMention, SemanticEvidenceSpan
    message='查询 Count，Code '+literal
    draft=SemanticFrame(mode='data',query_shape='scalar',measure_mentions=('Count',),
        filter_mentions=(SemanticFilterMention(field_mention='Code',member_mention=literal,evidence_span=literal),),
        evidence_spans=(SemanticEvidenceSpan(slot='measure',text='Count'),
            SemanticEvidenceSpan(slot='filter',text=literal),SemanticEvidenceSpan(slot='query_shape',text='查询')))
    async def lookup(field,limit):
        return await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name=field.table_name,field_name=field.canonical_name,limit=limit))
    with literal_scope():
        capture_frame(message,draft)
        grounded=await SemanticGroundingService(catalog).ground_frame(message,draft,None,lookup)
    assert grounded.status==GroundingStatus.RESOLVED
    assert grounded.delta.filters[0].field=='Category' and grounded.delta.filters[0].value=='15056BL'
    assert not any(name=='ExecuteQuery' for name,_ in transport.calls)


@pytest.mark.asyncio
async def test_duplicate_exact_candidates_remain_ambiguous(harness):
    from backend.app.query_plan.grounding import MemberGrounder, GroundingStatus
    from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    _,_,transport,adapter=harness
    declare(transport);enable_search(transport)
    ref=await adapter.resolve_bootstrap('fixture')
    transport.query=response('15056BL',values=[{'Table':'Facts','Column':'Category','Value':'15056BL','Score':1}]*2)
    with literal_scope():
        capture_frame('查询 Code 15056bl',frame('15056bl','Code'))
        proof=await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name='Facts',field_name='Category'))
    catalog=SemanticCatalogBuilder().build_from_context(ModelSemanticContextBuilder().build(adapter._schemas[ref.server_model_key]))
    field=next(obj for obj in catalog.objects if obj.canonical_name=='Category')
    assert MemberGrounder.resolve(field,'15056bl',proof).status==GroundingStatus.AMBIGUOUS
    assert not any(name=='ExecuteQuery' for name,_ in transport.calls)


@pytest.mark.parametrize('value', ['İ123','ab\t',' ab\n','   '])
def test_unproven_nonascii_or_control_transform_is_rejected(value):
    from backend.app.powerbi.member_identity import canonical_literal
    with pytest.raises(PowerBIAdapterError):
        canonical_literal(value)
