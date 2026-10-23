"""Round 1 only: temporal authority, pending obligations and exact members."""
from datetime import date
from contextlib import nullcontext
import json

import pytest

from backend.app.intent.models import TimeIntentDraft, TurnRelation
from backend.app.intent.semantic_interpreter import SemanticFrame
from backend.app.memory.models import PendingClarificationContext, RuntimeDataMode
from backend.app.query_plan.clarification import PendingClarificationService
from backend.app.query_plan.clarification_reasons import ClarificationReason
from backend.app.query_plan.grounding import (
    GroundedSemanticDelta, GroundingOutcome, GroundingStatus, SemanticGroundingService,
)
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder, GlossaryCatalogError
from backend.app.schemas.data_contracts import ColumnMembersResult, QueryShape
from backend.tests.unit.test_m6_5_operator_temporal_binding import schema, registry
from backend.tests.unit.test_fabric_iq_adapter import harness


def test_provider_declarations_reach_catalog_without_inventing_topology():
    from backend.tests.unit.test_fabric_iq_adapter import schema as wire_schema, MODEL
    from backend.app.powerbi.fabric_iq_normalization import normalize_schema
    raw = wire_schema()
    raw['schema']['Tables'][0]['DisplayName'] = 'Events label'
    raw['schema']['Tables'][0]['Measures'][0]['Expression'] = 'COUNTROWS(Facts)'
    value = normalize_schema(raw, MODEL, 'unknown-resource', 1)
    catalog = SemanticCatalogBuilder().build(value)
    ctx = catalog.context
    assert not ctx.relationships
    assert any(e.kind == 'relationship_endpoints' and e.level == 'AUTHORITATIVE' for e in ctx.provider_evidence)
    assert any(e.kind == 'cardinality' and e.level == 'UNKNOWN' for e in ctx.provider_evidence)
    assert ctx.tables[0].display_name == 'Events label'
    assert ctx.measures[0].expression == 'COUNTROWS(Facts)'
    assert catalog.capabilities.relationship_evidence == 'ENDPOINT_DECLARATIONS_ONLY'
    assert catalog.capabilities.default_temporal_authority == 'UNKNOWN'
    assert catalog.capabilities.exact_member_search == 'UNKNOWN'
    evidence = catalog.selection_evidence(catalog.objects)
    assert evidence['provider_evidence'] and evidence['capabilities']


@pytest.mark.parametrize('missing', ['relation', 'changed_slots', 'referenced_context_slots'])
@pytest.mark.asyncio
async def test_understanding_omitted_conversation_contract_is_repaired_or_rejected(missing):
    from backend.app.intent.semantic_interpreter import LLMSemanticInterpreter, SemanticInterpretationError
    from backend.app.llm.base import LLMResponse
    class Provider:
        is_mock = False
        calls = 0
        async def generate(self, request, response_model):
            self.calls += 1
            data = dict(mode='data', relation='fresh_question',changed_slots=[],referenced_context_slots=[])
            data.pop(missing)
            return LLMResponse(content='{}',structured=SemanticFrame(**data),model='synthetic')
    provider = Provider()
    with pytest.raises(SemanticInterpretationError):
        await LLMSemanticInterpreter(provider).interpret('synthetic')
    assert provider.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('repair', [True, False])
