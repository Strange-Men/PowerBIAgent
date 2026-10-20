"""Failure-first targeted proof requirements; raw IQ schema must be runtime-probed.

Candidate dictionaries below are internal structural fixtures, not fabricated
ValueSearch wire payloads or Real evidence. Full enumeration remains unchanged.
"""
import pytest

from backend.app.powerbi import fabric_iq_normalization as normalization
from backend.app.query_plan.grounding import GroundingStatus, MemberGrounder
from backend.app.query_plan.semantic_catalog import CatalogObject, SemanticObjectType
from backend.app.schemas.data_contracts import (
    ColumnSchema, SemanticModelSchema, TableSchema, QueryPlan, StructuredFilter,
)
from backend.app.harness.validators.validation_service import ValidationService


def schema():
    return SemanticModelSchema(key='bound-model',name='Synthetic proof model',metadata_source='fabric_iq',tables=[
        TableSchema(name='Facts',columns=[ColumnSchema(name='Country',data_type='string'),
            ColumnSchema(name='StockCode',data_type='string')]),
    ])


def proof(literal, candidates, column='Country'):
    # Missing function is the RED requirement; implementation waits for actual
    # runtime ValueSearch shape and identity/completeness observations.
    return normalization.verify_explicit_member_candidates(schema(), 'Facts', column, literal, candidates)


def field(column='Country'):
    return CatalogObject(object_id=f'field:Facts:{column}',canonical_name=column,
        table_name='Facts',data_type='string',object_type=SemanticObjectType.FIELD)


@pytest.mark.parametrize('literal,column', [('France','Country'),('Germany','Country'),
    ('United Kingdom','Country'),('01234X','StockCode')])
def test_explicit_literal_proof_requires_no_complete_member_enumeration(literal,column):
    candidates=[{'table':'Facts','column':column,'value':literal}]
    result=proof(literal,candidates,column)
    grounded=MemberGrounder.resolve(field(column),literal,result)
    assert grounded.status==GroundingStatus.RESOLVED and grounded.canonical_value==literal
    assert result.values==[literal]
    assert result.truncated  # Positive existence proof never claims whole vocabulary.


@pytest.mark.parametrize('literal,candidates', [('Atlantis',[{'table':'Facts','column':'Country','value':'France'}]),
    ('Fran',[{'table':'Facts','column':'Country','value':'France'}]),
    ('france',[{'table':'Facts','column':'Country','value':'France'}])])
def test_unknown_fuzzy_or_nonexact_candidate_cannot_become_member(literal,candidates):
    result=proof(literal,candidates)
    assert result.values==[]
    assert MemberGrounder.resolve(field(),literal,result).status==GroundingStatus.UNRESOLVED


def test_ambiguous_exact_candidates_cannot_silently_choose_first():
    candidates=[{'table':'Facts','column':'Country','value':'France'}]*2
    result=proof('France',candidates)
    assert MemberGrounder.resolve(field(),'France',result).status==GroundingStatus.AMBIGUOUS


def test_candidate_from_other_column_is_not_proof():
    result=proof('France',[{'table':'Facts','column':'StockCode','value':'France'}])
    assert result.values==[]


def test_missing_iq_relationships_reject_cross_table_plan_before_dax():
    from backend.app.schemas.data_contracts import MeasureSchema
    model=schema()
    model.tables[0].measures=[MeasureSchema(name='Count')]
    model.tables.append(TableSchema(name='CountryDim',columns=[ColumnSchema(name='Label',data_type='string')]))
    plan=QueryPlan(normalized_question='Synthetic cross-table filter',semantic_model_key=model.key,measures=['Count'],
        filters=[StructuredFilter(field='Label',value='France')])
    validation=ValidationService(allowed_semantic_models=[model.key]).validate_query_plan(
        plan,model,enforce_semantic_grounding=True)
    assert not validation.valid and any('query_plan_table_unrelated' in e for e in validation.errors)
