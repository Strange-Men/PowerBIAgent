"""Exact schema lineage at the IQ boundary; no Core matching changes."""
import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_normalization import normalize_query, normalize_schema
from backend.app.schemas.data_contracts import DAXRequest
from backend.tests.unit.test_fabric_iq_adapter import MODEL, harness, result, schema  # noqa: F401


def bound_schema(tables):
    raw = schema()
    raw['schema']['Tables'] = tables
    return normalize_schema(raw, MODEL, 'fixture', 1)


def table(name, columns=(), measures=()):
    return {'Name': name, 'Columns': [{'Name': c, 'Type': 'String'} for c in columns],
            'Measures': [{'Name': m, 'Type': 'Int64'} for m in measures]}


def normalize(labels, tables):
    raw = result([['A'] * len(labels)])
    raw['executionResult']['tables'][0]['columns'] = [
        {'name': label, 'type': 'String'} for label in labels]
    return normalize_query(raw, MODEL, DAXRequest(semantic_model_key='fixture', dax='EVALUATE x'),
                           schema=bound_schema(tables))


@pytest.mark.parametrize('label,tables,expected', [
    ('FactSales Region', [table('FactSales', ['Region'])], 'Region'),
    ('DimRegion Region', [table('FactSales', ['Region']), table('DimRegion', ['Region'])], 'Region'),
    ('Region', [table('FactSales', ['Region'])], 'Region'),
    ('Total Sales', [table('FactSales', measures=['Total Sales'])], 'Total Sales'),
])
def test_exact_schema_lineage_passes(label, tables, expected):
    assert normalize([label], tables).columns == [expected]


@pytest.mark.parametrize('label', ['Unknown Region', 'Sales Region', 'Region suffix',
    'FactSalesRegion', 'factsales Region', 'FactSales region', 'FactSales  Region',
    ' FactSales Region', 'FactSales Region ', 'FactSales\tRegion',
    'FactSales Region\n', "FactSales[Region]", '[Region]', '__member',
    'FactSales Region; DROP TABLE FactSales', 'FactSales Total Sales'])
def test_unknown_partial_case_spacing_and_invented_measure_aliases_fail(label):
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize([label], [table('FactSales', ['Region'], ['Total Sales'])])


@pytest.mark.parametrize('label,tables', [
    ('A B C', [table('A B', ['C']), table('A', ['B C'])]),
    ('FactSales Region', [table('FactSales', ['Region']), table('Other', ['FactSales Region'])]),
    ('Region', [table('FactSales', ['Region']), table('DimRegion', ['Region'])]),
    ('Region', [table('FactSales', ['Region'], ['Region'])]),
    ('Total Sales', [table('A', measures=['Total Sales']), table('B', measures=['Total Sales'])]),
])
def test_multiple_schema_candidates_fail(label, tables):
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize([label], tables)


def test_normalized_output_collision_fails():
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize(['FactSales Region', 'DimRegion Region'],
                  [table('FactSales', ['Region']), table('DimRegion', ['Region'])])


def test_foreign_schema_cannot_authorize_a_result():
    verified = bound_schema([table('FactSales', ['Region'])])
    verified.key = 'another-model'
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize_query(result(), MODEL, DAXRequest(semantic_model_key='fixture', dax='EVALUATE x'),
                        schema=verified)


@pytest.mark.parametrize('target', ['table', 'column', 'measure'])
def test_hidden_schema_objects_cannot_authorize_a_result(target):
    verified = bound_schema([table('FactSales', ['Region'], ['Total Sales'])])
    obj = verified.tables[0]
    if target == 'column': obj = obj.columns[0]
    if target == 'measure': obj = obj.measures[0]
    obj.is_hidden = True
    raw = result([['A']])
    raw['executionResult']['tables'][0]['columns'] = [
        {'name': 'Total Sales' if target == 'measure' else 'FactSales Region', 'type': 'String'}]
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        normalize_query(raw, MODEL, DAXRequest(semantic_model_key='fixture', dax='EVALUATE x'),
                        schema=verified)


def test_schema_normalized_entity_passes_unchanged_inspection_and_facts():
    from backend.app.facts.inspection import ResultSemanticInspectionGate
    from backend.app.facts.verified import VerifiedFactSetBuilder
    from backend.app.powerbi.fabric_iq_normalization import IQInlineEnvelope
    from backend.app.schemas.data_contracts import CanonicalQueryPlan
    raw = result([['A'], ['B']])
    raw['executionResult']['tables'][0]['columns'] = [{'name': 'FactSales Region', 'type': 'String'}]
    request = DAXRequest(semantic_model_key='fixture', dax='EVALUATE x')
    query = normalize_query(raw, MODEL, request, envelope=IQInlineEnvelope.for_request(request),
                            schema=bound_schema([table('FactSales', ['Region'])]))
    plan = CanonicalQueryPlan(normalized_question='synthetic entities', semantic_model_key='fixture',
        query_shape='entity_list', dimensions=['Region'], dimension_tables={'Region': 'FactSales'})
    assert ResultSemanticInspectionGate().inspect(plan, query, dax_semantic_verified=True).passed
    facts = VerifiedFactSetBuilder().build(plan, query)
    assert facts.facts and facts.source_mode == 'real' and not facts.truncated


@pytest.mark.asyncio
async def test_public_execution_uses_current_bound_schema_and_rejects_internal_alias(harness):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap('fixture')
    transport.query = result([['A']])
    transport.query['executionResult']['tables'][0]['columns'] = [
        {'name': 'Facts Category', 'type': 'String'}]
    request = DAXRequest(semantic_model_key=ref.server_model_key, dax='EVALUATE x')
    assert (await adapter.execute_dax(request)).columns == ['Category']
    transport.query['executionResult']['tables'][0]['columns'][0]['name'] = '__member'
    with pytest.raises(PowerBIAdapterError, match='^CONTRACT_DRIFT$'):
        await adapter.execute_dax(request)