async def test_time_only_aggregate_invalid_shape_repairs_or_fails_before_grounding(repair):
    from backend.app.intent.semantic_interpreter import (
        LLMSemanticInterpreter, SemanticInterpretationError, SemanticCoverageDecision)
    from backend.app.llm.base import LLMResponse

    class Provider:
        is_mock = False
        calls = 0
        async def generate(self, request, response_model):
            if response_model is SemanticCoverageDecision:
                return LLMResponse(content='{}', structured=SemanticCoverageDecision(decision='ACCEPT'), model='synthetic')
            self.calls += 1
            frame = SemanticFrame(mode='data', relation='fresh_question', changed_slots=[],
                referenced_context_slots=[], query_shape='scalar' if repair and self.calls==2 else 'filtered_aggregation',
                measure_mentions=['Amount'], time_mentions=['Events[ShipDay]', '2020'],
                time_intent=TimeIntentDraft(kind='absolute_year', expression='2020', year=2020),
                evidence_spans=[{'slot':slot, 'text':text} for slot,text in [
                    ('measure','Amount'),('time','Events[ShipDay]'),('time','2020'),('query_shape','Amount')]])
            return LLMResponse(content='{}', structured=frame, model='synthetic')

    provider = Provider()
    if repair:
        frame = await LLMSemanticInterpreter(provider).interpret('Amount using Events[ShipDay] in 2020')
        assert frame.query_shape == QueryShape.SCALAR
        assert frame.time_intent.year == 2020
    else:
        with pytest.raises(SemanticInterpretationError, match='time_only_aggregate_requires_scalar'):
            await LLMSemanticInterpreter(provider).interpret('Amount using Events[ShipDay] in 2020')
    assert provider.calls == 2


@pytest.mark.parametrize('boundary', ['fresh', 'model', 'conversation'])
def test_pending_semantic_scope_is_not_inherited_across_boundaries(boundary):
    previous = PendingClarificationContext(conversation_id='other' if boundary == 'conversation' else 'c',
        semantic_model_key='other' if boundary == 'model' else 'm', schema_fingerprint='a'*64,
        measures=['Amount'],filters=[{'field':'Market','value':'France'}],time_obligation=h1(),
        missing_slots=['time'],last_request_id='q',runtime_mode='real')
    result = merge(previous,GroundingOutcome(status=GroundingStatus.RESOLVED,
        delta=GroundedSemanticDelta(measures=['Units'])),SemanticFrame(mode='data',
            relation='fresh_question' if boundary == 'fresh' else 'follow_up'))
    assert result.context.measures == ['Units']
    assert result.context.filters == [] and result.context.time_obligation is None


def h1():
    return TimeIntentDraft(kind='bounded_range', expression='H1 2011',
        start_date=date(2011, 1, 1), end_date=date(2011, 6, 30))


def merge(previous, outcome, frame):
    return PendingClarificationService().merge(previous=previous, outcome=outcome,
        user_input='synthetic', conversation_id='c', request_id='q', semantic_model_key='m',
        schema_fingerprint='a'*64, runtime_mode=RuntimeDataMode.REAL,
        intent='data_question', committed=None, semantic_frame=frame)


@pytest.mark.parametrize('slot', ['measure', 'member'])
def test_unresolved_h1_survives_unrelated_replacement(slot):
    first = merge(None, GroundingOutcome(status=GroundingStatus.UNRESOLVED,
        delta=GroundedSemanticDelta(measures=['Amount'], filters=[{'field':'Market','value':'France'}]),
        clarification_reason=ClarificationReason.INCOMPLETE_TIME_RANGE),
        SemanticFrame(mode='data', query_shape='filtered_aggregation', time_intent=h1()))
    assert first.context.time_obligation == h1()
    delta = GroundedSemanticDelta(measures=['Units']) if slot == 'measure' else (
        GroundedSemanticDelta(filters=[{'field':'Market','value':'Germany'}]))
    follow = merge(first.context, GroundingOutcome(status=GroundingStatus.RESOLVED, delta=delta),
        SemanticFrame(mode='data', relation='replace', changed_slots=[slot]))
    assert not follow.complete and follow.executable_delta is None
    assert follow.context.missing_slots == ['time']
    assert follow.context.time_obligation == h1()
    assert follow.context.filters[0].value == ('France' if slot == 'measure' else 'Germany')
    assert follow.context.measures == (['Units'] if slot == 'measure' else ['Amount'])


