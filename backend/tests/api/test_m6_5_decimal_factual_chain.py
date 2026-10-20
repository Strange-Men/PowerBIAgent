"""Decimal compatibility through the unchanged formal product factual chain."""
from decimal import Decimal
import pytest

from backend.tests.api.test_cloud_factual_e2e import factual_product  # noqa: F401


def test_decimal_query_result_reaches_existing_facts_and_memory(factual_product, monkeypatch):
    client, app, headers, selected, identity, facts, llm, results = factual_product
    adapter = next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    original = adapter.execute_dax
    async def decimal_result(request):
        result = await original(request)
        return result.model_copy(update={'rows': [[Decimal('1200.5000')]]})
    monkeypatch.setattr(adapter, 'execute_dax', decimal_result)
    response = client.post('/api/v1/cloud/chat', headers=headers, json={
        'message':'查询 Total Sales', 'request_id':'decimal-formal',
        'expected_generation':selected['generation']})
    assert response.status_code == 200
    if response.json()['terminal_state'] == 'response_failed':
        assert not response.json()['memory_commit']
        assert any('answer_metric_non_numeric' in e
            for e in results[-1]['execution_audit']['answer_validation_errors'])
    assert response.json()['terminal_state'] == 'completed', {
        'terminal_state':response.json()['terminal_state'],
        'memory_commit':response.json()['memory_commit'],
        'errors':results[-1]['execution_audit'].get('answer_validation_errors'),
    }
    assert response.json()['memory_commit']
    assert facts and any(type(f.value) is Decimal for f in facts[-1].facts)


@pytest.mark.parametrize('value', ['¥10', '10,000', 'NaN', 'text'])
def test_invalid_numeric_wire_never_reaches_facts_or_memory(factual_product, monkeypatch, value):
    from backend.tests.unit.test_m6_5_typed_numeric_string import normalize, bound_schema
    client, app, headers, selected, identity, facts, llm, results = factual_product
    adapter = next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    async def rejected_result(request):
        return normalize(value, model=bound_schema())
    monkeypatch.setattr(adapter, 'execute_dax', rejected_result)
    response = client.post('/api/v1/cloud/chat', headers=headers, json={
        'message':'查询 Total Sales', 'request_id':'invalid-decimal-formal',
        'expected_generation':selected['generation']})
    assert response.status_code == 200
    assert response.json()['terminal_state'] != 'completed'
    assert not response.json()['memory_commit'] and not facts


def test_decimal_report_reaches_existing_verified_assembly_renderer_and_memory(factual_product, monkeypatch):
    client, app, headers, selected, identity, facts, llm, results = factual_product
    adapter = next(iter(app.state.cloud_workspace_service._contexts.values())).adapter
    original = adapter.execute_dax
    async def decimal_result(request):
        result = await original(request)
        rows = [[Decimal(str(v)) if type(v) in {int, float} else v for v in row]
                for row in result.rows]
        return result.model_copy(update={'rows': rows})
    monkeypatch.setattr(adapter, 'execute_dax', decimal_result)
    response = client.post('/api/v1/cloud/chat', headers=headers, json={
        'message': '生成销售分析报表', 'request_id': 'decimal-formal-report',
        'expected_generation': selected['generation'], 'report_template_key': 'sales_report'})
    assert response.status_code == 200
    body = response.json()
    assert body['terminal_state'] == 'completed' and body['memory_commit'], {
        'terminal_state': body['terminal_state'], 'error_type': body.get('error_type')}
    assert facts and any(type(f.value) is Decimal for fs in facts for f in fs.facts)
    assert body['tool_sequence'].count('render_report') == 1
    report_id = body['report']['report_id']
    rendered = client.get('/api/v1/cloud/reports/' + report_id)
    assert rendered.status_code == 200
    assert rendered.content == client.get('/api/v1/cloud/reports/' + report_id + '/download').content
    assert '1200.5' in rendered.text or '1,200.5' in rendered.text
