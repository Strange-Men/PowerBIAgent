"""Business semantic grounding invariants."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.memory.models import MemoryStatus, StructuredWorkMemory
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector,
    CandidateSelection,
    GroundedSemanticDelta,
    GroundingStatus,
    MemberGrounder,
    ObjectGrounder,
    SemanticGroundingService,
    TimeGrounder,
)
from backend.app.llm.base import LLMProvider, LLMResponse
from backend.app.query_plan.semantic_catalog import (
    GlossaryCatalogError,
    SemanticCatalogBuilder,
    SemanticObjectType,
)
from backend.app.query_plan.state_transition import (
    FilterTransition,
    SlotTransition,
    StateTransitionService,
)
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    ColumnSchema,
    MeasureSchema,
    QueryPlan,
    SemanticModelSchema,
    StructuredFilter,
    TableSchema,
    TimeRangeMode,
)


def _schema(*, two_dates: bool = False) -> SemanticModelSchema:
    columns = [
        ColumnSchema(name="Category", data_type="String"),
        ColumnSchema(name="Product", data_type="String"),
        ColumnSchema(name="OrderDate", data_type="DateTime"),
    ]
    if two_dates:
        columns.append(ColumnSchema(name="ShipDate", data_type="DateTime"))
    return SemanticModelSchema(
        name="Local",
        key="local_desktop_model",
        tables=[TableSchema(
            name="Sales",
            columns=columns,
            measures=[
                MeasureSchema(name="Total Sales", data_type="Double"),
                MeasureSchema(name="Total Quantity", data_type="Int64"),
            ],
        )],
    )


def _glossary(**overrides):
    raw = {
        "version": 1,
        "semantic_model_key": "local_desktop_model",
        "measures": {
            "Total Sales": {
                "table_name": "Sales", "object_type": "measure",
                "aliases": ["销售额"],
            },
            "Total Quantity": {
                "table_name": "Sales", "object_type": "measure",
                "aliases": ["销量"],
            },
        },
        "fields": {
            "Category": {
                "table_name": "Sales", "object_type": "field",
                "aliases": ["类别"],
            },
            "Product": {
                "table_name": "Sales", "object_type": "field",
                "aliases": ["产品"],
            },
            "OrderDate": {
                "table_name": "Sales", "object_type": "field",
                "aliases": ["订单日期"],
            },
        },
    }
    raw.update(overrides)
    return raw


def _catalog(glossary=None):
    return SemanticCatalogBuilder().build_from_data(
        _schema(), glossary or _glossary()
    )


def _intent(**kwargs) -> IntentSpec:
    defaults = {
        "intent": IntentType.DATA_QUESTION,
        "confidence": 0.9,
        "normalized_question": "query",
    }
    defaults.update(kwargs)
    return IntentSpec(**defaults)


def _draft(**kwargs) -> QueryPlan:
    defaults = {
        "normalized_question": "query",
        "semantic_model_key": "local_desktop_model",
    }
    defaults.update(kwargs)
    return QueryPlan(**defaults)


class TestSemanticCatalogAndObjectGrounding:
    def test_canonical_exact_and_unique_alias_resolve(self):
        grounder = ObjectGrounder(_catalog())
        canonical = grounder.resolve_phrase(
            "Total Sales", SemanticObjectType.MEASURE, "measure"
        )
        alias = grounder.resolve_phrase(
            "销量", SemanticObjectType.MEASURE, "measure"
        )
        assert canonical.status == GroundingStatus.RESOLVED
        assert canonical.canonical_object.canonical_name == "Total Sales"
        assert alias.status == GroundingStatus.RESOLVED
        assert alias.canonical_object.canonical_name == "Total Quantity"

    def test_wrong_model_key_and_unknown_object_rejected(self):
        wrong = _glossary(semantic_model_key="wrong")
        with pytest.raises(
            GlossaryCatalogError, match="glossary_semantic_model_key_mismatch"
        ):
            SemanticCatalogBuilder().build_from_data(_schema(), wrong)
        unknown = _glossary()
        unknown["measures"]["Ghost"] = {
            "table_name": "Sales", "object_type": "measure", "aliases": ["ghost"]
        }
        with pytest.raises(GlossaryCatalogError, match="glossary_unknown_object"):
            SemanticCatalogBuilder().build_from_data(_schema(), unknown)

    def test_alias_conflict_is_config_conflict(self):
        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["指标"]
        glossary["measures"]["Total Quantity"]["aliases"] = ["指标"]
        catalog = _catalog(glossary)
        result = ObjectGrounder(catalog).resolve_phrase(
            "指标", SemanticObjectType.MEASURE, "measure"
        )
        assert result.status == GroundingStatus.CONFIG_CONFLICT

    def test_absent_slot_is_not_mentioned_without_committed_state(self):
        result = ObjectGrounder(_catalog()).find_mentions(
            "换成 Furniture", SemanticObjectType.MEASURE, "measure"
        )
        assert result.status == GroundingStatus.NOT_MENTIONED
        assert result.canonical_object is None


class TestMemberAndTimeGrounding:
    def test_member_exact_normalized_ambiguous_and_unresolved(self):
        field = next(
            item for item in _catalog().objects if item.canonical_name == "Category"
        )
        members = ColumnMembersResult(
            semantic_model_key="local_desktop_model",
            table_name="Sales",
            field_name="Category",
            values=["Electronics", "Ｆｕｒｎｉｔｕｒｅ"],
            source_mode="real",
        )
        assert MemberGrounder.resolve(field, "Electronics", members).method == "runtime_exact"
        normalized = MemberGrounder.resolve(field, "furniture", members)
        assert normalized.canonical_value == "Ｆｕｒｎｉｔｕｒｅ"
        duplicate = members.model_copy(update={"values": ["North", "Ｎｏｒｔｈ"]})
        assert MemberGrounder.resolve(field, "north", duplicate).status == GroundingStatus.AMBIGUOUS
        assert MemberGrounder.resolve(field, "missing", members).status == GroundingStatus.UNRESOLVED

    def test_structured_time_uses_fixed_clock(self):
        field = next(
            item for item in _catalog().objects if item.canonical_name == "OrderDate"
        )
        grounder = TimeGrounder(lambda: date(2026, 8, 13))
        month = grounder.ground("本月", field)
        year = grounder.ground("今年", field)
        recent = grounder.ground("最近3个月", field)
        explicit = grounder.ground("2026-01-02 到 2026-02-03", field)
        assert (month.start_date, month.end_date) == (
            date(2026, 8, 1), date(2026, 8, 31)
        )
        assert (year.start_date, year.end_date) == (
            date(2026, 1, 1), date(2026, 12, 31)
        )
        assert (recent.start_date, recent.end_date) == (
            date(2026, 6, 1), date(2026, 8, 31)
        )
        assert explicit.mode == TimeRangeMode.EXPLICIT_RANGE
        assert '"date_field":"OrderDate"' in explicit.to_context_text()

    @pytest.mark.asyncio
    async def test_ambiguous_date_fields_require_clarification(self):
        glossary = _glossary()
        glossary["fields"]["ShipDate"] = {
            "table_name": "Sales", "object_type": "field", "aliases": ["发货日期"]
        }
        catalog = SemanticCatalogBuilder().build_from_data(
            _schema(two_dates=True), glossary
        )

        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(
            catalog, today=lambda: date(2026, 8, 13)
        ).ground(
            "今年销售额",
            _intent(detected_measures=["销量"]),
            _draft(measures=["Total Quantity"]),
            None,
            no_lookup,
        )
        assert outcome.status == GroundingStatus.AMBIGUOUS
        assert outcome.delta is None


class TestGroundingAuthorityAndStateTransition:
    @pytest.mark.asyncio
    async def test_current_measure_signal_uses_bounded_candidate_selection(self):
        class SelectorProvider(LLMProvider):
            @property
            def provider_name(self):
                return "selector-fake"

            @property
            def is_mock(self):
                return False

            async def generate(self, request, output_type):
                assert output_type is CandidateSelection
                assert "Total Quantity" in str(request.messages)
                assert "JSON" in str(request.messages)
                return LLMResponse(
                    content="{}",
                    structured=CandidateSelection(
                        outcome="RESOLVED",
                        candidate_id="measure:Sales:Total Quantity",
                    ),
                    model="selector-fake",
                )

        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(
            _catalog(),
            selector=BoundedLLMObjectSelector(SelectorProvider()),
        ).ground(
            "总共卖了多少件商品",
            _intent(detected_measures=["销售件数"]),
            _draft(measures=["Total Quantity"]),
            None,
            no_lookup,
        )
        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.measures == ["Total Quantity"]
        assert outcome.object_results[0].method == "bounded_llm"

    @pytest.mark.asyncio
    async def test_current_grounding_wins_over_wrong_intent(self):
        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "那销量呢",
            _intent(detected_measures=["销售额"]),
            _draft(measures=["Total Sales"]),
            StructuredWorkMemory(
                state_status=MemoryStatus.COMMITTED,
                measures=["Total Sales"],
            ),
            no_lookup,
        )
        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.measures == ["Total Quantity"]
        assert outcome.intent_disagreements == [
            "intent_measure_disagrees_with_grounding"
        ]

    @pytest.mark.asyncio
    async def test_filter_member_replacement_is_runtime_grounded(self):
        calls = 0

        async def lookup(field, limit):
            nonlocal calls
            calls += 1
            assert field.canonical_name == "Category"
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Category",
                values=["Electronics", "Furniture"],
                source_mode="real",
            )

        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            filters=[{"field": "Category", "operator": "eq", "value": "Electronics"}],
        )
        outcome = await SemanticGroundingService(_catalog()).ground(
            "换成 Furniture",
            _intent(detected_measures=["Total Sales"]),
            _draft(
                measures=["Total Sales"],
                filters=[StructuredFilter(field="Category", value="Furniture")],
            ),
            committed,
            lookup,
        )
        transition = StateTransitionService().merge(
            _draft(), outcome.delta, committed
        )
        assert calls == 1
        assert transition.query_plan.filters[0].value == "Furniture"
        assert transition.transitions.filters == [
            FilterTransition.REPLACE_SAME_FIELD
        ]
        assert outcome.object_results[0].status == GroundingStatus.NOT_MENTIONED
        assert transition.transitions.measure == SlotTransition.KEEP

    @pytest.mark.asyncio
    async def test_member_only_filter_uses_unique_committed_dimension(self):
        async def lookup(field, limit):
            assert field.canonical_name == "Category"
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Category",
                values=["North", "South"],
                source_mode="real",
            )

        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Category"],
        )
        outcome = await SemanticGroundingService(_catalog()).ground(
            "只看 North",
            _intent(detected_measures=["Total Sales"]),
            _draft(
                measures=["Total Sales"],
                filters=[StructuredFilter(field="Category", value="North")],
            ),
            committed,
            lookup,
        )
        transition = StateTransitionService().merge(_draft(), outcome.delta, committed)

        assert outcome.status == GroundingStatus.RESOLVED
        assert transition.query_plan.filters == [
            StructuredFilter(field="Category", value="North")
        ]
        assert transition.transitions.measure == SlotTransition.KEEP
        assert transition.transitions.filters == [FilterTransition.ADD]

    @pytest.mark.asyncio
    async def test_dimension_only_switch_keeps_measure(self):
        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Category"],
        )
        outcome = await SemanticGroundingService(_catalog()).ground(
            "改成按产品看",
            _intent(detected_dimensions=["产品"]),
            _draft(dimensions=["Product"]),
            committed,
            no_lookup,
        )
        transition = StateTransitionService().merge(_draft(), outcome.delta, committed)
        assert transition.query_plan.measures == ["Total Sales"]
        assert transition.query_plan.dimensions == ["Product"]
        assert transition.transitions.measure == SlotTransition.KEEP
        assert transition.transitions.dimension == SlotTransition.REPLACE

    @pytest.mark.asyncio
    async def test_measure_only_switch_keeps_dimension(self):
        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Product"],
        )
        outcome = await SemanticGroundingService(_catalog()).ground(
            "那销量呢",
            _intent(detected_measures=["销量"]),
            _draft(measures=["Total Quantity"]),
            committed,
            no_lookup,
        )
        transition = StateTransitionService().merge(_draft(), outcome.delta, committed)
        assert transition.query_plan.measures == ["Total Quantity"]
        assert transition.query_plan.dimensions == ["Product"]
        assert transition.transitions.measure == SlotTransition.REPLACE
        assert transition.transitions.dimension == SlotTransition.KEEP

    @pytest.mark.asyncio
    async def test_time_only_switch_keeps_measure_and_dimension(self):
        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Product"],
        )
        outcome = await SemanticGroundingService(
            _catalog(), today=lambda: date(2026, 8, 13)
        ).ground(
            "改成今年",
            _intent(detected_time_range="今年"),
            _draft(time_range="今年"),
            committed,
            no_lookup,
        )
        transition = StateTransitionService().merge(_draft(), outcome.delta, committed)
        assert transition.query_plan.measures == ["Total Sales"]
        assert transition.query_plan.dimensions == ["Product"]
        assert transition.query_plan.time_range.mode == TimeRangeMode.CURRENT_YEAR
        assert transition.transitions.measure == SlotTransition.KEEP
        assert transition.transitions.dimension == SlotTransition.KEEP
        assert transition.transitions.time == SlotTransition.REPLACE

    @pytest.mark.asyncio
    async def test_mentioned_unknown_measure_requires_clarification(self):
        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "看一下利润",
            _intent(detected_measures=["利润"]),
            _draft(),
            None,
            no_lookup,
        )
        assert outcome.status == GroundingStatus.UNRESOLVED
        assert outcome.delta is None

    @pytest.mark.asyncio
    async def test_mentioned_ambiguous_measure_requires_clarification(self):
        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["业绩"]
        glossary["measures"]["Total Quantity"]["aliases"] = ["业绩"]

        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(_catalog(glossary)).ground(
            "看一下业绩",
            _intent(detected_measures=["业绩"]),
            _draft(),
            None,
            no_lookup,
        )
        assert outcome.status == GroundingStatus.CONFIG_CONFLICT
        assert outcome.delta is None

    def test_explicit_switch_replace_and_absent_keep(self):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Category"],
        )
        replaced = StateTransitionService().merge(
            _draft(),
            GroundedSemanticDelta(
                measures=["Total Quantity"], dimensions=["Product"]
            ),
            committed,
        )
        kept = StateTransitionService().merge(
            _draft(), GroundedSemanticDelta(), committed
        )
        assert replaced.transitions.measure == SlotTransition.REPLACE
        assert replaced.transitions.dimension == SlotTransition.REPLACE
        assert replaced.query_plan.measures == ["Total Quantity"]
        assert kept.transitions.measure == SlotTransition.KEEP
        assert kept.query_plan.measures == ["Total Sales"]

        same = StateTransitionService().merge(
            _draft(),
            GroundedSemanticDelta(
                measures=["Total Sales"], dimensions=["Category"]
            ),
            committed,
        )
        assert same.transitions.measure == SlotTransition.KEEP
        assert same.transitions.dimension == SlotTransition.KEEP

    @pytest.mark.asyncio
    async def test_invented_intent_filter_value_is_not_grounded(self):
        async def no_lookup(*_):
            raise AssertionError("invented member must not reach runtime lookup")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "看销售额",
            _intent(
                detected_measures=["销售额"],
                detected_filters=[{
                    "field": "Category", "operator": "eq", "value": "Invented"
                }],
            ),
            _draft(measures=["Total Sales"]),
            None,
            no_lookup,
        )
        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.filters is None

    @pytest.mark.asyncio
    async def test_draft_filter_field_not_in_current_input_is_not_authority(self):
        async def no_lookup(*_):
            raise AssertionError("unmentioned filter field must not reach member lookup")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "只看 Furniture 的销售额",
            _intent(detected_measures=["销售额"]),
            _draft(
                measures=["Total Sales"],
                filters=[StructuredFilter(field="Product", value="Furniture")],
            ),
            None,
            no_lookup,
        )
        assert outcome.status == GroundingStatus.NOT_MENTIONED
        assert outcome.delta is None
        assert outcome.clarification_question == "请明确要筛选的字段。"

    @pytest.mark.asyncio
    async def test_unresolved_member_produces_no_delta_to_commit(self):
        async def lookup(field, limit):
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name=field.table_name,
                field_name=field.canonical_name,
                values=["Electronics"],
                source_mode="real",
            )

        outcome = await SemanticGroundingService(_catalog()).ground(
            "Missing 类别销售额",
            _intent(),
            _draft(
                measures=["Total Sales"],
                filters=[StructuredFilter(field="Category", value="Missing")],
            ),
            None,
            lookup,
        )
        assert outcome.status == GroundingStatus.UNRESOLVED
        assert outcome.delta is None