def test_pending_retains_both_measures_and_only_date_proof_discharges_h1():
    previous = PendingClarificationContext(conversation_id='c',semantic_model_key='m',
        schema_fingerprint='a'*64,measures=['Amount','Units'],time_obligation=h1(),
        missing_slots=['time'],last_request_id='q',runtime_mode='real')
    assert not merge(previous, GroundingOutcome(status=GroundingStatus.RESOLVED,delta=GroundedSemanticDelta()),
        SemanticFrame(mode='data',relation='follow_up')).complete
    from backend.app.schemas.data_contracts import TimeRangeSpec
    proven = GroundedSemanticDelta(time_specified=True,time_range=TimeRangeSpec(
        date_field='Day', start_date=date(2011,1,1),end_date=date(2011,6,30),mode='explicit_range'))
    final = merge(previous,GroundingOutcome(status=GroundingStatus.RESOLVED,delta=proven),
        SemanticFrame(mode='data',relation='follow_up',changed_slots=['time']))
    assert final.complete and final.context.time_obligation is None
    assert final.executable_delta.measures == ['Amount','Units']


@pytest.mark.asyncio
async def test_exact_operator_authority_resolves_bounded_month_trend():
    current = schema()
    from backend.app.query_plan.model_override import resolve_model_override
    ctx = ModelSemanticContextBuilder().build(current)
    catalog = SemanticCatalogBuilder().build_from_context(ctx,resolve_model_override(ctx,registry(current)))
    async def no_members(*args):
        raise AssertionError('Explicit operator month projection requires no member scan')
    outcome = await SemanticGroundingService(catalog).ground_frame('Amount H1 2011 monthly trend',
        SemanticFrame(mode='data',query_shape='bounded_trend',measure_mentions=['Amount'],
            time_mentions=['H1 2011'],time_intent=h1()),None,no_members)
    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta.time_range.date_field == 'Day'
    assert outcome.delta.dimensions == ['Period']
    assert outcome.delta.time_range.start_date == date(2011,1,1)
    assert outcome.delta.time_range.end_date == date(2011,6,30)


@pytest.mark.parametrize('drift', [None, 'fingerprint', 'resource'])
def test_temporal_registry_uses_exact_resource_across_opaque_session_keys(drift):
    from backend.app.query_plan.model_override import resolve_model_override
    current = schema()
    resource = {'workspace_id':'00000000-0000-0000-0000-000000000011',
                'model_id':'00000000-0000-0000-0000-000000000012'}
    current.provider_metadata['resource_identity'] = resource
    ctx = ModelSemanticContextBuilder().build(current)
    config = registry(current)
    binding = config['overrides'][0]
    binding['semantic_model_key'] = binding['runtime_identity'] = (
        'fabric_iq:'+resource['workspace_id']+':'+resource['model_id'])
    current.key = 'new-opaque-key'
    if drift == 'fingerprint': binding['schema_fingerprint'] = '0'*64
    if drift == 'resource': current.provider_metadata['resource_identity']['model_id'] = resource['workspace_id']
    ctx = ModelSemanticContextBuilder().build(current)
    if drift == 'fingerprint':
        with pytest.raises(GlossaryCatalogError): resolve_model_override(ctx,config)
    elif drift == 'resource':
        assert resolve_model_override(ctx,config) is None
    else:
        catalog = SemanticCatalogBuilder().build_from_context(ctx,resolve_model_override(ctx,config))
        assert catalog.get('field:Events:Day').temporal_role == 'default'


@pytest.mark.asyncio
async def test_explicit_exact_field_allows_two_measures_in_existing_plan():
    from backend.app.schemas.data_contracts import ColumnSchema, MeasureSchema
    current = schema()
    current.tables[0].columns.append(ColumnSchema(name='Item',data_type='string'))
    current.tables[0].measures.append(MeasureSchema(name='Units',data_type='Decimal'))
    catalog = SemanticCatalogBuilder().build(current)
    async def members(field,limit):
        assert field.canonical_name == 'Item'
        return ColumnMembersResult(semantic_model_key=current.key,table_name='Events',
            field_name='Item',values=['ZX19'],truncated=True,source_mode='real')
    frame = SemanticFrame(mode='data',query_shape='filtered_aggregation',
        measure_mentions=['Amount','Units'],filter_mentions=[
            {'field_mention':'Events[Item]','member_mention':'ZX19','evidence_span':'ZX19'}])
    outcome = await SemanticGroundingService(catalog).ground_frame('Amount and Units for Events[Item] ZX19',
        frame,None,members)
    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta.measures == ['Amount','Units']
    assert outcome.delta.filters[0].value == 'ZX19'
    from backend.app.query_plan.semantic_frame_adapter import build_grounding_draft
    from backend.app.query_plan.state_transition import StateTransitionService
    from backend.app.query_plan.completeness import CanonicalShapeCompletenessGate
    from backend.app.dax.builder import DeterministicDAXBuilder
    plan = StateTransitionService().merge(build_grounding_draft(frame,
        user_input='Amount and Units for Events[Item] ZX19',semantic_model_key=current.key),
        outcome.delta,None).query_plan
    assert plan.query_shape == QueryShape.FILTERED_AGGREGATION
    assert CanonicalShapeCompletenessGate().validate(plan,catalog=catalog).complete
    dax = DeterministicDAXBuilder().build(plan,current).dax
    assert '[Amount]' in dax and '[Units]' in dax and 'ZX19' in dax


