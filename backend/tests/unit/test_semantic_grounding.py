"""Business semantic grounding invariants."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.memory.models import (
    MemoryStatus,
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.query_plan.clarification import PendingClarificationService
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector,
    CandidateSelection,
    GroundedSemanticDelta,
    GroundingOutcome,
    GroundingStatus,
    MemberGrounder,
    ObjectGroundingResult,
    ObjectGrounder,
    SemanticGroundingService,
    TimeGrounder,
)
from backend.app.llm.base import LLMProvider, LLMResponse
from backend.app.query_plan.semantic_catalog import (
    compute_schema_fingerprint,
    GlossaryCatalogError,
    SemanticCatalogBuilder,
    SemanticObjectType,
)
from backend.app.query_plan.state_transition import (
    CommittedMemoryCorruptionError,
    FilterTransition,
    SlotTransition,
    StateTransitionService,
)
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    ColumnSchema,
    MeasureSchema,
    QueryPlan,
    RelationshipSchema,
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
        "schema_fingerprint": compute_schema_fingerprint(_schema()),
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
    def test_schema_fingerprint_is_stable_across_order_and_descriptions(self):
        schema = _schema()
        reordered = schema.model_copy(deep=True)
        reordered.tables[0].columns.reverse()
        reordered.tables[0].measures.reverse()
        reordered.tables[0].description = "display-only change"
        reordered.tables[0].columns[0].description = "display-only change"
        assert compute_schema_fingerprint(schema) == compute_schema_fingerprint(
            reordered
        )

    @pytest.mark.parametrize("mutation", ["object", "type", "expression", "relationship"])
    def test_meaningful_schema_change_changes_fingerprint(self, mutation):
        schema = _schema()
        changed = schema.model_copy(deep=True)
        if mutation == "object":
            changed.tables[0].columns[0].name = "CategoryChanged"
        elif mutation == "type":
            changed.tables[0].columns[0].data_type = "Int64"
        elif mutation == "expression":
            changed.tables[0].measures[0].expression = "SUM('Sales'[Amount])"
        else:
            changed.tables.append(TableSchema(
                name="CategoryDim",
                columns=[ColumnSchema(name="Category", data_type="String")],
            ))
            changed.relationships.append(RelationshipSchema(
                from_table="Sales",
                from_column="Category",
                to_table="CategoryDim",
                to_column="Category",
                is_active=True,
            ))
        assert compute_schema_fingerprint(schema) != compute_schema_fingerprint(changed)

    def test_schema_fingerprint_drift_does_not_block_complete_contract(self):
        glossary = _glossary(schema_fingerprint="0" * 64)
        catalog = SemanticCatalogBuilder().build_from_data(_schema(), glossary)
        assert catalog.schema_drift is True
        assert catalog.schema_fingerprint == compute_schema_fingerprint(_schema())

    def test_correct_schema_fingerprint_passes(self):
        catalog = SemanticCatalogBuilder().build_from_data(_schema(), _glossary())
        assert catalog.schema_fingerprint == compute_schema_fingerprint(_schema())
        assert catalog.schema_drift is False

    def test_missing_required_measure_fails_business_contract(self):
        schema = _schema()
        schema.tables[0].measures = [
            item for item in schema.tables[0].measures if item.name != "Total Sales"
        ]
        with pytest.raises(GlossaryCatalogError, match="glossary_unknown_object"):
            SemanticCatalogBuilder().build_from_data(schema, _glossary())

    def test_missing_required_field_fails_business_contract(self):
        schema = _schema()
        schema.tables[0].columns = [
            item for item in schema.tables[0].columns if item.name != "Category"
        ]
        with pytest.raises(GlossaryCatalogError, match="glossary_unknown_object"):
            SemanticCatalogBuilder().build_from_data(schema, _glossary())

    def test_required_object_type_conflict_fails_business_contract(self):
        schema = _schema()
        schema.tables[0].measures = [
            item for item in schema.tables[0].measures if item.name != "Total Sales"
        ]
        schema.tables[0].columns.append(
            ColumnSchema(name="Total Sales", data_type="Double")
        )
        with pytest.raises(
            GlossaryCatalogError, match="glossary_object_type_mismatch"
        ):
            SemanticCatalogBuilder().build_from_data(schema, _glossary())

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

    def test_approved_quantity_question_alias_is_deterministic_mention(self):
        glossary = _glossary()
        glossary["measures"]["Total Quantity"]["aliases"].append("多少件")
        result = ObjectGrounder(_catalog(glossary)).find_mentions(
            "总共卖了多少件商品？",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.RESOLVED
        assert result.canonical_object.canonical_name == "Total Quantity"
        assert result.method == "current_input_mention"

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

    @pytest.mark.asyncio
    async def test_two_similar_measures_remain_ambiguous_despite_selector(self):
        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["净销售额"]
        glossary["measures"]["Total Quantity"]["aliases"] = ["净销售量"]
        provider = _SelectionProvider("measure:Sales:Total Sales")

        result = await ObjectGrounder(
            _catalog(glossary), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "净销售指标",
            "净销售指标",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.AMBIGUOUS
        assert result.method == "bounded_llm_evidence_tie"
        assert provider.calls == 0

    @pytest.mark.asyncio
    async def test_two_similar_dimensions_remain_ambiguous(self):
        glossary = _glossary()
        glossary["fields"]["Category"]["aliases"] = ["产品分类名称"]
        glossary["fields"]["Product"]["aliases"] = ["产品分类编码"]
        provider = _SelectionProvider("field:Sales:Category")

        result = await ObjectGrounder(
            _catalog(glossary), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "产品分类分析",
            "按产品分类分析",
            SemanticObjectType.FIELD,
            "dimension",
        )

        assert result.status == GroundingStatus.AMBIGUOUS
        assert provider.calls == 0

    @pytest.mark.asyncio
    async def test_unknown_phrase_never_receives_forced_catalog_choice(self):
        provider = _SelectionProvider("measure:Sales:Total Sales")
        result = await ObjectGrounder(
            _catalog(), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "客户幸福指数",
            "客户幸福指数是多少",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.UNRESOLVED
        assert result.method == "bounded_llm_no_metadata_evidence"
        assert provider.calls == 0

    @pytest.mark.asyncio
    async def test_partial_alias_evidence_can_bound_selection(self):
        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["净销售额"]
        provider = _SelectionProvider("measure:Sales:Total Sales")
        catalog = _catalog(glossary)

        result = await ObjectGrounder(
            catalog, BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "净销售表现",
            "净销售表现如何",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.RESOLVED
        assert result.canonical_object == catalog.get("measure:Sales:Total Sales")
        assert result.canonical_object.object_type == SemanticObjectType.MEASURE
        assert result.canonical_object.table_name == "Sales"
        assert provider.calls == 1

    @pytest.mark.asyncio
    async def test_selector_invalid_id_is_unresolved(self):
        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["净销售额"]
        provider = _SelectionProvider("measure:Other:Ghost")

        result = await ObjectGrounder(
            _catalog(glossary), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "净销售表现",
            "净销售表现如何",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.UNRESOLVED
        assert result.method == "bounded_llm_unknown_candidate"

    @pytest.mark.asyncio
    async def test_exact_alias_wins_without_selector_call(self):
        provider = _SelectionProvider("measure:Sales:Total Sales")
        result = ObjectGrounder(
            _catalog(), BoundedLLMObjectSelector(provider)
        ).resolve_phrase("销量", SemanticObjectType.MEASURE, "measure")

        assert result.status == GroundingStatus.RESOLVED
        assert result.canonical_object.canonical_name == "Total Quantity"
        assert provider.calls == 0

    @pytest.mark.asyncio
    async def test_selector_cannot_override_stronger_metadata_candidate(self):
        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["净销售额"]
        glossary["measures"]["Total Quantity"]["aliases"] = ["净销售量"]
        provider = _SelectionProvider("measure:Sales:Total Quantity")

        result = await ObjectGrounder(
            _catalog(glossary), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "净销售额表现",
            "净销售额表现",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.AMBIGUOUS
        assert result.method == "bounded_llm_conflicts_with_metadata_evidence"


class _SelectionProvider(LLMProvider):
    def __init__(self, candidate_id: str):
        self.candidate_id = candidate_id
        self.calls = 0

    @property
    def provider_name(self):
        return "selector-adversarial"

    @property
    def is_mock(self):
        return False

    async def generate(self, request, output_type):
        self.calls += 1
        assert output_type is CandidateSelection
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(
                outcome="RESOLVED", candidate_id=self.candidate_id
            ),
            model="selector-adversarial",
        )


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
        previous_year = grounder.ground("改成去年", field)
        recent = grounder.ground("最近3个月", field)
        explicit = grounder.ground("2026-01-02 到 2026-02-03", field)
        assert (month.start_date, month.end_date) == (
            date(2026, 8, 1), date(2026, 8, 31)
        )
        assert (year.start_date, year.end_date) == (
            date(2026, 1, 1), date(2026, 12, 31)
        )
        assert (previous_year.start_date, previous_year.end_date) == (
            date(2025, 1, 1), date(2025, 12, 31)
        )
        assert previous_year.mode == TimeRangeMode.EXPLICIT_RANGE
        assert (recent.start_date, recent.end_date) == (
            date(2026, 6, 1), date(2026, 8, 31)
        )
        assert explicit.mode == TimeRangeMode.EXPLICIT_RANGE
        assert '"date_field":"OrderDate"' in explicit.to_context_text()

    @pytest.mark.asyncio
    async def test_runtime_only_extra_date_does_not_override_glossary_date(self):
        schema = _schema(two_dates=True)
        catalog = SemanticCatalogBuilder().build_from_data(schema, _glossary())

        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(
            catalog, today=lambda: date(2026, 8, 13)
        ).ground(
            "本月销售额是多少？",
            _intent(detected_measures=["销售额"], detected_time_range="本月"),
            _draft(measures=["Total Sales"], time_range="本月"),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.time_range is not None
        assert outcome.delta.time_range.date_field == "OrderDate"

    @pytest.mark.asyncio
    async def test_glossary_owner_becomes_canonical_dimension_table_hint(self):
        schema = _schema()
        schema.tables[0].columns.append(
            ColumnSchema(name="Region", data_type="String")
        )
        schema.tables.append(
            TableSchema(
                name="Region",
                columns=[ColumnSchema(name="Region", data_type="String")],
            )
        )
        glossary = _glossary()
        glossary["fields"]["Region"] = {
            "table_name": "Sales",
            "object_type": "field",
            "aliases": ["区域"],
            "member_aliases": {"华南": "South", "华东": "East"},
        }
        catalog = SemanticCatalogBuilder().build_from_data(schema, glossary)

        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(catalog).ground(
            "按区域列出销售额",
            _intent(detected_measures=["销售额"], detected_dimensions=["区域"]),
            _draft(measures=["Total Sales"], dimensions=["Region"]),
            None,
            no_lookup,
        )
        transition = StateTransitionService().merge(
            _draft(), outcome.delta, None
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.dimension_tables == {"Region": "Sales"}
        assert transition.query_plan.dimension_tables == {"Region": "Sales"}

    @pytest.mark.asyncio
    async def test_member_refinement_reuses_committed_glossary_owner_hint(self):
        schema = _schema()
        schema.tables[0].columns.append(
            ColumnSchema(name="Region", data_type="String")
        )
        schema.tables.append(
            TableSchema(
                name="Region",
                columns=[ColumnSchema(name="Region", data_type="String")],
            )
        )
        glossary = _glossary()
        glossary["fields"]["Region"] = {
            "table_name": "Sales",
            "object_type": "field",
            "aliases": ["区域"],
            "member_aliases": {"华南": "South", "华东": "East"},
        }
        catalog = SemanticCatalogBuilder().build_from_data(schema, glossary)
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Region"],
            last_query_plan={"dimension_tables": {"Region": "Sales"}},
        )

        async def lookup(field, limit):
            assert field.table_name == "Sales"
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Region",
                values=["South", "East"],
                source_mode="real",
            )

        outcome = await SemanticGroundingService(catalog).ground(
            "只看华南",
            _intent(),
            _draft(),
            committed,
            lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.filters == [
            StructuredFilter(field="Region", value="South")
        ]
        assert outcome.delta.dimension_tables == {"Region": "Sales"}

    @pytest.mark.asyncio
    async def test_draft_filter_reuses_committed_glossary_owner_hint(self):
        schema = _schema()
        schema.tables[0].columns.append(
            ColumnSchema(name="Region", data_type="String")
        )
        schema.tables.append(
            TableSchema(
                name="Region",
                columns=[ColumnSchema(name="Region", data_type="String")],
            )
        )
        glossary = _glossary()
        glossary["fields"]["Region"] = {
            "table_name": "Sales",
            "object_type": "field",
            "aliases": ["区域"],
            "member_aliases": {"华南": "South", "华东": "East"},
        }
        catalog = SemanticCatalogBuilder().build_from_data(schema, glossary)
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Region"],
            last_query_plan={"dimension_tables": {"Region": "Sales"}},
        )

        async def lookup(field, limit):
            assert field.table_name == "Sales"
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Region",
                values=["South", "East"],
                source_mode="real",
            )

        outcome = await SemanticGroundingService(catalog).ground(
            "只看华南",
            _intent(),
            _draft(filters=[StructuredFilter(field="Region", value="华南")]),
            committed,
            lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.filters == [
            StructuredFilter(field="Region", value="South")
        ]
        assert outcome.delta.dimension_tables == {"Region": "Sales"}

    def test_committed_dimension_table_hint_is_inherited(self):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Region"],
            last_query_plan={"dimension_tables": {"Region": "Sales"}},
        )

        transition = StateTransitionService().merge(
            _draft(), GroundedSemanticDelta(), committed
        )

        assert transition.query_plan.dimension_tables == {"Region": "Sales"}

    @pytest.mark.asyncio
    async def test_ambiguous_date_fields_require_clarification(self):
        schema = _schema(two_dates=True)
        glossary = _glossary()
        glossary["schema_fingerprint"] = compute_schema_fingerprint(schema)
        glossary["fields"]["ShipDate"] = {
            "table_name": "Sales", "object_type": "field", "aliases": ["发货日期"]
        }
        catalog = SemanticCatalogBuilder().build_from_data(
            schema, glossary
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
    async def test_explicit_grouping_cue_discards_hallucinated_draft_filter(self):
        async def no_lookup(*_):
            raise AssertionError("grouping field must not trigger member lookup")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "按产品看销售额",
            _intent(detected_measures=["Total Sales"]),
            _draft(
                measures=["Total Sales"],
                dimensions=["Product"],
                filters=[StructuredFilter(field="Product", value="产品")],
            ),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.measures == ["Total Sales"]
        assert outcome.delta.dimensions == ["Product"]
        assert outcome.delta.filters is None

    @pytest.mark.asyncio
    async def test_runtime_member_discovers_filter_when_weak_draft_omits_it(self):
        calls: list[str] = []

        async def lookup(field, limit):
            calls.append(field.canonical_name)
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name=field.canonical_name,
                values=["Electronics", "Furniture"],
                source_mode="real",
            )

        outcome = await SemanticGroundingService(_catalog()).ground(
            "Electronics 类别中销量最高的前3个产品是什么？",
            _intent(),
            _draft(),
            None,
            lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.measures == ["Total Quantity"]
        assert outcome.delta.dimensions == ["Product"]
        assert outcome.delta.filters == [
            StructuredFilter(field="Category", value="Electronics")
        ]
        assert outcome.delta.sort == "desc"
        assert outcome.delta.top_n == 3
        assert calls == ["Category"]

    @pytest.mark.asyncio
    async def test_filter_role_excludes_explicit_grouping_candidate(self):
        async def lookup(field, limit):
            assert field.canonical_name == "Category"
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Category",
                values=["Electronics", "Furniture"],
                source_mode="real",
            )

        outcome = await SemanticGroundingService(_catalog()).ground(
            "Electronics 类别中销量最高的前3个产品是什么？",
            _intent(),
            _draft(filters=[
                StructuredFilter(field="Category", value="Electronics")
            ]),
            None,
            lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.dimensions == ["Product"]
        assert outcome.delta.filters == [
            StructuredFilter(field="Category", value="Electronics")
        ]

    @pytest.mark.asyncio
    async def test_member_only_refinement_uses_committed_single_field(self):
        async def lookup(field, limit):
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
            dimensions=["Category"],
        )
        outcome = await SemanticGroundingService(_catalog()).ground(
            "只看 Electronics",
            _intent(),
            _draft(),
            committed,
            lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.filters == [
            StructuredFilter(field="Category", value="Electronics")
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("slot", ["dimension", "filter", "time"])
    async def test_intent_clarification_cannot_preempt_authoritative_slots(self, slot):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
        )
        intent = _intent(
            intent=IntentType.CLARIFICATION,
            needs_clarification=True,
            clarification_question="intent diagnostic only",
        )

        async def lookup(field, limit):
            assert field.canonical_name == "Category"
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Category",
                values=["Furniture"],
                source_mode="real",
            )

        if slot == "dimension":
            outcome = await SemanticGroundingService(_catalog()).ground(
                "改成按产品看", intent, _draft(dimensions=["Product"]),
                committed, lookup,
            )
            assert outcome.delta.dimensions == ["Product"]
        elif slot == "filter":
            outcome = await SemanticGroundingService(_catalog()).ground(
                "只看 Furniture 类别",
                intent,
                _draft(filters=[StructuredFilter(field="Category", value="Furniture")]),
                committed,
                lookup,
            )
            assert outcome.delta.filters == [
                StructuredFilter(field="Category", value="Furniture")
            ]
        else:
            outcome = await SemanticGroundingService(
                _catalog(), today=lambda: date(2026, 8, 13)
            ).ground("改成今年", intent, _draft(time_range="今年"), committed, lookup)
            assert outcome.delta.time_range.mode == TimeRangeMode.CURRENT_YEAR
        assert outcome.status == GroundingStatus.RESOLVED

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
                assert "Total Sales" in str(request.messages)
                assert "JSON" in str(request.messages)
                return LLMResponse(
                    content="{}",
                    structured=CandidateSelection(
                        outcome="RESOLVED",
                        candidate_id="measure:Sales:Total Sales",
                    ),
                    model="selector-fake",
                )

        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["净销售额"]
        outcome = await SemanticGroundingService(
            _catalog(glossary),
            selector=BoundedLLMObjectSelector(SelectorProvider()),
        ).ground(
            "净销售表现如何",
            _intent(detected_measures=["净销售表现"]),
            _draft(measures=["Total Sales"]),
            None,
            no_lookup,
        )
        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.measures == ["Total Sales"]
        assert outcome.object_results[0].method == "bounded_llm"

    @pytest.mark.asyncio
    async def test_unsupported_comparison_is_non_persistable_clarification(self):
        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "销售额同比去年如何",
            _intent(detected_measures=["Total Sales"]),
            _draft(measures=["Total Sales"]),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.UNRESOLVED
        assert outcome.pending_eligible is False
        assert "尚未支持" in outcome.clarification_question

    @pytest.mark.asyncio
    async def test_unsupported_filter_operator_is_non_persistable(self):
        async def no_lookup(*_):
            raise AssertionError("unsupported operator must stop before member lookup")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "销售额中类别包含 Furniture",
            _intent(detected_measures=["Total Sales"]),
            _draft(
                measures=["Total Sales"],
                filters=[StructuredFilter(
                    field="Category",
                    operator="contains",
                    value="Furniture",
                )],
            ),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.UNRESOLVED
        assert outcome.pending_eligible is False
        assert "仅支持等值筛选" in outcome.clarification_question

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

    def test_valid_committed_filter_is_inherited(self):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            filters=[{
                "field": "Category",
                "operator": "eq",
                "value": "Electronics",
            }],
        )

        result = StateTransitionService().merge(
            _draft(), GroundedSemanticDelta(), committed
        )

        assert result.query_plan.filters == [
            StructuredFilter(field="Category", value="Electronics")
        ]
        assert result.transitions.filters == [FilterTransition.KEEP]

    @pytest.mark.parametrize(
        "runtime_mode", [RuntimeDataMode.MOCK, RuntimeDataMode.REAL]
    )
    def test_malformed_committed_filter_fails_closed_in_all_runtime_modes(
        self, runtime_mode
    ):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            runtime_mode=runtime_mode,
            measures=["Total Sales"],
        )
        # Simulate corruption after initial domain validation.  The transition
        # boundary must never reinterpret this as an empty committed filter.
        committed.filters = [{"operator": "eq"}]

        with pytest.raises(
            CommittedMemoryCorruptionError,
            match="committed_memory_filter_invalid",
        ):
            StateTransitionService().merge(
                _draft(), GroundedSemanticDelta(), committed
            )

    def test_corrupt_committed_time_range_fails_closed_before_transition(self):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
        )
        # Simulate process-local corruption after initial domain validation.
        committed.time_range = {"date_field": "OrderDate"}

        with pytest.raises(
            CommittedMemoryCorruptionError,
            match="committed_memory_time_range_invalid",
        ):
            StateTransitionService().merge(
                _draft(), GroundedSemanticDelta(), committed
            )

    def test_llm_template_draft_never_crosses_state_transition(self):
        draft = _draft(requested_template="sales_weekly")
        without_grounding = StateTransitionService().merge(
            draft, GroundedSemanticDelta(measures=["Total Sales"]), None
        )
        grounded = StateTransitionService().merge(
            draft,
            GroundedSemanticDelta(measures=["Total Sales"]),
            None,
            canonical_template_key="operating_overview",
        )
        assert without_grounding.query_plan.requested_template is None
        assert grounded.query_plan.requested_template == "operating_overview"

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


class TestPendingClarificationContract:
    @staticmethod
    def _resolved(role: str, canonical_name: str) -> ObjectGroundingResult:
        object_type = (
            SemanticObjectType.MEASURE
            if role == "measure"
            else SemanticObjectType.FIELD
        )
        canonical = next(
            item
            for item in _catalog().by_type(object_type)
            if item.canonical_name == canonical_name
        )
        return ObjectGroundingResult(
            status=GroundingStatus.RESOLVED,
            role=role,
            phrase=canonical_name,
            canonical_object=canonical,
            method="canonical_exact",
        )

    @staticmethod
    def _merge(
        previous: PendingClarificationContext | None,
        outcome: GroundingOutcome,
        message: str,
        request_id: str,
    ):
        return PendingClarificationService().merge(
            previous=previous,
            outcome=outcome,
            user_input=message,
            conversation_id="clarification-chain",
            request_id=request_id,
            semantic_model_key="local_desktop_model",
            schema_fingerprint=compute_schema_fingerprint(_schema()),
            runtime_mode=RuntimeDataMode.REAL,
            intent="data_question",
            committed=None,
        )

    def test_partial_slots_accumulate_without_becoming_executable(self):
        first = self._merge(
            None,
            GroundingOutcome(status=GroundingStatus.NOT_MENTIONED),
            "哪个表现最好？",
            "e1",
        )
        assert not first.complete
        assert first.executable_delta is None
        assert first.context.measures == []
        assert first.context.dimensions == []
        assert first.context.sort == "desc"
        assert first.context.top_n == 1
        assert first.context.missing_slots == ["measure", "dimension"]

        second = self._merge(
            first.context,
            GroundingOutcome(
                status=GroundingStatus.RESOLVED,
                delta=GroundedSemanticDelta(measures=["Total Sales"]),
                object_results=[self._resolved("measure", "Total Sales")],
            ),
            "按销售额",
            "e2",
        )
        assert not second.complete
        assert second.executable_delta is None
        assert second.context.chain_id == first.context.chain_id
        assert second.context.measures == ["Total Sales"]
        assert second.context.missing_slots == ["dimension"]

        third = self._merge(
            second.context,
            GroundingOutcome(
                status=GroundingStatus.RESOLVED,
                delta=GroundedSemanticDelta(dimensions=["Product"]),
                object_results=[self._resolved("dimension", "Product")],
            ),
            "按产品",
            "e3",
        )
        assert third.complete
        assert third.context.missing_slots == []
        assert third.executable_delta is not None
        assert third.executable_delta.measures == ["Total Sales"]
        assert third.executable_delta.dimensions == ["Product"]
        assert third.executable_delta.sort == "desc"
        assert third.executable_delta.top_n == 1

    def test_current_explicit_semantic_overrides_pending_slot(self):
        previous = PendingClarificationContext(
            conversation_id="clarification-chain",
            semantic_model_key="local_desktop_model",
            schema_fingerprint=compute_schema_fingerprint(_schema()),
            measures=["Total Sales"],
            missing_slots=["dimension"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="before",
        )
        merged = self._merge(
            previous,
            GroundingOutcome(
                status=GroundingStatus.RESOLVED,
                delta=GroundedSemanticDelta(
                    measures=["Total Quantity"], dimensions=["Product"]
                ),
                object_results=[
                    self._resolved("measure", "Total Quantity"),
                    self._resolved("dimension", "Product"),
                ],
            ),
            "改成按产品看销量",
            "override",
        )
        assert merged.complete
        assert merged.context.measures == ["Total Quantity"]
        assert merged.context.dimensions == ["Product"]

    def test_ambiguity_remains_non_executable(self):
        previous = PendingClarificationContext(
            conversation_id="clarification-chain",
            semantic_model_key="local_desktop_model",
            schema_fingerprint=compute_schema_fingerprint(_schema()),
            measures=["Total Sales"],
            dimensions=["Product"],
            sort="desc",
            top_n=1,
            missing_slots=["dimension"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="before",
        )
        ambiguous = ObjectGroundingResult(
            status=GroundingStatus.AMBIGUOUS,
            role="dimension",
            phrase="产品还是类别",
            candidate_ids=("field:Sales.Product", "field:Sales.Category"),
            method="multiple_signals",
        )
        merged = self._merge(
            previous,
            GroundingOutcome(
                status=GroundingStatus.AMBIGUOUS,
                object_results=[ambiguous],
                clarification_question="请明确唯一维度。",
            ),
            "按产品还是类别",
            "ambiguous",
        )
        assert not merged.complete
        assert merged.executable_delta is None
        assert merged.context.dimensions == []
        assert merged.context.missing_slots == ["dimension"]

        next_partial = self._merge(
            merged.context,
            GroundingOutcome(
                status=GroundingStatus.RESOLVED,
                delta=GroundedSemanticDelta(measures=["Total Quantity"]),
                object_results=[self._resolved("measure", "Total Quantity")],
            ),
            "改成销量",
            "after-ambiguous",
        )
        assert not next_partial.complete
        assert next_partial.context.measures == ["Total Quantity"]
        assert next_partial.context.dimensions == []
        assert next_partial.context.missing_slots == ["dimension"]

    def test_standalone_scalar_question_discards_unfinished_ranking(self):
        previous = PendingClarificationContext(
            conversation_id="clarification-chain",
            semantic_model_key="local_desktop_model",
            schema_fingerprint=compute_schema_fingerprint(_schema()),
            sort="desc",
            top_n=1,
            missing_slots=["measure", "dimension"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="ranking",
        )
        merged = self._merge(
            previous,
            GroundingOutcome(
                status=GroundingStatus.RESOLVED,
                delta=GroundedSemanticDelta(measures=["Total Sales"]),
                object_results=[self._resolved("measure", "Total Sales")],
            ),
            "总销售额是多少？",
            "independent-scalar",
        )
        assert merged.complete
        assert merged.context.measures == ["Total Sales"]
        assert merged.context.dimensions == []
        assert merged.context.sort is None
        assert merged.context.top_n is None

    def test_explicit_abandonment_terms_are_narrow(self):
        assert PendingClarificationService.should_abandon("取消澄清，重新开始")
        assert not PendingClarificationService.should_abandon("按产品")
