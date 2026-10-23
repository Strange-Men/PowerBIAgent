"""Coverage rejection retains the exact omitted language for bounded repair."""
import pytest

from backend.app.intent.semantic_interpreter import (
    LLMSemanticInterpreter, SemanticInterpretationError,
    SemanticFrame, SemanticCoverageDecision, UNDERSTANDING_SYSTEM_PROMPT,
)
from backend.tests.unit.test_m5_10_6_understanding_failure_corpus import _FrameProvider


def test_coverage_repair_carries_only_exact_missing_language():
    instruction = LLMSemanticInterpreter._repair_instruction(
        SemanticInterpretationError('semantic_coverage_incomplete',
                                    repair_detail={'missing_span': '2011年1月至6月'}))
    assert '2011年1月至6月' in instruction
    assert 'verbatim' in instruction


def test_explicit_trend_field_language_is_preserved_before_runtime_binding():
    assert 'For trend and bounded_trend' in UNDERSTANDING_SYSTEM_PROMPT
    assert 'dimension_mentions' in UNDERSTANDING_SYSTEM_PROMPT


def test_dimension_coverage_repair_does_not_guess_or_resolve_field():
    instruction = LLMSemanticInterpreter._repair_instruction(
        SemanticInterpretationError('semantic_coverage_incomplete',
                                    repair_detail={'missing_span': 'Events[Period]'}))
    assert 'Events[Period]' in instruction
    assert 'dimension_mentions' in instruction


@pytest.mark.parametrize('shape', ['trend', 'bounded_trend'])
def test_trend_missing_axis_is_repaired_before_coverage(shape):
    frame = SemanticFrame.model_validate({'mode':'data','query_shape':shape,
        'measure_mentions':['Revenue'], 'evidence_spans':[{'slot':'measure','text':'Revenue'},
            {'slot':'dimension','text':'Events[Period]'}]})
    with pytest.raises(SemanticInterpretationError) as error:
        LLMSemanticInterpreter._validate_structure(frame)
    assert error.value.code == 'trend_dimension_mention_required'
    instruction=LLMSemanticInterpreter._repair_instruction(error.value)
    assert 'dimension_mentions' in instruction
    assert 'verbatim' in instruction


@pytest.mark.parametrize('shape', ['trend', 'bounded_trend'])
def test_implicit_temporal_axis_remains_subject_to_existing_runtime_binding(shape):
    frame = SemanticFrame.model_validate({'mode':'data','query_shape':shape,
        'measure_mentions':['Revenue'], 'evidence_spans':[{'slot':'measure','text':'Revenue'}]})
    LLMSemanticInterpreter._validate_structure(frame)
    assert frame.dimension_mentions == ()


@pytest.mark.asyncio
async def test_final_coverage_failure_preserves_evidence_without_creating_facts():
    frame = SemanticFrame.model_validate({'relation': 'fresh_question', 'changed_slots': [], 'referenced_context_slots': [], 'mode': 'data', 'query_shape': 'scalar',
        'measure_mentions': ['销售额'], 'evidence_spans': [
            {'slot': 'measure', 'text': '销售额'}, {'slot': 'query_shape', 'text': '多少'}]})
    with pytest.raises(SemanticInterpretationError) as caught:
        await LLMSemanticInterpreter(_FrameProvider(frame)).interpret('华南销售额多少')
    assert caught.value.code == 'semantic_coverage_incomplete'
    assert caught.value.repair_detail == {'missing_span': '华南'}