@pytest.mark.asyncio
@pytest.mark.parametrize('explicit', [True, False])
async def test_explicit_qualified_date_survives_year_only_language_hint(explicit):
    from backend.app.schemas.data_contracts import ColumnSchema
    current = schema()
    current.tables[0].columns.append(ColumnSchema(name='ShipDay', data_type='datetime'))
    catalog = SemanticCatalogBuilder().build(current)
    frame = SemanticFrame(mode='data', query_shape='scalar', measure_mentions=['Amount'],
        time_mentions=['2020'], time_intent=TimeIntentDraft(kind='bounded_range',
            expression='2020', start_date=date(2020,1,1), end_date=date(2020,12,31)))
    async def no_members(*args):
        raise AssertionError('A date selection needs no member scan')
    outcome = await SemanticGroundingService(catalog).ground_frame(
        'Amount in 2020' + (' using Events[ShipDay]' if explicit else ''), frame, None, no_members)
    if explicit:
        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.time_range.date_field == 'ShipDay'
        assert outcome.delta.dimension_tables['ShipDay'] == 'Events'
        assert not outcome.delta.dimensions
    else:
        assert outcome.status == GroundingStatus.AMBIGUOUS
        assert outcome.delta.time_range is None


@pytest.mark.asyncio
@pytest.mark.parametrize('semantic_choice,hits,expected', [
    ('Item', ['Item'], 'RESOLVED'),
    (None, ['Item'], 'UNRESOLVED'),
    ('Other', ['Item'], 'UNRESOLVED'),
    ('Item', ['Item', 'Other'], 'AMBIGUOUS'),
    ('Item', [], 'UNRESOLVED'),
])
async def test_fieldless_member_combines_independent_catalog_semantics_and_exact_existence(
        semantic_choice, hits, expected):
    from backend.app.schemas.data_contracts import ColumnSchema, MeasureSchema
    from backend.app.query_plan.grounding import ObjectGroundingResult
    current = schema()
    current.tables[0].columns.extend(ColumnSchema(name=n, data_type='string') for n in ('Item', 'Other'))
    current.tables[0].measures.append(MeasureSchema(name='Units', data_type='Decimal'))
    catalog = SemanticCatalogBuilder().build(current)
    order = []

    class ExistingSelector:
        async def select(self, phrase, user_input, candidates, committed_context, **kwargs):
            order.append('catalog')
            assert {obj.canonical_name for obj in candidates} >= {'Item', 'Other'}
            return ObjectGroundingResult(role='filter_field', phrase=phrase,
                status='RESOLVED' if semantic_choice else 'AMBIGUOUS',
                canonical_object=catalog.get(f'field:Events:{semantic_choice}') if semantic_choice else None)

    async def discovery(literal):
        order.append('runtime')
        return ColumnMembersResult(semantic_model_key=current.key, table_name='', field_name='',
            source_mode='real', truncated=True, field_candidates=[
                {'table_name':'Events', 'field_name':name, 'canonical_value':literal} for name in hits])

    async def no_scan(*args):
        raise AssertionError('The exact existence witness needs no field scan')

    outcome = await SemanticGroundingService(catalog, selector=ExistingSelector(),
        member_discovery=discovery).ground_frame('Amount and Units for item ZX19',
            SemanticFrame(mode='data', query_shape='filtered_aggregation',
                measure_mentions=['Amount', 'Units'], member_mentions=['ZX19']), None, no_scan)
    assert order == ['catalog', 'runtime']
    assert outcome.status.value == expected
    if expected == 'RESOLVED':
        assert outcome.delta.measures == ['Amount', 'Units']
        assert outcome.delta.filters[0].field == 'Item'
        assert outcome.delta.filters[0].value == 'ZX19'
    else:
        assert not outcome.delta.filters


