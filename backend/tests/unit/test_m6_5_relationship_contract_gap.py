"""Observed V1 relationship structure is insufficient; never infer cardinality."""
import pytest

from backend.app.powerbi.fabric_iq_normalization import normalize_schema
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.schemas.data_contracts import QueryPlan, StructuredFilter
from backend.tests.unit.test_fabric_iq_adapter import MODEL


def observed_schema():
    # Structural names are synthetic; field set and string grammar match fresh
    # 2026-10-15 approved-workspace GetSemanticModelSchema runtime evidence.
    return {'semanticModel':{'ArtifactId':MODEL,'Name':'Synthetic relationship gap'},'schema':{
        'Tables':[
            {'Name':'Dimension','Columns':[{'Name':'Key','Type':'Text'}, {'Name':'Label','Type':'Text'}]},
            {'Name':'Facts','Columns':[{'Name':'Key','Type':'Text'}, {'Name':'When','Type':'DateTime'}],
                'Measures':[{'Name':'Amount','Type':'Decimal'}]},
        ],'ActiveRelationships':[{'PK':"'Dimension'[Key]",'FK':"'Facts'[Key]",
            'UnidirectionalFilter':"'Dimension' filters 'Facts'"}]}}


@pytest.mark.parametrize('relations', [None, [], 'observed'])
def test_missing_or_unknown_cardinality_cannot_grant_canonical_edge(relations):
    raw=observed_schema()
    if relations is None:
        raw['schema'].pop('ActiveRelationships')
    elif relations != 'observed':
        raw['schema']['ActiveRelationships']=relations
    schema=normalize_schema(raw,MODEL,'bound-model',1)
    assert schema.relationships==[]
    assert schema.provider_metadata['relationship_mapping']=='NOT_VERIFIED'
    plan=QueryPlan(normalized_question='Synthetic cross-table filter',semantic_model_key=schema.key,
        measures=['Amount'],filters=[StructuredFilter(field='Label',value='explicit-member')])
    validation=ValidationService(allowed_semantic_models=[schema.key]).validate_query_plan(
        plan,schema,enforce_semantic_grounding=True)
    assert not validation.valid and any('query_plan_table_unrelated' in e for e in validation.errors)


def test_observed_pk_fk_direction_does_not_create_temporal_one_side_authority():
    from backend.app.query_plan.model_semantic_context import ModelSemanticContextBuilder
    schema=normalize_schema(observed_schema(),MODEL,'bound-model',1)
    context=ModelSemanticContextBuilder().build(schema)
    assert context.relationships==()
    assert not any(e.kind=='active_relationship_key' for e in context.temporal_candidates)
