"""P0 audit using synthetic markers and in-process HTTP only.

These tests document disclosure paths and the closed native gate. They do not
establish enterprise authorization or certify historical production traffic.
"""
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.answer.context import AnswerContext
from backend.app.answer.prompt import build_answer_messages
from backend.app.harness.models import HarnessConfig
from backend.app.harness.observability.llm_observer import LLMCallCollector, ObservedLLMProvider
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.llm.base import LLMRequest
from backend.app.llm.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.main import create_app
from backend.tests.api.test_auth_security import config, FakeIdentity, login, ORIGIN
from backend.tests.unit.test_multi_llm_provider import _profile, _response, _StructuredResult


@pytest.mark.asyncio
@pytest.mark.parametrize('profile_key', ['deepseek', 'kimi-k2.6'])
async def test_synthetic_answer_cells_reach_provider_wire_so_real_cells_require_authorization(profile_key):
    """Bounded context is data minimization, not anonymization or consent."""
    context = AnswerContext.build('SYNTHETIC_QUESTION', result_id='synthetic-result',
        semantic_model_key='synthetic-model', columns=['SYNTHETIC_COLUMN'],
        rows=[['SYNTHETIC_CELL_MARKER']], row_count=1, truncated=False, source_mode='mock')
    seen = []
    def receive(request):
        payload = json.loads(request.content)
        messages = json.dumps(payload['messages'])
        seen.append({'cell_forwarded':'SYNTHETIC_CELL_MARKER' in messages,
                     'column_forwarded':'SYNTHETIC_COLUMN' in messages})
        return _response({'status':'synthetic', 'value':1}, model='synthetic-model')
    collector = LLMCallCollector()
    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        provider = OpenAICompatibleLLMProvider(profile=_profile(profile_key, 'synthetic-model'),
            api_key='SYNTHETIC_LLM_KEY', client=client)
        await ObservedLLMProvider(provider, collector).generate(
            LLMRequest(messages=build_answer_messages(context)), _StructuredResult)
    assert seen == [{'cell_forwarded':True, 'column_forwarded':True}]
    # Existing observer stores counts/categories, not prompt/cell text.
    assert 'SYNTHETIC_CELL_MARKER' not in json.dumps(collector.summary().to_dict())


def test_generic_secret_redaction_does_not_certify_business_data_minimization():
    trace = TraceRecorder(HarnessConfig())
    trace.record('synthetic-audit', data_summary={'rows':[['SYNTHETIC_BUSINESS_MARKER']],
        'access_token':'synthetic-sensitive-token'})
    exported = trace.to_json()
    assert 'synthetic-sensitive-token' not in exported
    assert 'SYNTHETIC_BUSINESS_MARKER' in exported
    # No export is written. A Cloud trace must never pass real rows to this API.


def test_native_cloud_business_paths_cannot_disclose_to_configured_external_providers(monkeypatch):
    generate = AsyncMock(side_effect=AssertionError('external generation must not run'))
    monkeypatch.setattr(OpenAICompatibleLLMProvider, 'generate', generate)
    settings = config(powerbi_mode='fabric_iq', llm_mode='openai_compatible',
        deepseek_api_key='NOT_A_REAL_SECRET_DEEPSEEK', kimi_api_key='NOT_A_REAL_SECRET_KIMI')
    app = create_app(settings, identity_client=FakeIdentity())
    with TestClient(app, base_url=ORIGIN) as client:
        login(client)
        headers = {'Origin':ORIGIN, 'X-CSRF-Token':client.get('/auth/session').json()['csrf_token']}
        for path in ('/api/v1/chat', '/api/v1/cloud/chat'):
            assert client.post(path, json={'message':'SYNTHETIC_BUSINESS_MARKER'}, headers=headers).status_code == 403
        for path in ('/api/reports', '/api/v1/conversations', '/api/reports/synthetic-report/download'):
            assert client.get(path).status_code == 403
        assert app.state.turn_service is None and app.state._persistence_engine is None
        assert app.state.cloud_product_services is not None
        assert app.state.cloud_product_services._repositories._engine is None
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_execution_gate_or_client_source_cannot_grant_enterprise_retention(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from backend.app.application.cloud_product_runtime import DeferredCloudRepositories,require_cloud_business_data
    from backend.app.auth.models import AuthFailure
    from backend.app.memory.models import RuntimeDataMode
    from backend.app.persistence import database
    engine=Mock(side_effect=AssertionError('enterprise persistence must not open'))
    monkeypatch.setattr(database,'create_engine',engine)
    workspace=SimpleNamespace(require_business_access=lambda *args:None,
        data_mode=lambda *args:RuntimeDataMode.REAL)
    with pytest.raises(AuthFailure): require_cloud_business_data(workspace,'synthetic',object())
    repositories=DeferredCloudRepositories(object(),workspace,config(powerbi_mode='fabric_iq',persistence_backend='sqlite'))
    with pytest.raises(AuthFailure): await repositories.for_session(object(),'synthetic',object())
    engine.assert_not_called()


def test_client_disclosure_synthetic_and_retention_flags_are_never_grants():
    from backend.app.api.cloud_routes import CloudChatRequest,GenerationRequest
    from pydantic import ValidationError
    for field in ('synthetic_only','external_llm_approved','retention_approved','source_mode'):
        with pytest.raises(ValidationError):
            CloudChatRequest.model_validate({'message':'SYNTHETIC','request_id':'safe',
                'expected_generation':0,field:True})
        with pytest.raises(ValidationError): GenerationRequest.model_validate({'expected_generation':0,field:True})
