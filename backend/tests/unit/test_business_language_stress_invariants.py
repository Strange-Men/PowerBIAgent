"""M5.9.4 cross-domain grounding, memory, and ZERO-DAX invariants."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.intent.question_router import QuestionRouter
from backend.app.memory.models import StructuredWorkMemory
from backend.app.query_plan.completeness import (
    CanonicalShapeCompletenessError,
    CanonicalShapeCompletenessGate,
    SemanticObligationCoverageGate,
)
from backend.app.query_plan.grounding import (
    GroundedSemanticDelta,
    GroundingStatus,
    SemanticGroundingService,
)
from backend.app.query_plan.state_transition import (
    InheritanceMode,
    StateTransitionService,
    TurnInheritancePolicy,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticObjectType,
)
from backend.app.query_plan.turn_relation import TurnRelationEvidence
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    FilterOperator,
    QueryPlan,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)
from backend.tests.stress.business_language_stress import DOMAINS, _runtime_fixture


def _intent(question: str) -> IntentSpec:
    return IntentSpec(
        intent=IntentType.DATA_QUESTION,
        confidence=0.99,
        normalized_question=question,
    )


def _draft(question: str, model_key: str, shape: QueryShape) -> QueryPlan:
    return QueryPlan(
        normalized_question=question,
        semantic_model_key=model_key,
        query_shape=shape,
    )


def _member_lookup(domain):
    async def lookup(field, limit):
        assert limit == 100
        if field.canonical_name == domain.filter_field[0]:
            values = list(domain.known_members)
        elif field.canonical_name == domain.dimension[0]:
            values = [domain.known_dimension_member]
        else:
            values = []
        return ColumnMembersResult(
            semantic_model_key=domain.fixture_id,
            table_name=field.table_name,
            field_name=field.canonical_name,
            values=values,
            source_mode="mock",
        )

    return lookup


@pytest.mark.asyncio
async def test_cross_domain_grouping_language_metamorphs_bind_runtime_objects() -> None:
    templates = (
        "各{dimension}{measure}",
        "每个{dimension}{measure}",
        "按{dimension}看{measure}",
        "{dimension}{measure}分别是多少",
    )
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        for template in templates:
            question = template.format(
                dimension=domain.dimension[1], measure=domain.measure[1]
            )
            assert QuestionRouter().route(question).query_shape == QueryShape.GROUPED
            outcome = await SemanticGroundingService(fixture.catalog).ground(
                question,
                _intent(question),
                _draft(question, domain.fixture_id, QueryShape.GROUPED),
                None,
                _member_lookup(domain),
                query_shape=QueryShape.GROUPED,
            )
            assert outcome.status == GroundingStatus.RESOLVED, (domain.fixture_id, question, outcome)
            assert outcome.delta is not None
            assert outcome.delta.measures == [domain.measure[0]]
            assert outcome.delta.dimensions == [domain.dimension[0]]
            assert not outcome.delta.filters


@pytest.mark.asyncio
async def test_discourse_markers_do_not_become_business_modifiers() -> None:
    markers = (
        "请问", "能不能帮忙", "麻烦", "简单看下", "直接", "顺便", "其中"
    )
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        for marker in markers:
            question = f"{marker}{domain.measure[1]}是多少"
            outcome = await SemanticGroundingService(fixture.catalog).ground(
                question,
                _intent(question),
                _draft(question, domain.fixture_id, QueryShape.SCALAR),
                None,
                _member_lookup(domain),
                query_shape=QueryShape.SCALAR,
            )
            coverage = SemanticObligationCoverageGate().inspect(
                user_input=question,
                outcome=outcome,
                catalog=fixture.catalog,
                relation=TurnRelationEvidence.classify(question),
            )
            assert outcome.status == GroundingStatus.RESOLVED
            assert outcome.delta is not None
            assert coverage.executable, (domain.fixture_id, marker, coverage)


@pytest.mark.asyncio
async def test_router_trend_terms_are_consumed_by_semantic_coverage() -> None:
    trend_phrases = ("月度走势", "按月看变化", "逐月趋势")
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        for phrase in trend_phrases:
            question = f"今年{domain.measure[1]}{phrase}"
            outcome = await SemanticGroundingService(fixture.catalog).ground(
                question,
                _intent(question),
                _draft(question, domain.fixture_id, QueryShape.TREND),
                None,
                _member_lookup(domain),
                query_shape=QueryShape.TREND,
            )
            coverage = SemanticObligationCoverageGate().inspect(
                user_input=question,
                outcome=outcome,
                catalog=fixture.catalog,
                relation=TurnRelationEvidence.classify(question),
            )
            assert outcome.status == GroundingStatus.RESOLVED
            assert coverage.executable, (domain.fixture_id, phrase, coverage)


@pytest.mark.asyncio
async def test_generic_month_alias_does_not_create_a_second_trend_axis() -> None:
    domain = DOMAINS[0]
    fixture = _runtime_fixture(domain)
    month_name = CatalogObject(
        object_id="field:Calendar:MonthName",
        canonical_name="MonthName",
        object_type=SemanticObjectType.FIELD,
        table_name="Calendar",
        data_type="string",
        aliases=("月", "月份"),
    )
    temporal_objects = tuple(
        item.model_copy(update={"aliases": ("月", "月份")})
        if item.canonical_name == fixture.temporal_dimension else item
        for item in fixture.catalog.objects
    )
    catalog = fixture.catalog.model_copy(update={
        "objects": (*temporal_objects, month_name)
    })
    question = f"{domain.measure[1]}按月看变化"

    outcome = await SemanticGroundingService(catalog).ground(
        question,
        _intent(question),
        _draft(question, domain.fixture_id, QueryShape.TREND).model_copy(
            update={"dimensions": ["月"]}
        ),
        None,
        _member_lookup(domain),
        query_shape=QueryShape.TREND,
    )

    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.dimensions == [fixture.temporal_dimension]
    assert "MonthName" not in outcome.delta.dimensions


@pytest.mark.asyncio
async def test_entity_list_structure_terms_do_not_become_filter_residue() -> None:
    templates = ("列出所有{dimension}", "展示全部{dimension}清单")
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        for template in templates:
            question = template.format(dimension=domain.dimension[1])
            outcome = await SemanticGroundingService(fixture.catalog).ground(
                question,
                _intent(question),
                _draft(question, domain.fixture_id, QueryShape.ENTITY_LIST),
                None,
                _member_lookup(domain),
                query_shape=QueryShape.ENTITY_LIST,
            )
            coverage = SemanticObligationCoverageGate().inspect(
                user_input=question,
                outcome=outcome,
                catalog=fixture.catalog,
                relation=TurnRelationEvidence.classify(question),
            )
            assert outcome.status == GroundingStatus.RESOLVED
            assert coverage.executable, (domain.fixture_id, question, coverage)


@pytest.mark.asyncio
async def test_entity_list_field_suffix_is_not_an_unknown_member() -> None:
    domain = DOMAINS[1]
    fixture = _runtime_fixture(domain)
    catalog = fixture.catalog.model_copy(update={
        "objects": tuple(
            item.model_copy(update={"member_suffixes": ("项目",)})
            if item.canonical_name == domain.dimension[0]
            else item
            for item in fixture.catalog.objects
        )
    })
    question = f"列出所有{domain.dimension[1]}"

    outcome = await SemanticGroundingService(catalog).ground(
        question,
        _intent(question),
        _draft(question, domain.fixture_id, QueryShape.ENTITY_LIST),
        None,
        _member_lookup(domain),
        query_shape=QueryShape.ENTITY_LIST,
    )

    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.dimensions == [domain.dimension[0]]
    assert not outcome.member_results


@pytest.mark.asyncio
async def test_cross_domain_bounded_time_keeps_both_endpoints_and_month_grain() -> None:
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        question = f"今年1月至6月每个月的{domain.measure[1]}趋势"
        outcome = await SemanticGroundingService(
            fixture.catalog, today=lambda: date(2026, 9, 10)
        ).ground(
            question,
            _intent(question),
            _draft(question, domain.fixture_id, QueryShape.BOUNDED_TREND),
            None,
            _member_lookup(domain),
            query_shape=QueryShape.BOUNDED_TREND,
        )
        assert outcome.status == GroundingStatus.RESOLVED, (domain.fixture_id, outcome)
        assert outcome.delta is not None and outcome.delta.time_range is not None
        assert outcome.delta.time_range.start_date == date(2026, 1, 1)
        assert outcome.delta.time_range.end_date == date(2026, 6, 30)
        assert outcome.delta.time_range.grain == "month"
        assert outcome.delta.time_range.date_field == fixture.date_field
        assert outcome.delta.dimensions == [fixture.temporal_dimension]


@pytest.mark.asyncio
async def test_yearless_bounded_time_is_clarification_and_zero_dax() -> None:
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        question = f"1月到6月每个月的{domain.measure[1]}趋势"
        outcome = await SemanticGroundingService(
            fixture.catalog, today=lambda: date(2026, 9, 10)
        ).ground(
            question,
            _intent(question),
            _draft(question, domain.fixture_id, QueryShape.BOUNDED_TREND),
            None,
            _member_lookup(domain),
            query_shape=QueryShape.BOUNDED_TREND,
        )
        coverage = SemanticObligationCoverageGate().inspect(
            user_input=question,
            outcome=outcome,
            catalog=fixture.catalog,
            relation=TurnRelationEvidence.classify(question),
        )
        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.time_range is None
        assert not coverage.executable


@pytest.mark.asyncio
async def test_unknown_and_known_unknown_member_sets_fail_closed_before_dax() -> None:
    dax_attempts = 0
    checked = 0
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        known_values = list(domain.known_members[:2])
        known_question = f"{'和'.join(known_values)}的{domain.measure[1]}分别是多少"
        known_draft = _draft(
            known_question, domain.fixture_id, QueryShape.MEMBER_SET
        )
        known_outcome = await SemanticGroundingService(fixture.catalog).ground(
            known_question,
            _intent(known_question),
            known_draft,
            None,
            _member_lookup(domain),
            query_shape=QueryShape.MEMBER_SET,
        )
        assert known_outcome.status == GroundingStatus.RESOLVED
        assert known_outcome.delta is not None
        assert known_outcome.delta.filters is not None
        assert known_outcome.delta.filters[0].field == domain.filter_field[0]
        assert known_outcome.delta.filters[0].operator == FilterOperator.IN_SET
        assert known_outcome.delta.filters[0].value == known_values
        known_coverage = SemanticObligationCoverageGate().inspect(
            user_input=known_question,
            outcome=known_outcome,
            catalog=fixture.catalog,
            relation=TurnRelationEvidence.classify(known_question),
        )
        assert known_coverage.executable, (domain.fixture_id, known_coverage)
        for values in (
            [domain.unknown_member],
            [domain.known_members[0], domain.unknown_member],
        ):
            joined = "和".join(values)
            question = f"{joined}的{domain.measure[1]}分别是多少"
            draft = _draft(question, domain.fixture_id, QueryShape.MEMBER_SET)
            outcome = await SemanticGroundingService(fixture.catalog).ground(
                question,
                _intent(question),
                draft,
                None,
                _member_lookup(domain),
                query_shape=QueryShape.MEMBER_SET,
            )
            coverage = SemanticObligationCoverageGate().inspect(
                user_input=question,
                outcome=outcome,
                catalog=fixture.catalog,
                relation=TurnRelationEvidence.classify(question),
            )
            checked += 1
            assert outcome.status in {
                GroundingStatus.NOT_MENTIONED,
                GroundingStatus.UNRESOLVED,
                GroundingStatus.AMBIGUOUS,
                GroundingStatus.RESOLVED,
            }
            executable_boundary = (
                coverage.executable
                and outcome.status == GroundingStatus.RESOLVED
                and outcome.delta is not None
            )
            if executable_boundary:
                try:
                    candidate_plan = StateTransitionService().merge(
                        draft,
                        outcome.delta,
                        None,
                        inheritance_mode=InheritanceMode.FRESH_QUESTION,
                    ).query_plan
                    CanonicalShapeCompletenessGate().validate(
                        candidate_plan, catalog=fixture.catalog
                    )
                except (CanonicalShapeCompletenessError, ValueError):
                    executable_boundary = False
            assert not executable_boundary, (
                domain.fixture_id,
                values,
                outcome.model_dump(mode="json"),
                coverage.model_dump(mode="json"),
            )
            # The frozen execution owner is intentionally never invoked.
            if executable_boundary:  # pragma: no cover - invariant tripwire
                dax_attempts += 1
    assert checked == 8
    assert dax_attempts == 0


@pytest.mark.asyncio
async def test_qualified_member_set_connectors_are_structure_after_runtime_resolution() -> None:
    domain = DOMAINS[0]
    fixture = _runtime_fixture(domain)
    field = next(
        item
        for item in fixture.catalog.objects
        if item.canonical_name == domain.filter_field[0]
    )
    left, right = domain.known_members[:2]
    question = (
        f"{field.table_name}[{field.canonical_name}]中\"{left}\"和\"{right}\""
        f"的{domain.measure[1]}分别是多少"
    )
    outcome = await SemanticGroundingService(fixture.catalog).ground(
        question,
        _intent(question),
        _draft(question, domain.fixture_id, QueryShape.MEMBER_SET),
        None,
        _member_lookup(domain),
        query_shape=QueryShape.MEMBER_SET,
    )
    coverage = SemanticObligationCoverageGate().inspect(
        user_input=question,
        outcome=outcome,
        catalog=fixture.catalog,
        relation=TurnRelationEvidence.classify(question),
    )

    assert outcome.status == GroundingStatus.RESOLVED
    assert coverage.executable, coverage


@pytest.mark.asyncio
async def test_filtered_aggregation_structure_terms_preserve_complete_member_set() -> None:
    cues = ("加起来", "合起来", "一起", "总共")
    for domain in DOMAINS:
        fixture = _runtime_fixture(domain)
        members = "和".join(domain.known_members[:2])
        for cue in cues:
            question = f"{members}{cue}的{domain.measure[1]}是多少"
            outcome = await SemanticGroundingService(fixture.catalog).ground(
                question,
                _intent(question),
                _draft(question, domain.fixture_id, QueryShape.FILTERED_AGGREGATION),
                None,
                _member_lookup(domain),
                query_shape=QueryShape.FILTERED_AGGREGATION,
            )
            coverage = SemanticObligationCoverageGate().inspect(
                user_input=question,
                outcome=outcome,
                catalog=fixture.catalog,
                relation=TurnRelationEvidence.classify(question),
            )
            assert outcome.status == GroundingStatus.RESOLVED
            assert coverage.executable, (domain.fixture_id, cue, coverage)


def test_fresh_follow_replace_clear_and_model_switch_do_not_bleed_slots() -> None:
    first, second = DOMAINS[0], DOMAINS[1]
    committed_time = TimeRangeSpec(
        date_field="Month",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
        mode=TimeRangeMode.EXPLICIT_RANGE,
        grain="month",
    )
    committed = StructuredWorkMemory(
        conversation_id="m594-conversation",
        request_id="m594-request-a",
        semantic_model_key=first.fixture_id,
        measures=[first.measure[0]],
        dimensions=[first.dimension[0]],
        filters=[StructuredFilter(
            field=first.filter_field[0], value=first.known_members[0]
        ).model_dump(mode="json")],
        time_range=committed_time,
        sort="desc",
        top_n=3,
        last_query_plan={
            "query_shape": QueryShape.RANKING.value,
            "dimension_tables": {first.dimension[0]: "Products"},
            "dimension_order": None,
        },
    )
    service = StateTransitionService()

    follow_delta = GroundedSemanticDelta(
        query_shape=QueryShape.RANKING,
        filters=[StructuredFilter(
            field=first.filter_field[0], value=first.known_members[1]
        )],
    )
    follow_intent = _intent("那换成华北呢")
    follow_policy = TurnInheritancePolicy.decide(
        "那只看华北呢", follow_intent, follow_delta, committed
    )
    assert follow_policy.mode == InheritanceMode.FOLLOW_UP
    followed = service.merge(
        _draft("那只看华北呢", first.fixture_id, QueryShape.RANKING),
        follow_delta,
        committed,
        inheritance_mode=InheritanceMode.FOLLOW_UP,
    ).query_plan
    assert followed.measures == [first.measure[0]]
    assert followed.dimensions == [first.dimension[0]]
    assert followed.filters[0].value == first.known_members[1]
    assert followed.time_range == committed_time
    assert followed.top_n == 3 and followed.sort == "desc"

    cleared = service.merge(
        _draft("独立问题：不限制范围", first.fixture_id, QueryShape.SCALAR),
        GroundedSemanticDelta(
            query_shape=QueryShape.SCALAR,
            measures=[first.measure[0]],
            clear_filters=True,
            clear_time=True,
            clear_sort=True,
            clear_top_n=True,
        ),
        committed,
        inheritance_mode=InheritanceMode.FRESH_QUESTION,
    ).query_plan
    assert cleared.filters == [] and cleared.time_range is None
    assert cleared.dimensions == [] and cleared.sort is None and cleared.top_n is None

    switched = service.merge(
        _draft("独立问题", second.fixture_id, QueryShape.GROUPED),
        GroundedSemanticDelta(
            query_shape=QueryShape.GROUPED,
            measures=[second.measure[0]],
            dimensions=[second.dimension[0]],
        ),
        committed,
        inheritance_mode=InheritanceMode.FRESH_QUESTION,
    ).query_plan
    switched_json = switched.model_dump_json()
    assert switched.semantic_model_key == second.fixture_id
    assert switched.measures == [second.measure[0]]
    assert switched.dimensions == [second.dimension[0]]
    assert first.measure[0] not in switched_json
    assert first.dimension[0] not in switched_json
    assert first.known_members[0] not in switched_json
