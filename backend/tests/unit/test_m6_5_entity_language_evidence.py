"""Entity list language must identify its field before runtime grounding."""
import pytest
from backend.app.intent.semantic_interpreter import (
    SemanticFrame, LLMSemanticInterpreter, SemanticInterpretationError,
)


def frame(**updates):
    return SemanticFrame.model_validate(dict(mode='data', query_shape='entity_list', **updates))


def test_entity_list_missing_dimension_is_bounded_repair_failure():
    with pytest.raises(SemanticInterpretationError, match='entity_list_dimension_mention_required'):
        LLMSemanticInterpreter._validate_structure(frame())


def test_entity_list_unresolved_language_may_clarify_without_inventing_field():
    LLMSemanticInterpreter._validate_structure(frame(unresolved_mentions=['销售年份']))


def test_entity_list_literal_is_still_required_to_be_verbatim():
    valid = frame(dimension_mentions=['Fiscal Period'], evidence_spans=[
        {'slot':'dimension','text':'Fiscal Period'}, {'slot':'query_shape','text':'list'}])
    LLMSemanticInterpreter._validate_structure(valid)
    LLMSemanticInterpreter._validate_evidence(valid, 'list Fiscal Period')
    with pytest.raises(SemanticInterpretationError):
        LLMSemanticInterpreter._validate_evidence(valid, 'list another field')


def test_entity_list_repair_never_supplies_canonical_object():
    instruction = LLMSemanticInterpreter._repair_instruction(
        SemanticInterpretationError('entity_list_dimension_mention_required'))
    assert 'dimension_mentions' in instruction
    assert 'verbatim' in instruction
    assert 'Fiscal Period' not in instruction
