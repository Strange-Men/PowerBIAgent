"""Explicit table qualification is user language, never runtime object inference."""
import pytest

from backend.app.intent.semantic_interpreter import (
    LLMSemanticInterpreter, SemanticFrame, SemanticInterpretationError,
)


def frame(mention):
    return SemanticFrame.model_validate({
        'mode': 'data', 'query_shape': 'grouped',
        'dimension_mentions': [mention], 'measure_mentions': ['Revenue'],
        'evidence_spans': [{'slot': 'dimension', 'text': mention},
                           {'slot': 'measure', 'text': 'Revenue'},
                           {'slot': 'query_shape', 'text': 'by'}],
    })


@pytest.mark.parametrize('qualified', ['Events[Zone]', "'Event Facts'[Zone]", "'交易'[区域]"])
def test_qualified_dimension_cannot_be_reduced_to_ambiguous_leaf(qualified):
    leaf=qualified.rsplit('[',1)[1][:-1]
    with pytest.raises(SemanticInterpretationError) as caught:
        LLMSemanticInterpreter._validate_evidence(frame(leaf), 'Revenue by '+qualified)
    assert caught.value.code=='semantic_slot_evidence_missing'
    assert caught.value.repair_detail=={'slot':'dimension','text':qualified}


@pytest.mark.parametrize('qualified', ['Events[Zone]', "'Event Facts'[Zone]", "'交易'[区域]"])
def test_complete_current_qualification_is_preserved_without_binding(qualified):
    LLMSemanticInterpreter._validate_evidence(frame(qualified), 'Revenue by '+qualified)


def test_unqualified_dimension_and_unrelated_qualified_field_keep_existing_contract():
    LLMSemanticInterpreter._validate_evidence(frame('Zone'), 'Revenue by Zone')
    LLMSemanticInterpreter._validate_evidence(frame('Zone'), 'Revenue by Zone, mention Events[Other]')


def test_chinese_grouping_prefix_is_not_part_of_ascii_table_qualifier():
    with pytest.raises(SemanticInterpretationError) as caught:
        LLMSemanticInterpreter._validate_evidence(frame('Zone'), '按Events[Zone] by Revenue')
    assert caught.value.repair_detail['text']=='Events[Zone]'


def test_qualification_repair_requires_verbatim_text_and_no_canonical_choice():
    text=LLMSemanticInterpreter._repair_instruction(SemanticInterpretationError(
        'semantic_slot_evidence_missing', repair_detail={'slot':'dimension','text':'Events[Zone]'}))
    assert 'Events[Zone]' in text
    assert 'verbatim' in text