@pytest.mark.asyncio
@pytest.mark.parametrize('candidates', [[], [('Events','Item')], [('Events','Item'),('Events','Other')]])
async def test_model_wide_candidates_never_claim_exhaustive_field_authority(candidates):
    from backend.app.schemas.data_contracts import ColumnSchema
    current = schema()
    current.tables[0].columns.extend(ColumnSchema(name=n,data_type='string') for n in ('Item','Other'))
    catalog = SemanticCatalogBuilder().build(current)
    calls = []
    async def discovery(literal):
        calls.append(literal)
        return ColumnMembersResult(semantic_model_key=current.key,table_name='',field_name='',
            values=[],source_mode='real',truncated=True,field_candidates=[
                {'table_name':t,'field_name':f,'canonical_value':literal} for t,f in candidates])
    async def no_scan(*args):
        raise AssertionError('No guessed field or exhaustive scan')
    outcome = await SemanticGroundingService(catalog,member_discovery=discovery).ground_frame(
        'Amount for ZX19',SemanticFrame(mode='data',query_shape='filtered_aggregation',
            measure_mentions=['Amount'],member_mentions=['ZX19']),None,no_scan)
    assert calls == ['ZX19']
    assert outcome.status in {GroundingStatus.UNRESOLVED,GroundingStatus.AMBIGUOUS}
    assert outcome.delta is None or not outcome.delta.filters


