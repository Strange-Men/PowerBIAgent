"""Safe runtime failures retain codes without logging arbitrary exception data."""
import pytest
from fastapi import HTTPException
from backend.app.api.cloud_routes import product_call
from backend.app.llm.base import LLMServiceError
from backend.app.api.cloud_routes import safe_call
from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.application.cloud_operation import cloud_stage


@pytest.mark.asyncio
@pytest.mark.parametrize('error,code', [(LLMServiceError('SENSITIVE_SENTINEL'),'LLM_SERVICE_UNAVAILABLE'),
                                        (RuntimeError('SENSITIVE_SENTINEL'),'INTERNAL_FAILURE')])
async def test_product_failure_is_typed_and_trace_is_bounded(error,code,caplog):
    async def unavailable(): raise error
    with pytest.raises(HTTPException) as caught:
        await product_call(unavailable())
    assert caught.value.detail['failure']['code'] == code
    assert 'SENSITIVE_SENTINEL' not in caplog.text
    traces=[record.cloud_failure for record in caplog.records if hasattr(record,'cloud_failure')]
    assert len(traces)==1
    assert set(traces[0])=={'request_id','operation','stage','failure_code','retryable','provider','http_status_category'}
    assert traces[0]['failure_code']==code


@pytest.mark.asyncio
@pytest.mark.parametrize('code',['RESOURCE_NOT_ACCESSIBLE','AUTH_FORBIDDEN','MODEL_RESOLUTION_FAILED',
    'SCHEMA_UNAVAILABLE','RATE_LIMITED','QUERY_TIMEOUT','UPSTREAM_UNAVAILABLE',
    'LLM_SERVICE_UNAVAILABLE','PERSISTENCE_UNAVAILABLE','INTERNAL_FAILURE'])
async def test_failure_codes_and_operation_are_preserved(code,caplog):
    @cloud_stage('resource_verify','microsoft_rest')
    async def unavailable(): raise fail(code)
    with pytest.raises(HTTPException) as caught:
        await safe_call(unavailable(),context='history')
    assert caught.value.detail['failure']['code']==code
    trace=next(r.cloud_failure for r in caplog.records if hasattr(r,'cloud_failure'))
    assert trace['operation']=='history' and trace['stage']=='resource_verify'


@pytest.mark.asyncio
async def test_wrapped_provider_origin_is_not_relabelled_persistence(caplog):
    from backend.app.harness.errors import ToolExecutionError
    @cloud_stage('iq_schema','fabric_iq')
    async def schema(): raise fail('UPSTREAM_UNAVAILABLE')
    @cloud_stage('persistence','persistence')
    async def prepare():
        try: await schema()
        except Exception as error: raise ToolExecutionError('private') from error
    with pytest.raises(HTTPException): await safe_call(prepare(),context='chat')
    trace=next(r.cloud_failure for r in caplog.records if hasattr(r,'cloud_failure'))
    assert trace['stage']=='iq_schema' and trace['provider']=='fabric_iq'
