"""FIX5: ValueSearch-first members, material coverage and metadata mutations."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from backend.app.application.cloud_product_services import (
    CloudProductServiceFactory, _MetadataResourceLease,
)
from backend.app.application.cloud_workspace_service import CloudWorkspaceService
from backend.app.intent.semantic_interpreter import (
    LLMSemanticInterpreter, SemanticFrame, SemanticInterpretationError,
)
from backend.app.memory.models import RuntimeDataMode
from backend.app.query_plan.clarification_reasons import ClarificationReason
from backend.app.query_plan.grounding import GroundingStatus, SemanticGroundingService
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
from backend.app.schemas.data_contracts import (
    ColumnMembersResult, ColumnSchema, MeasureSchema, QueryShape,
    SemanticModelSchema, TableSchema,
)


def synthetic_schema(*, extra_country_table: bool = False) -> SemanticModelSchema:
    tables = [
        TableSchema(name='Sales', columns=[
            ColumnSchema(name='Country', data_type='String'),
            ColumnSchema(name='Billing Country', data_type='String'),
            ColumnSchema(name='Shipping Country', data_type='String'),
            ColumnSchema(name='StockCode', data_type='String'),
        ], measures=[
            MeasureSchema(name='Total Sales', data_type='Decimal'),
            MeasureSchema(name='Total Quantity', data_type='Integer'),
        ]),
    ]
    if extra_country_table:
        tables.append(TableSchema(name='Unrelated', columns=[
            ColumnSchema(name='Country', data_type='String'),
        ]))
    return SemanticModelSchema(name='Synthetic Retail', key='retail-model',
        metadata_source='fabric_iq', session_generation=1, tables=tables)


def discovery_returning(model_key, candidates):
    async def discovery(literal):
        return ColumnMembersResult(
            semantic_model_key=model_key, table_name='', field_name='',
            values=[], source_mode='real', truncated=True,
            field_candidates=[
                {'table_name': table, 'field_name': field, 'canonical_value': literal}
                for table, field in candidates
            ],
        )
    return discovery


async def no_scan(*_args):
    raise AssertionError('Field-less member must not scan every field')


def member_frame(member, *, measure='Total Sales'):
    return SemanticFrame(mode='data', query_shape='filtered_aggregation',
        measure_mentions=[measure], member_mentions=[member])


class ChoosingProvider:
    """Minimal bounded resolver provider that selects one candidate_id."""

    def __init__(self, chosen_field):
        self._chosen = f'field:Sales:{chosen_field}'

    @property
    def provider(self):
        return self

    async def generate(self, request, output_type):
        import json
        from backend.app.llm.base import LLMResponse
        from backend.app.query_plan.semantic_resolution import (
            ResolutionDecision, ResolutionResponse,
        )
        payload = json.loads(request.messages[-1]['content'])
        decisions = []
        for slot in payload['slots']:
            ids = [item['candidate_id'] for item in slot['candidates']]
            decisions.append(ResolutionDecision(
                slot_id=slot['slot_id'],
                outcome='RESOLVED' if self._chosen in ids else 'UNRESOLVED',
                candidate_id=self._chosen if self._chosen in ids else None,
            ))
        return LLMResponse(content='{}', structured=ResolutionResponse(
            decisions=tuple(decisions)), model='synthetic')


@pytest.mark.asyncio
async def test_value_search_first_binds_france_to_country_without_lexical_overlap():
    schema = synthetic_schema()
    catalog = SemanticCatalogBuilder().build(schema)
    outcome = await SemanticGroundingService(catalog,
        member_discovery=discovery_returning(catalog.semantic_model_key,
            [('Sales', 'Country')])).ground_frame(
                'How much sales did France generate?', member_frame('France'),
                None, no_scan)
    assert outcome.status is GroundingStatus.RESOLVED
    assert [(item.field, item.value) for item in outcome.delta.filters] == [
        ('Country', 'France')]
    field_result = next(item for item in outcome.object_results
        if item.role == 'filter_field')
    assert field_result.method == 'runtime_value_search_unique_field'


@pytest.mark.asyncio
async def test_value_search_first_binds_product_code_without_field_name():
    schema = synthetic_schema()
    catalog = SemanticCatalogBuilder().build(schema)
    outcome = await SemanticGroundingService(catalog,
        member_discovery=discovery_returning(catalog.semantic_model_key,
            [('Sales', 'StockCode')])).ground_frame(
                'What are the sales and quantity for product 15056BL?',
                member_frame('15056BL'), None, no_scan)
    assert outcome.status is GroundingStatus.RESOLVED
    assert [(item.field, item.value) for item in outcome.delta.filters] == [
        ('StockCode', '15056BL')]


@pytest.mark.asyncio
async def test_value_search_scope_prefers_fields_reachable_from_measures():
    schema = synthetic_schema(extra_country_table=True)
    catalog = SemanticCatalogBuilder().build(schema)
    outcome = await SemanticGroundingService(catalog,
        member_discovery=discovery_returning(catalog.semantic_model_key,
            [('Sales', 'Country'), ('Unrelated', 'Country')])).ground_frame(
                'How much sales did France generate?', member_frame('France'),
                None, no_scan)
    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta.dimension_tables['Country'] == 'Sales'
    assert [(item.field, item.value) for item in outcome.delta.filters] == [
        ('Country', 'France')]


@pytest.mark.asyncio
async def test_multiple_runtime_proven_fields_use_one_bounded_role_decision():
    schema = synthetic_schema()
    catalog = SemanticCatalogBuilder().build(schema)
    outcome = await SemanticGroundingService(catalog,
        selector=ChoosingProvider('Billing Country'),
        member_discovery=discovery_returning(catalog.semantic_model_key,
            [('Sales', 'Billing Country'), ('Sales', 'Shipping Country')])
    ).ground_frame('How much sales did France generate?',
        member_frame('France'), None, no_scan)
    assert outcome.status is GroundingStatus.RESOLVED
    assert [(item.field, item.value) for item in outcome.delta.filters] == [
        ('Billing Country', 'France')]
    field_result = next(item for item in outcome.object_results
        if item.role == 'filter_field')
    assert field_result.method == 'runtime_value_search_bounded_role'


@pytest.mark.asyncio
async def test_multiple_runtime_proven_fields_without_decision_clarify():
    schema = synthetic_schema()
    catalog = SemanticCatalogBuilder().build(schema)
    outcome = await SemanticGroundingService(catalog,
        member_discovery=discovery_returning(catalog.semantic_model_key,
            [('Sales', 'Billing Country'), ('Sales', 'Shipping Country')])
    ).ground_frame('How much sales did France generate?',
        member_frame('France'), None, no_scan)
    assert outcome.status is GroundingStatus.AMBIGUOUS
    assert outcome.clarification_reason is ClarificationReason.FILTER_FIELD_AMBIGUOUS
    assert outcome.delta is None or not outcome.delta.filters


@pytest.mark.asyncio
async def test_value_search_no_match_is_member_no_match():
    schema = synthetic_schema()
    catalog = SemanticCatalogBuilder().build(schema)
    outcome = await SemanticGroundingService(catalog,
        member_discovery=discovery_returning(catalog.semantic_model_key, [])
    ).ground_frame('What are the sales for the Mars region?',
        member_frame('Mars'), None, no_scan)
    assert outcome.status is GroundingStatus.UNRESOLVED
    assert outcome.clarification_reason is ClarificationReason.MEMBER_NO_MATCH


def coverage_frame(*, measures=('sales',), unresolved=()):
    return SemanticFrame(mode='data', query_shape=QueryShape.SCALAR,
        measure_mentions=measures, unresolved_mentions=unresolved)


def test_generic_data_model_framing_is_not_a_coverage_veto():
    frame = coverage_frame()
    result = LLMSemanticInterpreter._validate_coverage(
        frame, 'What is the total sales amount in this data model?')
    assert result.unresolved_mentions == ()
    assert result.measure_mentions == ('sales',)


def test_generic_unresolved_mentions_are_dropped_but_material_ones_remain():
    frame = coverage_frame(unresolved=('amount', 'model', 'France', '2011'))
    result = LLMSemanticInterpreter._validate_coverage(
        frame, 'What is the total sales amount in this data model for France in 2011?')
    assert result.unresolved_mentions == ('France', '2011')


def test_measurement_noun_omission_still_blocks_execution():
    frame = SemanticFrame(mode='data', query_shape=QueryShape.FILTERED_AGGREGATION,
        measure_mentions=('total sales',), member_mentions=('France',))
    with pytest.raises(SemanticInterpretationError) as captured:
        LLMSemanticInterpreter._validate_coverage(
            frame, 'What are the total sales and total quantity for France?')
    assert captured.value.code == 'semantic_coverage_incomplete'
    assert captured.value.repair_detail == {'missing_span': 'quantity'}


def test_sentence_initial_command_word_is_not_a_material_literal():
    """Capitalization from sentence position is not naming evidence."""

    from backend.app.intent.language_cues import is_material_literal

    assert is_material_literal('switch', 'Switch that to total quantity.') is False
    assert is_material_literal('change', 'Change that to total quantity.') is False
    # A proper name outside the sentence-initial position still carries identity.
    assert is_material_literal(
        'france', 'What were the sales for France in 2011?') is True


def test_command_follow_up_survives_coverage():
    frame = SemanticFrame(mode='data', relation='follow_up',
        query_shape=QueryShape.SCALAR, measure_mentions=('total quantity',),
        changed_slots=('measure',))
    result = LLMSemanticInterpreter._validate_coverage(
        frame, 'Switch that to total quantity.')
    assert result.measure_mentions == ('total quantity',)


def product_catalog():
    schema = SemanticModelSchema(name='Synthetic Retail', key='retail-model',
        metadata_source='fabric_iq', session_generation=1, tables=[
            TableSchema(name='Sales', columns=[
                ColumnSchema(name='Product', data_type='String'),
                ColumnSchema(name='StockCodeRaw', data_type='String'),
                ColumnSchema(name='Description', data_type='String'),
            ], measures=[MeasureSchema(name='Total Sales', data_type='Decimal')])])
    return SemanticCatalogBuilder().build(schema)


def product_frame():
    return SemanticFrame(mode='data', query_shape='filtered_aggregation',
        measure_mentions=['Total Sales'],
        filter_mentions=[{'field_mention': 'product', 'member_mention': '15056BL',
            'evidence_span': 'product 15056BL'}])


@pytest.mark.asyncio
async def test_runtime_member_evidence_outranks_an_explicit_role_noun():
    catalog = product_catalog()
    outcome = await SemanticGroundingService(catalog,
        member_discovery=discovery_returning(catalog.semantic_model_key,
            [('Sales', 'Description')])).ground_frame(
                'What are the sales for product 15056BL?',
                product_frame(), None, no_scan)
    assert outcome.status is GroundingStatus.RESOLVED
    assert [(item.field, item.value) for item in outcome.delta.filters] == [
        ('Description', '15056BL')]
    field_result = next(item for item in outcome.object_results
        if item.role == 'filter_field')
    assert field_result.method == 'runtime_value_search_unique_field'


@pytest.mark.asyncio
async def test_explicit_field_still_binds_when_runtime_proves_nothing():
    catalog = product_catalog()

    async def members(field, limit):
        values = ['15056BL'] if field.canonical_name == 'Product' else []
        return ColumnMembersResult(
            semantic_model_key=catalog.semantic_model_key,
            table_name=field.table_name, field_name=field.canonical_name,
            values=values, source_mode='real')

    outcome = await SemanticGroundingService(catalog,
        member_discovery=discovery_returning(catalog.semantic_model_key, [])
    ).ground_frame('What are the sales for product 15056BL?',
        product_frame(), None, members)
    assert outcome.status is GroundingStatus.RESOLVED
    assert [(item.field, item.value) for item in outcome.delta.filters] == [
        ('Product', '15056BL')]


def ranking_memory():
    from backend.app.memory.models import MemoryStatus, StructuredWorkMemory
    return StructuredWorkMemory(
        conversation_id='conversation-ranking', request_id='previous-ranking',
        semantic_model_key='retail-model', state_status=MemoryStatus.COMMITTED,
        measures=['Total Sales'], dimensions=['Country'], filters=[],
        sort='desc', top_n=5,
        last_query_plan={'query_shape': 'ranking', 'measures': ['Total Sales'],
            'dimensions': ['Country'], 'filters': []},
        memory_version=3)


def test_ranking_operators_do_not_leak_into_a_non_ranking_follow_up():
    from backend.app.query_plan.grounding import GroundedSemanticDelta
    from backend.app.query_plan.semantic_frame_adapter import build_grounding_draft
    from backend.app.query_plan.state_transition import StateTransitionService
    from backend.app.schemas.data_contracts import StructuredFilter

    frame = SemanticFrame(mode='data', relation='follow_up',
        query_shape=QueryShape.FILTERED_AGGREGATION, measure_mentions=('Total Sales',),
        member_mentions=('France',))
    delta = GroundedSemanticDelta(query_shape=QueryShape.FILTERED_AGGREGATION,
        measures=['Total Sales'],
        filters=[StructuredFilter(field='Country', value='France')])
    plan = StateTransitionService().merge(
        build_grounding_draft(frame, user_input='What about France?',
            semantic_model_key='retail-model'), delta, ranking_memory()).query_plan
    assert plan.query_shape is QueryShape.FILTERED_AGGREGATION
    assert plan.sort is None
    assert plan.top_n is None


def test_a_still_ranking_follow_up_keeps_its_operators():
    from backend.app.query_plan.grounding import GroundedSemanticDelta
    from backend.app.query_plan.semantic_frame_adapter import build_grounding_draft
    from backend.app.query_plan.state_transition import StateTransitionService

    frame = SemanticFrame(mode='data', relation='follow_up',
        query_shape=QueryShape.RANKING, measure_mentions=('Total Quantity',),
        dimension_mentions=('Country',))
    delta = GroundedSemanticDelta(query_shape=QueryShape.RANKING,
        measures=['Total Quantity'], dimensions=['Country'])
    plan = StateTransitionService().merge(
        build_grounding_draft(frame, user_input='Switch that to total quantity.',
            semantic_model_key='retail-model'), delta, ranking_memory()).query_plan
    assert plan.query_shape is QueryShape.RANKING
    assert plan.sort == 'desc'
    assert plan.top_n == 5


def test_presentation_locale_follows_the_current_request():
    from backend.app.presentation.builder import StructuredPresentationBuilder
    from backend.app.presentation.locale import presentation_locale

    with presentation_locale('en-US'):
        english = StructuredPresentationBuilder.build_report('report-1')
    with presentation_locale('zh-CN'):
        chinese = StructuredPresentationBuilder.build_report('report-1')
    english_text = english.blocks[0].content
    chinese_text = chinese.blocks[0].content
    assert english_text != chinese_text
    assert english_text.startswith('Your report is ready')
    assert chinese_text.startswith('报表已生成')


class _LabelBinding:
    """Minimal stand-in for DisplayLocalization used by the label resolver."""

    def __init__(self, canonical, display, source='fallback'):
        self.canonical_name = canonical
        self.display_name = display
        self.source = SimpleNamespace(value=source)

    def model_copy(self, *, update):
        clone = _LabelBinding(self.canonical_name, self.display_name, self.source.value)
        for key, value in update.items():
            setattr(clone, key, value)
        return clone


def test_two_measures_keep_the_phrase_that_denotes_each_of_them():
    from backend.app.application.deepseek_turn_service import (
        apply_measure_display_names,
    )

    bindings = {
        'Total Sales': _LabelBinding('Total Sales', 'sales'),
        'Total Quantity': _LabelBinding('Total Quantity', 'sales'),
    }
    apply_measure_display_names(
        bindings, ['Total Sales', 'Total Quantity'],
        {'Total Sales': 'sales', 'Total Quantity': 'quantity'})
    assert bindings['Total Sales'].display_name == 'sales'
    assert bindings['Total Quantity'].display_name == 'quantity'


def test_two_measures_never_share_one_display_label():
    from backend.app.application.deepseek_turn_service import (
        apply_measure_display_names,
    )

    bindings = {
        'Total Sales': _LabelBinding('Total Sales', 'same'),
        'Total Quantity': _LabelBinding('Total Quantity', 'same'),
    }
    apply_measure_display_names(
        bindings, ['Total Sales', 'Total Quantity'],
        {'Total Sales': 'same', 'Total Quantity': 'same'})
    labels = {binding.display_name for binding in bindings.values()}
    assert len(labels) == 2
    assert bindings['Total Quantity'].display_name == 'Total Quantity'


def test_proper_literal_and_numeric_omission_still_block_execution():
    frame = coverage_frame()
    with pytest.raises(SemanticInterpretationError) as captured:
        LLMSemanticInterpreter._validate_coverage(
            frame, 'Total sales for France in 2011')
    assert captured.value.repair_detail == {'missing_span': 'france'}
    with pytest.raises(SemanticInterpretationError) as captured:
        LLMSemanticInterpreter._validate_coverage(
            frame, 'Total sales for product 15056BL')
    assert captured.value.repair_detail == {'missing_span': '15056bl'}


@dataclass
class _Binding:
    model_key: str = 'retail-model'
    workspace_id: object = 'workspace-1'
    model_id: object = 'model-1'
    schema_fingerprint: str = 'fingerprint'
    source_mode: str = 'real'


class _FakeAuth:
    def __init__(self):
        self.settings = SimpleNamespace(fabric_test_mode=False)
        self.principal = SimpleNamespace()

    def require_session(self, sid):
        assert sid == 'session-1'
        return SimpleNamespace(principal=self.principal)


class _FakeAdapter:
    def assert_session_binding(self, auth, sid, principal):
        return None

    def bound_resource_identity(self, key):
        return ('workspace-1', 'model-1')


class _FakeWorkspace(CloudWorkspaceService):
    """Real Cloud boundary without any semantic schema round-trip."""

    _synthetic_product = False

    def __init__(self):
        self.summary_calls = 0
        self.revalidate_calls = 0
        self.policy = ('product', True, True)

    def policy_snapshot(self):
        return self.policy

    def status(self, sid, principal):
        return SimpleNamespace(generation=3, selected_model_key='retail-model',
            conversation_id='conversation-2')

    def require_persistence(self, sid, principal, *, binding=None):
        return None

    async def authorize_persisted_summary(self, sid, principal, binding):
        assert (binding.workspace_id, binding.model_id) == ('workspace-1', 'model-1')
        self.summary_calls += 1

    async def revalidate_binding(self, *args, **kwargs):
        self.revalidate_calls += 1
        raise AssertionError('schema revalidation is not metadata authority')

    def _context(self, sid, principal):
        return SimpleNamespace(adapter=_FakeAdapter())

    def data_mode(self, sid, principal):
        return RuntimeDataMode.REAL


class _FakeHistoryService:
    def __init__(self):
        self.calls = []

    async def rename(self, mode, conversation_id, title):
        self.calls.append(('rename', mode, conversation_id, title))
        return {'conversation_id': conversation_id, 'title': title}

    async def archive(self, mode, conversation_id):
        self.calls.append(('archive', mode, conversation_id))
        return {'conversation_id': conversation_id}


class _FakeRepositories:
    def __init__(self, binding):
        self.cloud_bindings = SimpleNamespace(get=self._get_binding,
            delete=lambda cid: None)
        self.history_service = _FakeHistoryService()
        self.reports = SimpleNamespace()

    async def _get_binding(self, conversation_id):
        return _Binding()


class _FakeRepositoryFactory:
    def __init__(self, repositories):
        self._repositories = repositories
        self.session_proofs = []

    async def for_session(self, auth, sid, principal):
        self.session_proofs.append(auth)
        return self._repositories


@pytest.mark.asyncio
@pytest.mark.parametrize('action,title', [('rename', 'new title'), ('archive', None)])
async def test_metadata_mutation_authorizes_current_access_without_schema(action, title):
    workspace = _FakeWorkspace()
    repositories = _FakeRepositories(_Binding())
    factory = _FakeRepositoryFactory(repositories)
    auth = _FakeAuth()
    principal = auth.principal
    service = CloudProductServiceFactory(auth, workspace, factory, None, None)
    result = await service.mutate_resource('session-1', principal,
        'history', 'conversation-1', action, expected_generation=3, title=title)
    assert workspace.summary_calls >= 2
    assert workspace.revalidate_calls == 0
    assert repositories.history_service.calls == [
        (action, RuntimeDataMode.REAL, 'conversation-1') + ((title,) if title else ())
    ]
    assert result['workspace_status'].generation == 3
    assert any(isinstance(proof, _MetadataResourceLease)
        for proof in factory.session_proofs)


@pytest.mark.asyncio
async def test_metadata_lease_revalidation_never_loads_a_schema():
    workspace = _FakeWorkspace()
    auth = _FakeAuth()
    lease = _MetadataResourceLease(auth, workspace, 'session-1',
        auth.principal, workspace.status('session-1', auth.principal),
        adapter=_FakeAdapter(), binding=_Binding())
    await lease.revalidate_resource()
    assert workspace.summary_calls == 1
    assert workspace.revalidate_calls == 0


def test_localized_scope_answer_validates_under_its_own_locale():
    """A localized answer is not rejected for being in the request language.

    Regression: the fact validator forced ``zh-CN`` when recomputing the
    deterministic scope prefix, so every non-empty localized scope mismatched
    and the turn collapsed into INTERNAL_FAILURE at ANSWER_GENERATION.
    """

    from datetime import date

    from backend.app.facts import (
        FactBoundedAnswerBuilder, FactOutputValidator, VerifiedFactSetBuilder,
    )
    from backend.app.presentation.locale import presentation_locale
    from backend.app.schemas.data_contracts import (
        CanonicalQueryPlan, QueryResult, QueryShape,
        StructuredFilter, TimeRangeMode, TimeRangeSpec,
    )

    plan = CanonicalQueryPlan(
        normalized_question="q", semantic_model_key="model",
        query_shape=QueryShape.FILTERED_AGGREGATION, measures=["Total Sales"],
        filters=[StructuredFilter(field="Country", value="France")],
        time_range=TimeRangeSpec(
            date_field="Order Date", start_date=date(2011, 1, 1),
            end_date=date(2011, 6, 30), mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month"),
    )
    result = QueryResult(
        result_id="r1", semantic_model_key="model", columns=["[Total Sales]"],
        rows=[[123.45]], row_count=1, source_mode="real")
    facts = VerifiedFactSetBuilder().build(plan, result)

    with presentation_locale("en-US"):
        answer = FactBoundedAnswerBuilder().build(
            plan, result, facts,
            user_facing_filter_values={("Country", "France"): "France"})
        assert answer.evidence["user_facing_scope"]
        # Default locale follows the ambient request locale, not a hard-coded one.
        assert FactOutputValidator().validate_answer(answer, facts) == []

    # An explicit override still wins, and a genuinely foreign locale still
    # rejects the mismatch: the validator is aligned, never weakened.
    with presentation_locale("en-US"):
        assert FactOutputValidator().validate_answer(
            answer, facts, locale="zh-CN"
        ) == ["user_facing_scope_mismatch", "unverified_numeric_claim"]


def _trend_memory():
    from backend.app.memory.models import MemoryStatus, StructuredWorkMemory
    return StructuredWorkMemory(
        conversation_id='conversation-trend', request_id='previous-trend',
        semantic_model_key='retail-model', state_status=MemoryStatus.COMMITTED,
        measures=['Total Sales'], dimensions=['YearMonth'], filters=[],
        sort=None, top_n=None,
        last_query_plan={
            'query_shape': 'bounded_trend', 'measures': ['Total Sales'],
            'dimensions': ['YearMonth'], 'filters': [],
            'time_range': {'date_field': 'Order Date', 'start_date': '2011-01-01',
                'end_date': '2011-06-30', 'mode': 'explicit_range', 'grain': 'month'},
        },
        memory_version=3)


def _merge_follow_up(frame, delta, memory):
    from backend.app.query_plan.semantic_frame_adapter import build_grounding_draft
    from backend.app.query_plan.state_transition import StateTransitionService
    return StateTransitionService().merge(
        build_grounding_draft(frame, user_input='follow up',
            semantic_model_key='retail-model'), delta, memory).query_plan


def test_a_trend_time_axis_does_not_leak_into_a_non_trend_follow_up():
    """Regression: 'product 15056BL' after a monthly trend stayed grouped.

    The inherited date axis made the answer describe an unrelated monthly
    series as a trend; the factual authority refused the claim and the turn
    collapsed into INTERNAL_FAILURE at ANSWER_GENERATION.
    """

    from backend.app.query_plan.grounding import GroundedSemanticDelta
    from backend.app.schemas.data_contracts import StructuredFilter

    frame = SemanticFrame(mode='data', relation='follow_up',
        query_shape=QueryShape.FILTERED_AGGREGATION,
        measure_mentions=('Total Sales', 'Total Quantity'),
        member_mentions=('15056BL',),
        filter_mentions=({'field_mention': 'product', 'member_mention': '15056BL',
            'evidence_span': 'product 15056BL'},),
        changed_slots=('filter', 'filters', 'measure', 'measures', 'member',
            'query_shape'))
    delta = GroundedSemanticDelta(query_shape=QueryShape.FILTERED_AGGREGATION,
        measures=['Total Sales', 'Total Quantity'],
        filters=[StructuredFilter(field='Product', value='15056BL')])
    plan = _merge_follow_up(frame, delta, _trend_memory())
    assert plan.query_shape is QueryShape.FILTERED_AGGREGATION
    assert plan.dimensions == []
    assert plan.measures == ['Total Sales', 'Total Quantity']
    assert [(item.field, item.value) for item in plan.filters] == [
        ('Product', '15056BL')]


def test_a_trend_axis_is_kept_by_a_still_trend_follow_up():
    from backend.app.query_plan.grounding import GroundedSemanticDelta
    from backend.app.schemas.data_contracts import StructuredFilter

    frame = SemanticFrame(mode='data', relation='follow_up',
        query_shape=QueryShape.BOUNDED_TREND, member_mentions=('France',))
    delta = GroundedSemanticDelta(query_shape=QueryShape.BOUNDED_TREND,
        measures=['Total Sales'],
        filters=[StructuredFilter(field='Country', value='France')])
    plan = _merge_follow_up(frame, delta, _trend_memory())
    assert plan.query_shape is QueryShape.BOUNDED_TREND
    assert plan.dimensions == ['YearMonth']