@pytest.mark.parametrize('bad', [None,'model','partial','unknown','fuzzy'])
def test_value_search_candidates_are_exact_and_never_executable(bad):
    from backend.app.powerbi.fabric_iq_normalization import normalize_value_search, normalize_schema
    from backend.tests.unit.test_fabric_iq_adapter import MODEL, WORKSPACE, schema as wire_schema
    from backend.app.powerbi.base import PowerBIAdapterError
    current = normalize_schema(wire_schema(),MODEL,'m',1)
    raw = {'resultType':'complete','structuredContent':{'artifact_citation':{'ArtifactId':MODEL}},
        'content':[{'type':'text','text':json.dumps({'Results':{'ZX19':[
            {'Table':'Facts','Column':'Missing' if bad=='unknown' else 'Category',
             'Value':'ZX20' if bad=='fuzzy' else 'ZX19','Score':1}]}})}]}
    if bad == 'model': raw['structuredContent']['artifact_citation']['ArtifactId'] = WORKSPACE
    if bad == 'partial': raw['resultType'] = 'partial'
    if bad in {'model','partial','unknown'}:
        with pytest.raises(PowerBIAdapterError): normalize_value_search(raw,MODEL,current,None,None,'ZX19')
    else:
        proof = normalize_value_search(raw,MODEL,current,None,None,'ZX19')
        assert proof.values == [] and proof.truncated
        assert len(proof.field_candidates) == (0 if bad=='fuzzy' else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', [False, True])
async def test_field_discovery_uses_one_exact_search_and_revalidates_principal(harness, revoke):
    from backend.tests.unit.test_m6_5_value_search_adapter import enable_search, response
    from backend.tests.unit.test_fabric_iq_adapter import MODEL
    from backend.app.schemas.data_contracts import ColumnMembersRequest
    auth, session, transport, adapter = harness
    enable_search(transport)
    ref = await adapter.resolve_bootstrap('fixture')
    transport.query = response('ZX19')
    original = transport.call
    async def search(name, arguments):
        result = await original(name, arguments)
        if name == 'ValueSearch' and revoke:
            auth.logout(session.session_id, None)
        return result
    transport.call = search
    request = ColumnMembersRequest(semantic_model_key=ref.server_model_key,search_literal='ZX19')
    with pytest.raises(Exception) if revoke else nullcontext():
        result = await adapter.get_column_members(request)
        assert result.values == [] and result.truncated
        assert result.field_candidates[0].canonical_value == 'ZX19'
    calls = [(name,args) for name,args in transport.calls if name in {'ValueSearch','ExecuteQuery'}]
    assert calls == [('ValueSearch',{'artifactId':MODEL,'searchTerms':['ZX19']})]


@pytest.mark.asyncio
@pytest.mark.parametrize('evidence_failure',[False,True,'shape'])
async def test_pending_h1_measure_replacement_is_zero_execution_in_product_pipeline(monkeypatch,evidence_failure):
    from httpx import ASGITransport, AsyncClient
    from backend.tests.api.test_chat import (
        _patch_m533_multi_turn_composition, _M24FakeLocalPowerBIAdapter, _semantic_frame)
    from backend.app.intent.semantic_interpreter import LLMSemanticInterpreter, SemanticFilterMention
    from backend.app.schemas.data_contracts import ColumnMembersResult, TableSchema, ColumnSchema, QueryShape
    import backend.app.main as main_module

    class DateAmbiguousAdapter(_M24FakeLocalPowerBIAdapter):
        member_calls = 0
        async def get_semantic_model_schema(self, key):
            value = await super().get_semantic_model_schema(key)
            value.tables[0].columns.append(ColumnSchema(name='ShipDate',data_type='datetime'))
            value.tables.append(TableSchema(name='Markets',columns=[ColumnSchema(name='Country',data_type='string')]))
            return value

        async def get_column_members(self, request):
            self.member_calls += 1
            if evidence_failure is True and self.member_calls == 1:
                from backend.app.powerbi.base import PowerBIAdapterError
                raise PowerBIAdapterError('RESULT_LIMIT_EXCEEDED',provider='synthetic',error_type='RESULT_LIMIT_EXCEEDED')
            return ColumnMembersResult(semantic_model_key=request.semantic_model_key,
                table_name=request.table_name,field_name=request.field_name,values=['France'],source_mode='real')

        async def execute_dax(self, request):
            raise AssertionError('Unresolved date must execute ZERO DAX')

    async def interpret(self, text, **kwargs):
        if text.startswith('What about'):
            return _semantic_frame(text,shape=QueryShape.FILTERED_AGGREGATION,
                measures=('Total Sales',),filters=(() if evidence_failure == 'shape' else
                    (SemanticFilterMention(field_mention='Country',member_mention='France',evidence_span='France'),)),
                time_mentions=(('Sales[OrderDate]', 'first half of 2011') if evidence_failure == 'shape' else ()),
                time_intent=TimeIntentDraft(kind='bounded_range',expression='first half of 2011',start_date=date(2011,1,1),end_date=date(2011,6,30)))
        return _semantic_frame(text,shape=None,measures=('total quantity',),relation=TurnRelation.REPLACE,
            changed_slots=('measure',),referenced_context_slots=('time','filter','query_shape'))

    app, _ = _patch_m533_multi_turn_composition(monkeypatch)
    monkeypatch.setattr(main_module,'LocalMCPPowerBIAdapter',DateAmbiguousAdapter)
    app = main_module.create_app(settings=app.state.settings)
    monkeypatch.setattr(LLMSemanticInterpreter,'interpret',interpret)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            with nullcontext():
                for request_id, text in [('h1-first','What about France? What were its Total Sales in the first half of 2011?'
                                         + (' using Sales[OrderDate]' if evidence_failure == 'shape' else '')),
                                         ('h1-replace','Switch that to total quantity.')]:
                    response=await client.post('/api/v1/chat',json={'conversation_id':'sticky-h1','request_id':request_id,
                        'message':text,'semantic_model_key':'local_desktop_model'})
                    body=response.json()
                    assert body['terminal_state']==('tool_failed' if evidence_failure is True and request_id=='h1-first' else 'clarification_required')
                    assert body['memory_commit'] is False
                    assert body['answer'] is None
                    assert 'execute_dax' not in body['tool_sequence']
                    if body['terminal_state']=='clarification_required':
                        assert body['execution_audit']['dax_executed'] is False
                    pending=await app.state.turn_service.pipeline.get_pending_clarification('sticky-h1',RuntimeDataMode.REAL)
                    assert pending is not None
                    time = pending.time_obligation or pending.time_range
                    assert time.start_date==date(2011,1,1)
                    assert time.end_date==date(2011,6,30)
                    if evidence_failure is False:
                        assert pending.filters[0].value=='France'
                    if evidence_failure is True:
                        assert (any(item.value=='France' for item in pending.filters)
                            or any(item.member_mention=='France' for item in pending.member_obligations))
                    assert ('filter' if evidence_failure == 'shape' else 'time') in pending.missing_slots
                    assert await app.state.turn_service.pipeline.get_latest_committed_memory('sticky-h1',RuntimeDataMode.REAL) is None
                assert pending.measures==['Total Quantity']

@pytest.mark.asyncio
async def test_member_replacement_validation_failure_preserves_filter_for_measure_followup(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from backend.tests.api.test_chat import _patch_m533_multi_turn_composition, _M24FakeLocalPowerBIAdapter, _semantic_frame
    from backend.app.intent.semantic_interpreter import LLMSemanticInterpreter, SemanticFilterMention
    from backend.app.schemas.data_contracts import ColumnMembersResult, TableSchema, ColumnSchema, QueryShape

    class UnrelatedMembersAdapter(_M24FakeLocalPowerBIAdapter):
        async def get_semantic_model_schema(self, key):
            value = await super().get_semantic_model_schema(key)
            value.tables.append(TableSchema(name='Markets',columns=[ColumnSchema(name='Market',data_type='string')]))
            return value

        async def get_column_members(self, request):
            return ColumnMembersResult(semantic_model_key=request.semantic_model_key,table_name=request.table_name,
                field_name=request.field_name,values=['North'],source_mode='real')

        async def execute_dax(self, request):
            raise AssertionError('A rejected member filter must never become an all-time query')

    async def interpret(self, text, **kwargs):
        if text.startswith('What'):
            return _semantic_frame(text,shape=QueryShape.FILTERED_AGGREGATION,measures=('Total Sales',),
                filters=(SemanticFilterMention(field_mention='Markets[Market]',member_mention='Absent',evidence_span='Absent'),))
        if text.startswith('Switch Markets'):
            return _semantic_frame(text,shape=None,relation=TurnRelation.REPLACE,changed_slots=('member',),
                referenced_context_slots=('measure','filter','query_shape'),
                filters=(SemanticFilterMention(field_mention='Markets[Market]',member_mention='North',evidence_span='North'),))
        return _semantic_frame(text,shape=None,measures=('total quantity',),relation=TurnRelation.REPLACE,
            changed_slots=('measure',),referenced_context_slots=('filter','query_shape'))

    app, _ = _patch_m533_multi_turn_composition(monkeypatch,adapter_type=UnrelatedMembersAdapter)
    monkeypatch.setattr(LLMSemanticInterpreter,'interpret',interpret)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            for index,text in enumerate(['What is Total Sales where Markets[Market] equals Absent?',
                                        'Switch Markets[Market] to North.','Switch that to total quantity.']):
                response=await client.post('/api/v1/chat',json={'conversation_id':'sticky-member','request_id':f'member-{index}',
                    'message':text,'semantic_model_key':'local_desktop_model'})
                body=response.json()
                assert body['terminal_state']==('clarification_required' if index==0 else 'validation_failed')
                assert body['memory_commit'] is False
                assert body['answer'] is None
                assert 'execute_dax' not in body['tool_sequence']
                pending=await app.state.turn_service.pipeline.get_pending_clarification('sticky-member',RuntimeDataMode.REAL)
                assert pending is not None
                if index:
                    assert pending.filters[0].value=='North'
                    assert pending.dimension_tables['Market']=='Markets'
                assert await app.state.turn_service.pipeline.get_latest_committed_memory('sticky-member',RuntimeDataMode.REAL) is None
            assert pending.measures==['Total Quantity']
