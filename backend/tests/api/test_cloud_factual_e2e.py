"""Offline Synthetic E2E of the frozen factual callbacks through Cloud APIs.

The legacy service's adapter flag selects its formal or old fixture callbacks.
The test-only branch view below selects formal callbacks; it is NOT a Provider
and grants no execution authorization. The actual adapter/LLM, pipeline mode,
QueryResults, facts, snapshots, artifacts and public API all remain MOCK.
No production flag, environment variable or client input installs this host.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.application.cloud_product_services import CloudProductServiceFactory
from backend.app.application.cloud_workspace_service import CloudWorkspaceService
from backend.app.application.deepseek_turn_service import LLMTurnService
from backend.app.auth.models import AuthFailure
from backend.app.config.settings import LLMMode, PowerBIMode
from backend.app.facts import VerifiedFactSetBuilder
from backend.app.harness.models import HarnessConfig
from backend.app.intent.semantic_interpreter import (
    SemanticFrame, SemanticInterpretationMode, SemanticEvidenceSpan,
    SemanticCoverageDecision,
)
from backend.app.llm.base import LLMResponse
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.profiles import mock_profile
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.llm.registry import LLMProviderSnapshot
from backend.app.main import create_app
from backend.app.memory.models import RuntimeDataMode
from backend.app.persistence.database import create_engine, create_session_factory
from backend.app.persistence.models import Base
from backend.app.persistence.ownership import PrincipalScopedRepositoryFactory
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.intent import ReportIntentDraft
from backend.app.schemas.data_contracts import QueryResult, QueryShape
from backend.app.answer.natural import NaturalAnswerDraft
from backend.tests.api.test_auth_security import config, FakeIdentity, login, ORIGIN
from backend.tests.api.test_cloud_product_api import SyntheticAdapter, SyntheticREST
from backend.tests.unit.test_report_generation import _schema


class FactualSyntheticAdapter(SyntheticAdapter):
    """Finite, owned artificial model; strict native execution is never used."""
    def __init__(self, *args):
        super().__init__(*args)
        self.dax = []
        self.truncated = False
        self.before_result = None

    async def get_semantic_model_schema(self, key):
        self.assert_session_binding(self.auth, self.sid, self.principal)
        self.bound_resource_identity(key)
        return _schema().model_copy(update={'key':key, 'name':'Synthetic Sales'})

    async def execute_dax(self, request):
        self.assert_session_binding(self.auth, self.sid, self.principal)
        self.bound_resource_identity(request.semantic_model_key)
        self.dax.append(request.dax)
        if 'Total Quantity' in request.dax:
            columns, rows = ['[Total Quantity]'], [[9]]
        elif '[Category]' in request.dax:
            columns, rows = ['Sales[Category]', '[Total Sales]'], [['办公用品',700.25],['家具',500.25]]
        elif '[Product]' in request.dax:
            columns, rows = ['Sales[Product]', '[Total Sales]'], [['产品 A',800.0],['产品 B',400.5]]
        else:
            columns, rows = ['[Total Sales]'], [[1200.5]]
        if self.before_result: await self.before_result()
        self.assert_session_binding(self.auth, self.sid, self.principal)
        self.bound_resource_identity(request.semantic_model_key)
        if self.truncated:
            from backend.app.powerbi.fabric_iq_contract import fail
            # Same product result guard as native FabricIQ, never Core partial
            # disclosure semantics. Synthetic completeness cannot open Real.
            raise fail('CONTRACT_DRIFT')
        return QueryResult(semantic_model_key=request.semantic_model_key, columns=columns,
            rows=rows, row_count=len(rows), source_mode='mock', truncated=self.truncated,
            request_id=request.request_id)


class FactualMockLLM(MockLLMProvider):
    """Script only language; no plan, DAX, numeric facts or report data draft."""
    def __init__(self):
        super().__init__()
        self.tasks = []

    async def generate(self, request, output_type):
        self.tasks.append(request.task.value)
        if output_type is SemanticFrame:
            report = '生成' in request.messages[-1]['content']
            structured = (SemanticFrame(mode=SemanticInterpretationMode.REPORT,
                output_mode='report', unresolved_mentions=('销售',),
                evidence_spans=(SemanticEvidenceSpan(slot='unresolved',text='销售'),))
                if report else SemanticFrame(mode=SemanticInterpretationMode.DATA,
                    query_shape=QueryShape.SCALAR, measure_mentions=('Total Sales',),
                    evidence_spans=(SemanticEvidenceSpan(slot='measure',text='Total Sales'),
                        SemanticEvidenceSpan(slot='query_shape',text='Total Sales'))))
        elif output_type is SemanticCoverageDecision:
            structured = SemanticCoverageDecision(decision='ACCEPT')
        elif output_type is ReportIntentDraft:
            structured = ReportIntentDraft(report_section_ids=[])
        elif output_type is NaturalAnswerDraft:
            structured = NaturalAnswerDraft(answer=json.loads(request.messages[-1]['content'])['safe_fallback'])
        else:
            raise AssertionError(f'Unexpected synthetic language task: {output_type}')
        return LLMResponse(content='{}', structured=structured, model='mock-llm')


class _FormalBranchView:
    """Test-only callback selector, never passed to Cloud authorization."""
    is_mock = False
    def __init__(self, adapter): self._adapter = adapter
    def __getattr__(self, name): return getattr(self._adapter, name)


class SyntheticFactualTurn(LLMTurnService):
    def __init__(self, *, adapter, repositories, settings, llm, renderer, results):
        assert adapter.is_mock and llm.is_mock
        registry = LLMProviderRegistry()
        registry.register(mock_profile(), llm)
        settings = settings.model_copy(update={'llm_mode':LLMMode.MOCK,
            'powerbi_mode':PowerBIMode.MOCK, 'llm_default_profile':'mock'})
        super().__init__(memory_repo=repositories.memory, snapshot_store=repositories.snapshots,
            llm_provider=None, llm_registry=registry, powerbi_adapter=adapter,
            report_renderer=renderer, report_repository=repositories.reports,
            settings=settings, config=HarnessConfig.from_settings(settings))
        self.powerbi = _FormalBranchView(adapter)
        self.results = results
        assert self._source_mode == 'mock'

    async def execute(self, message, *, conversation_id, request_id, semantic_model_key,
                      report_template_key=None, llm_profile_key=None):
        if llm_profile_key not in (None, 'mock'): raise AuthFailure('AUTH_FORBIDDEN',403)
        snapshot = self.llm_registry.get('mock')
        assert snapshot.provider.is_mock
        result = await self.pipeline.execute(message=message, conversation_id=conversation_id,
            request_id=request_id, semantic_model_key=semantic_model_key,
            report_template_key=report_template_key, runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True, llm_provider_name='mock', llm_profile_key='mock',
            llm_model='mock-llm', llm_provider_protocol='mock', powerbi_provider_name='mock',
            do_execute=self._do_execute, do_conversation=self._do_conversation,
            # The interpreter has the same legacy branch guard. This test-only
            # view selects its existing formal code; profile/protocol and every
            # observable/persisted source remain Mock. It cannot issue HTTP.
            llm_snapshot=LLMProviderSnapshot(snapshot.profile,_FormalBranchView(snapshot.provider)))
        self.results.append(result)
        return result

    def _build_result(self, *args, **kwargs):
        # Frozen callbacks historically hardcode is_mock=False. Correct their
        # test provenance BEFORE TurnPipeline saves any result or snapshot.
        kwargs.update(is_mock=True, source_mode='mock')
        return super()._build_result(*args, **kwargs)

    async def _fail_result(self, *args, **kwargs):
        result = await super()._fail_result(*args, **kwargs)
        result['synthetic_failure_reason'] = kwargs.get('reason')
        return result


@pytest.fixture
def factual_product(tmp_path, monkeypatch):
    settings = config(powerbi_mode='fabric_iq', fabric_test_mode=False)
    identity = FakeIdentity()
    llm = FactualMockLLM()
    renderer = SalesReportRenderer()
    facts = []
    results = []
    original = VerifiedFactSetBuilder.build
    def observe(builder, *args, **kwargs):
        result = original(builder, *args, **kwargs)
        assert result.source_mode == 'mock'
        facts.append(result)
        return result
    monkeypatch.setattr(VerifiedFactSetBuilder, 'build', observe)
    async def runtime(auth):
        engine = create_engine(settings.model_copy(update={
            'persistence_database_path':str(tmp_path/'synthetic.db')}))
        async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
        ws = CloudWorkspaceService(auth, SimpleNamespace(create_product=lambda sid,p:
            FactualSyntheticAdapter(auth,sid,p)), rest_factory=lambda *args:SyntheticREST())
        repos = PrincipalScopedRepositoryFactory(create_session_factory(engine),tmp_path/'reports')
        registry = LLMProviderRegistry()
        registry.register(mock_profile(),llm)
        products = CloudProductServiceFactory(auth,ws,repos,registry,registry,
            synthetic_turn_factory=lambda **kwargs:SyntheticFactualTurn(**kwargs,llm=llm,renderer=renderer,results=results))
        return SimpleNamespace(workspace=ws,products=products,registry=registry,close=engine.dispose)
    app = create_app(settings,identity_client=identity,cloud_runtime_factory=runtime)
    with TestClient(app,base_url=ORIGIN) as client:
        login(client)
        headers = {'Origin':ORIGIN,'X-CSRF-Token':client.get('/auth/session').json()['csrf_token']}
        catalog = client.get('/api/v1/cloud/catalog').json()
        selection = client.post('/api/v1/cloud/selection',headers=headers,json={
            'key':catalog['items'][0]['key'],'expected_generation':0}).json()
        yield client,app,headers,selection,identity,facts,llm,results


def test_full_synthetic_factual_answer_history_and_fixed_report(factual_product):
    c,app,h,s,identity,facts,llm,results = factual_product
    def chat(message, rid, template=None):
        return c.post('/api/v1/cloud/chat',headers=h,json={'message':message,'request_id':rid,
            'expected_generation':s['generation'],'report_template_key':template})
    answer = chat('查询 Total Sales','synthetic-facts')
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body['terminal_state']=='completed' and body['memory_commit'], json.dumps(results[-1],default=str,ensure_ascii=False)
    assert body['is_mock'] and body['source_mode']=='mock'
    assert '1,200.5' in body['answer'] or '1200.5' in body['answer']
    assert facts and all(x.source_mode=='mock' for x in facts)
    assert body['execution_audit'] is None  # public API never exposes raw audit
    assert results[-1]['execution_audit']['verified_fact_set_id'] == facts[-1].fact_set_id
    assert results[-1]['execution_audit']['llm_dax_call_count']==0
    assert c.get('/api/v1/cloud/history/'+s['conversation_id']).json()['items'][0]['answer']==body['answer']
    templates = c.get('/api/v1/cloud/report-templates').json()
    assert any(x['template_key']=='sales_report' and x['selectable'] for x in templates['items']),templates
    report = chat('生成销售分析报表','synthetic-fixed-report','sales_report')
    assert report.status_code==200, report.text
    rb = report.json()
    assert rb['terminal_state']=='completed' and rb['memory_commit'], json.dumps(results[-1],default=str,ensure_ascii=False)
    assert rb['is_mock'] and rb['source_mode']=='mock'
    audit = results[-1]['execution_audit']
    assert audit['query_count']==4 and audit['llm_dax_call_count']==0
    assert len(audit['canonical_query_plans'])==4
    assert rb['tool_sequence'].count('render_report')==1
    rid = rb['report']['report_id']
    view = c.get('/api/v1/cloud/reports/'+rid)
    assert view.status_code==200 and view.content==c.get('/api/v1/cloud/reports/'+rid+'/download').content
    assert '1200.5' in view.text or '1,200.5' in view.text
    assert 'sandbox' in view.headers['content-security-policy']
    assert c.get('/api/v1/cloud/reports').json()['items'][0]['source_mode']=='mock'
    adapter = next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    before = len(adapter.dax)
    replay = chat('生成销售分析报表','synthetic-fixed-report','sales_report').json()
    assert replay['idempotent_replay'] and replay['is_mock']
    assert replay['report']['report_id']==rid and len(adapter.dax)==before
    new = c.post('/api/v1/cloud/new-chat',headers=h,json={'expected_generation':s['generation']}).json()
    restored = c.post('/api/v1/cloud/restore',headers=h,json={'conversation_id':s['conversation_id'],
        'expected_generation':new['generation']})
    assert restored.status_code==200 and restored.json()['conversation_id']==s['conversation_id']
    assert 'dax' not in llm.tasks and 'query_plan' not in llm.tasks and 'report' not in llm.tasks
    async def verify_persistence():
        owner = await app.state.cloud_product_services._repositories.for_session(
            app.state.auth_service,adapter.sid,adapter.principal)
        for request_id in ('synthetic-facts','synthetic-fixed-report'):
            snapshot = await owner.snapshots.get(request_id,RuntimeDataMode.MOCK)
            assert snapshot.is_mock and snapshot.source_mode=='mock'
            assert await owner.snapshots.get(request_id,RuntimeDataMode.REAL) is None
            memory = await owner.memory.get_by_request_id(request_id,RuntimeDataMode.MOCK)
            assert memory.runtime_mode==RuntimeDataMode.MOCK
            assert await owner.memory.get_by_request_id(request_id,RuntimeDataMode.REAL) is None
        artifact = await owner.report_metadata.get(rid)
        assert artifact.source_mode=='mock'
    c.portal.call(verify_persistence)
    # Full factual artifacts remain owner-bound across logout/relogin, and
    # the same schema on another principal never authorizes prior artifacts.
    from uuid import UUID
    c.post('/auth/logout',headers=h)
    identity.claim_changes={'oid':str(UUID(int=4))}
    login(c)
    assert not c.get('/api/v1/cloud/history').json()['items']
    assert c.get('/api/v1/cloud/history/'+s['conversation_id']).status_code==403
    assert c.get('/api/v1/cloud/reports/'+rid).status_code==404
    h['X-CSRF-Token']=c.get('/auth/session').json()['csrf_token']
    c.post('/auth/logout',headers=h)
    identity.claim_changes={}
    login(c)
    assert c.get('/api/v1/cloud/status').json()['selected_model_key'] is None
    assert c.get('/api/v1/cloud/reports/'+rid).status_code==200


@pytest.mark.parametrize('failure',['truncated','revoked','switch'])
def test_synthetic_factual_failure_cannot_commit_or_publish(factual_product,failure):
    c,app,h,s,_,facts,_,_ = factual_product
    adapter = next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    if failure=='truncated': adapter.truncated=True
    else:
        async def invalidate():
            if failure=='revoked': adapter.allowed=False
            else:
                adapter.before_result=None
                await app.state.cloud_workspace_service.new_chat(adapter.sid,adapter.principal,s['generation'])
        adapter.before_result=invalidate
    response=c.post('/api/v1/cloud/chat',headers=h,json={'message':'查询 Total Sales',
        'request_id':'synthetic-failure','expected_generation':s['generation']})
    assert response.status_code in (200,403)
    if response.status_code==200:
        assert not response.json()['memory_commit'] and not response.json()['answer']
    if failure!='switch': assert not facts
    history = c.get('/api/v1/cloud/history/'+s['conversation_id'])
    if history.status_code==200:
        assert all(not item['answer'] and not item['report'] for item in history.json()['items'])
    assert not c.get('/api/v1/cloud/reports').json().get('items')
