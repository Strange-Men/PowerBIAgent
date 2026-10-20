"""Existing operator registry binds exact runtime objects, never client claims."""
import pytest
from pydantic import ValidationError

from backend.app.api.cloud_routes import CloudChatRequest
from backend.app.query_plan.completeness import CanonicalShapeCompletenessGate, CanonicalShapeCompletenessError
from backend.app.query_plan.grounding import SemanticGroundingService, GroundingStatus
from backend.app.query_plan.model_override import resolve_model_override
from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder, GlossaryCatalogError
from backend.app.schemas.data_contracts import (
    SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema, CanonicalQueryPlan, QueryShape,
)
from backend.tests.unit.test_fabric_iq_adapter import harness, WORKSPACE, MODEL  # noqa: F401


def schema():
    return SemanticModelSchema(name='Synthetic',key='operator-model',metadata_source='fabric_iq',
        session_generation=7,tables=[TableSchema(name='Events',columns=[
            ColumnSchema(name='Day',data_type='DateTime'),
            ColumnSchema(name='OtherDay',data_type='DateTime'),
            ColumnSchema(name='FiscalYear',data_type='Integer'),
            ColumnSchema(name='Period',data_type='DateTime'),
        ],measures=[MeasureSchema(name='Amount',data_type='Decimal')])])


def registry(current):
    ctx=ModelSemanticContextBuilder().build(current)
    return {'version':2,'profiles':{},'overrides':[{
        'semantic_model_key':ctx.semantic_model_key,'runtime_identity':ctx.runtime_identity,
        'schema_fingerprint':ctx.schema_fingerprint,'objects':{
            'field:Events:Day':{'temporal_role':'default'},
            'field:Events:FiscalYear':{'temporal_grouping':{
                'grain':'year','date_table_name':'Events','date_field':'Day'}},
            'field:Events:Period':{'temporal_grouping':{
                'grain':'month','date_table_name':'Events','date_field':'Day'}},
        }}]}


def build(current, config):
    ctx=ModelSemanticContextBuilder().build(current)
    return SemanticCatalogBuilder().build_from_context(ctx,resolve_model_override(ctx,config))


def trend_plan(field):
    return CanonicalQueryPlan(normalized_question='synthetic trend',semantic_model_key='operator-model',
        query_shape=QueryShape.TREND,measures=['Amount'],dimensions=[field],dimension_order='asc',
        dimension_tables={field:'Events'})


def test_exact_operator_binding_uses_existing_year_month_and_day_roles():
    current=schema(); catalog=build(current,registry(current))
    assert catalog.get('field:Events:FiscalYear').temporal_grouping.grain=='year'
    assert catalog.get('field:Events:Period').temporal_grouping.grain=='month'
    date=SemanticGroundingService(catalog)._resolve_date_field('今年')
    assert date.status is GroundingStatus.RESOLVED and date.canonical_object.canonical_name=='Day'
    for field in ('FiscalYear','Period'):
        assert CanonicalShapeCompletenessGate().validate(trend_plan(field),catalog=catalog).complete


@pytest.mark.parametrize('mutation',['model','fingerprint','table','column','date_table','date_column'])
def test_invalid_operator_binding_never_grants_executable_trend(mutation):
    current=schema(); config=registry(current); binding=config['overrides'][0]
    if mutation=='model':
        current=current.model_copy(update={'key':'other'})
    elif mutation=='fingerprint': binding['schema_fingerprint']='0'*64
    elif mutation in {'table','column'}:
        obj=binding['objects'].pop('field:Events:Period')
        binding['objects']['field:Wrong:Period' if mutation=='table' else 'field:Events:Wrong']=obj
    else:
        binding['objects']['field:Events:Period']['temporal_grouping'][
            'date_table_name' if mutation=='date_table' else 'date_field']='Wrong'
    with pytest.raises((GlossaryCatalogError,CanonicalShapeCompletenessError)):
        catalog=build(current,config)
        CanonicalShapeCompletenessGate().validate(trend_plan('Period'),catalog=catalog)


def test_schema_drift_and_missing_registry_stay_closed():
    current=schema(); config=registry(current)
    changed=current.model_copy(deep=True); changed.tables[0].columns[0].description='changed'
    with pytest.raises(GlossaryCatalogError,match='fingerprint'):
        build(changed,config)
    catalog=build(current,{'version':2,'overrides':[]})
    with pytest.raises(CanonicalShapeCompletenessError):
        CanonicalShapeCompletenessGate().validate(trend_plan('FiscalYear'),catalog=catalog)


@pytest.mark.parametrize('conflict',['grain','source'])
def test_explicit_runtime_projection_cannot_be_overridden(conflict):
    current=schema()
    current.tables[0].columns[-1].expression='DATE(YEAR([Day]),MONTH([Day]),1)'
    config=registry(current)
    grouping=config['overrides'][0]['objects']['field:Events:Period']['temporal_grouping']
    grouping['grain' if conflict=='grain' else 'date_field']='year' if conflict=='grain' else 'OtherDay'
    with pytest.raises(GlossaryCatalogError,match='override_temporal_authority_conflict'):
        build(current,config)


def test_matching_runtime_projection_is_preserved():
    current=schema();current.tables[0].columns[-1].expression='DATE(YEAR([Day]),MONTH([Day]),1)'
    catalog=build(current,registry(current))
    assert catalog.get('field:Events:Period').temporal_grouping.grain=='month'


def test_operator_year_binding_does_not_rewrite_result_axis_or_bypass_inspection():
    from backend.app.facts.inspection import ResultSemanticInspectionGate, ResultSemanticInspectionError
    from backend.app.schemas.data_contracts import QueryResult
    current=schema();catalog=build(current,registry(current));plan=trend_plan('FiscalYear')
    assert CanonicalShapeCompletenessGate().validate(plan,catalog=catalog).complete
    result=QueryResult(semantic_model_key=current.key,columns=['FiscalYear','Amount'],
        rows=[[2024,10],[2025,20]],row_count=2,source_mode='real')
    with pytest.raises(ResultSemanticInspectionError,match='result_trend_temporal_value_invalid'):
        ResultSemanticInspectionGate().inspect(plan,result)
    assert result.rows==[[2024,10],[2025,20]]


@pytest.mark.parametrize('claim',['temporal_grouping','schema','model_override','temporal_grain'])
def test_client_temporal_metadata_is_rejected_before_product_execution(claim):
    with pytest.raises(ValidationError):
        CloudChatRequest.model_validate({'message':'trend','request_id':'forged','expected_generation':1,claim:{'grain':'year'}})


@pytest.mark.asyncio
async def test_wrong_workspace_cannot_establish_operator_model_identity(harness):
    _,_,transport,adapter=harness
    from uuid import UUID
    from backend.app.powerbi.base import PowerBIAdapterError
    with pytest.raises(PowerBIAdapterError):
        await adapter.bind_catalog_model(str(UUID(int=987)),MODEL)
    assert not any(name=='ExecuteQuery' for name,_ in transport.calls)
    assert adapter.binding_count==0
