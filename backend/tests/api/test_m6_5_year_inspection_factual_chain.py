"""Integer years enter Facts/Memory only after exact existing temporal proof."""
import pytest

from backend.tests.api.test_cloud_factual_e2e import factual_product  # noqa: F401
from backend.tests.unit.test_m6_5_operator_temporal_binding import schema, registry
from backend.app.intent.semantic_interpreter import SemanticFrame, SemanticCoverageDecision
from backend.app.llm.base import LLMResponse
from backend.app.schemas.data_contracts import QueryResult


@pytest.mark.parametrize('proven', [True, False])
def test_formal_year_result_is_inspected_before_facts_and_commit(factual_product, monkeypatch, tmp_path, proven):
    client, app, headers, selected, identity, facts, llm, results = factual_product
    adapter = next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    key = next(iter(app.state.cloud_workspace_service._contexts.values())).selected
    current = schema().model_copy(update={'key': key, 'metadata_source': 'mock'})
    async def runtime_schema(request_key):
        assert request_key == key
        return current
    async def runtime_result(request):
        return QueryResult(semantic_model_key=key, columns=['FiscalYear', 'Amount'],
                           rows=[[2009, 1], [2010, 2]], row_count=2, source_mode='mock')
    monkeypatch.setattr(adapter, 'get_semantic_model_schema', runtime_schema)
    monkeypatch.setattr(adapter, 'execute_dax', runtime_result)
    original_generate = llm.generate
    async def language(request, output_type):
        if output_type is SemanticFrame:
            return LLMResponse(content='{}', model='mock-llm', structured=SemanticFrame.model_validate({
                'mode': 'data', 'query_shape': 'trend', 'analysis_goal': 'TREND',
                'measure_mentions': ['Amount'], 'dimension_mentions': ['FiscalYear'],
                'evidence_spans': [{'slot': 'measure', 'text': 'Amount'},
                                   {'slot': 'dimension', 'text': 'FiscalYear'},
                                   {'slot': 'query_shape', 'text': '趋势'}]}))
        if output_type is SemanticCoverageDecision:
            return LLMResponse(content='{}', model='mock-llm', structured=SemanticCoverageDecision(decision='ACCEPT'))
        return await original_generate(request, output_type)
    monkeypatch.setattr(llm, 'generate', language)
    config = tmp_path / 'operator.json'
    import json
    config.write_text(json.dumps(registry(current) if proven else {'version': 2, 'overrides': []}), encoding='utf-8')
    original_prepare = app.state.cloud_product_services.prepare
    async def prepare(*args, **kwargs):
        prepared = await original_prepare(*args, **kwargs)
        prepared.turn_service.settings = prepared.turn_service.settings.model_copy(update={
            'powerbi_semantic_override_path': str(config)})
        return prepared
    monkeypatch.setattr(app.state.cloud_product_services, 'prepare', prepare)
    response = client.post('/api/v1/cloud/chat', headers=headers, json={
        'message': '按 FiscalYear 查看 Amount 趋势', 'request_id': 'year-authority',
        'expected_generation': selected['generation']})
    assert response.status_code == 200
    body = response.json()
    if proven:
        assert body['terminal_state'] == 'completed', results[-1].get('synthetic_failure_reason')
        assert body['memory_commit'] and facts
        assert results[-1]['execution_audit']['result_semantic_inspection']['passed']
    else:
        assert body['terminal_state'] != 'completed'
        assert not body['memory_commit'] and not facts
