"""English language drafts keep verbatim evidence, never canonical authority."""
import pytest
from backend.app.intent.semantic_interpreter import LLMSemanticInterpreter,SemanticFrame,SemanticInterpretationError
from backend.app.query_plan.semantic_frame_adapter import build_grounding_draft
from backend.tests.unit.test_m5_10_6_understanding_failure_corpus import _FrameProvider


@pytest.mark.asyncio
@pytest.mark.parametrize('message,shape,dimensions,filters,extra',[
 ('Show total sales by year.','grouped',['year'],[],{}),
 ('Show total margin by territory.','grouped',['territory'],[],{}),
 ('Show me the top 5 countries by total sales.','ranking',['countries'],[],
  {'ranking_intent':{'direction':'desc','top_n':5,'evidence_span':'top 5'}}),
 ('What were the total sales for France in the first half of 2011?','filtered_aggregation',[],
  [{'field_mention':None,'member_mention':'France','operator':'eq','evidence_span':'France'}],
  {'member_mentions':['France'],'time_mentions':['first half of 2011'],'time_intent':{'kind':'bounded_range','expression':'first half of 2011','start_date':'2011-01-01','end_date':'2011-06-30'}}),
])
async def test_english_target_shapes_preserve_evidence(message,shape,dimensions,filters,extra):
    measure='total margin' if 'margin' in message else 'total sales'
    spans=[{'slot':'measure','text':measure},{'slot':'query_shape','text':message}]
    spans += [{'slot':'dimension','text':value} for value in dimensions]
    spans += [{'slot':'filter','text':item['evidence_span']} for item in filters]
    if filters: spans += [{'slot':'member','text':'France'},{'slot':'time','text':'first half of 2011'}]
    if shape=='ranking': spans += [{'slot':'ranking','text':'top 5'}]
    frame=SemanticFrame.model_validate(dict(relation='fresh_question', changed_slots=[], referenced_context_slots=[], mode='data',query_shape=shape,measure_mentions=[measure],
        dimension_mentions=dimensions,filter_mentions=filters,evidence_spans=spans,**extra))
    interpreted=await LLMSemanticInterpreter(_FrameProvider(frame)).interpret(message)
    draft=build_grounding_draft(interpreted,user_input=message,semantic_model_key='synthetic')
    assert draft.query_shape.value==shape
    assert draft.dimensions==dimensions
    assert draft.measures==[measure]
    assert draft.normalized_question==message
    # Translated/paraphrased evidence still fails the unchanged validator.
    with pytest.raises(SemanticInterpretationError):
        LLMSemanticInterpreter._validate_evidence(frame,'A different question')
