"""Request-local explicit language transport; no Core or second Grounding."""
import asyncio
import pytest

from backend.app.intent.semantic_interpreter import SemanticFrame, SemanticEvidenceSpan, SemanticFilterMention


def frame(literal,field='Country'):
    return SemanticFrame(relation="fresh_question", changed_slots=(), referenced_context_slots=(), mode='data',query_shape='scalar',member_mentions=(literal,),
        filter_mentions=(SemanticFilterMention(field_mention=field,member_mention=literal,evidence_span=literal),),
        evidence_spans=(SemanticEvidenceSpan(slot='query_shape',text='查询'),
            SemanticEvidenceSpan(slot='member',text=literal),SemanticEvidenceSpan(slot='filter',text=literal)))


@pytest.mark.asyncio
async def test_literals_are_request_local_and_reset_after_failure():
    from backend.app.application.cloud_literal_context import literal_scope, capture_frame, requested_literals
    async def scoped(literal):
        with literal_scope():
            capture_frame(f'查询 Country {literal}',frame(literal))
            await asyncio.sleep(0)
            assert requested_literals('Sales','Country')==(literal,)
            assert requested_literals('Sales','Other')==()
    await asyncio.gather(scoped('France'),scoped('Germany'))
    assert requested_literals('Sales','Country')==()
    with pytest.raises(RuntimeError):
        with literal_scope():
            capture_frame('查询 Country France',frame('France'))
            raise RuntimeError()
    assert requested_literals('Sales','Country')==()


def test_general_or_unbacked_member_never_becomes_targeted_input():
    from backend.app.application.cloud_literal_context import literal_scope, capture_frame, requested_literals
    with literal_scope():
        capture_frame('查询 Country Germany',frame('France'))
        assert requested_literals('Sales','Country')==()
    with literal_scope():
        capture_frame('有哪些 Country',SemanticFrame(relation='fresh_question', changed_slots=(), referenced_context_slots=(), mode='data',query_shape='entity_list',
            dimension_mentions=('Country',),evidence_spans=(SemanticEvidenceSpan(slot='dimension',text='Country'),
                SemanticEvidenceSpan(slot='query_shape',text='有哪些'))))
        assert requested_literals('Sales','Country')==()


def test_no_implicit_full_member_or_date_grain_proof():
    from backend.app.application.cloud_literal_context import literal_scope, capture_frame, requested_literals
    with literal_scope():
        capture_frame('查询 Country France',frame('France'))
        assert requested_literals('Sales','YearMonth')==()
        assert requested_literals('Sales','Country')==('France',)


def test_grounded_callback_transports_language_field_without_selecting_an_object():
    from backend.app.application.cloud_literal_context import (
        literal_scope, capture_frame, requested_literals, grounded_literal_scope)
    from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
    from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, ColumnSchema
    schema = SemanticModelSchema(key='synthetic', name='Synthetic', tables=[TableSchema(
        name='Events', columns=[ColumnSchema(name='Area', data_type='String')])])
    catalog = SemanticCatalogBuilder().build(schema)
    field = catalog.get('field:Events:Area')
    with literal_scope():
        capture_frame('地区改为 Example', frame('Example', '地区'))
        assert requested_literals('Events', 'Area') == ()
        with grounded_literal_scope(field, catalog, schema):
            assert requested_literals('Events', 'Area') == ('Example',)
            assert requested_literals('Events', 'Other') == ()
        assert requested_literals('Events', 'Area') == ()
        for bad_schema, bad_field in (
            (schema.model_copy(update={'key':'other'}), field),
            (schema, field.model_copy(update={'canonical_name':'Other'})),
        ):
            with grounded_literal_scope(bad_field, catalog, bad_schema):
                assert requested_literals('Events', 'Area') == ()


@pytest.mark.asyncio
async def test_native_cloud_callback_transports_existing_frame_without_reinterpretation(monkeypatch):
    from backend.app.application.cloud_product_services import _NativeCloudTurnService
    from backend.app.application.deepseek_turn_service import LLMTurnService
    from backend.app.application.cloud_literal_context import literal_scope, requested_literals
    draft=frame('France')
    expected={'_semantic_frame':draft,'terminal_state':'completed'}
    async def original(service,**kwargs): return expected
    monkeypatch.setattr(LLMTurnService,'_do_conversation',original)
    with literal_scope():
        service = object.__new__(_NativeCloudTurnService)
        result=await service._do_conversation(message='查询 Country France')
        assert result is expected and result['_semantic_frame'] is draft
        assert requested_literals('Sales','Country')==('France',)
    assert requested_literals('Sales','Country')==()
