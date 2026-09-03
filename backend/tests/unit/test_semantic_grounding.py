"""Business semantic grounding invariants."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.intent.models import (
    IntentSpec,
    IntentType,
    TimeIntentDraft,
    TimeIntentKind,
    TurnRelation,
)
from backend.app.intent.question_router import QuestionRouter
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
    InheritanceMode,
    SlotTransition,
    StateTransitionService,
    TurnInheritancePolicy,
)
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    ColumnSchema,
    MeasureSchema,
    QueryPlan,
    QueryShape,
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


def _rich_temporal_schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="Rich Local",
        key="local_desktop_model",
        tables=[
            TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="Category", data_type="String"),
                    ColumnSchema(name="Product", data_type="String"),
                    ColumnSchema(name="OrderDate", data_type="DateTime"),
                ],
                measures=[
                    MeasureSchema(name="Total Sales", data_type="Double"),
                    MeasureSchema(name="Total Quantity", data_type="Int64"),
                ],
            ),
            TableSchema(
                name="Date",
                columns=[
                    ColumnSchema(name="Date", data_type="DateTime"),
                    ColumnSchema(name="YearMonth", data_type="DateTime"),
                ],
            ),
        ],
        relationships=[RelationshipSchema(
            from_table="Sales",
            from_column="OrderDate",
            to_table="Date",
            to_column="Date",
            is_active=True,
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

    def test_server_owned_instance_key_can_use_explicit_glossary_scope(self):
        opaque_key = "local_desktop:" + "a" * 64
        schema = _schema().model_copy(update={
            "key": opaque_key,
            "name": opaque_key,
        })
        glossary = _glossary(semantic_model_key="local_desktop_model")

        with pytest.raises(
            GlossaryCatalogError, match="glossary_semantic_model_key_mismatch"
        ):
            SemanticCatalogBuilder().build_from_data(schema, glossary)

        catalog = SemanticCatalogBuilder().build_from_data(
            schema,
            glossary,
            glossary_scope_key="local_desktop_model",
        )

        assert catalog.semantic_model_key == opaque_key

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
    async def test_two_similar_measures_preserve_selector_abstention(self):
        glossary = _glossary()
        glossary["measures"]["Total Sales"]["aliases"] = ["净销售额"]
        glossary["measures"]["Total Quantity"]["aliases"] = ["净销售量"]
        provider = _SelectionProvider(None, "AMBIGUOUS")

        result = await ObjectGrounder(
            _catalog(glossary), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "净销售指标",
            "净销售指标",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.AMBIGUOUS
        assert result.canonical_object is None
        assert provider.calls == 1

    @pytest.mark.asyncio
    async def test_two_similar_dimensions_remain_ambiguous(self):
        glossary = _glossary()
        glossary["fields"]["Category"]["aliases"] = ["产品分类名称"]
        glossary["fields"]["Product"]["aliases"] = ["产品分类编码"]
        provider = _SelectionProvider(None, "AMBIGUOUS")

        result = await ObjectGrounder(
            _catalog(glossary), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "产品分类分析",
            "按产品分类分析",
            SemanticObjectType.FIELD,
            "dimension",
        )

        assert result.status == GroundingStatus.AMBIGUOUS
        assert result.canonical_object is None
        assert provider.calls == 1

    @pytest.mark.asyncio
    async def test_unknown_phrase_never_receives_forced_catalog_choice(self):
        provider = _SelectionProvider(None, "UNRESOLVED")
        result = await ObjectGrounder(
            _catalog(), BoundedLLMObjectSelector(provider)
        ).select_bounded(
            "客户幸福指数",
            "客户幸福指数是多少",
            SemanticObjectType.MEASURE,
            "measure",
        )

        assert result.status == GroundingStatus.UNRESOLVED
        assert result.canonical_object is None
        assert provider.calls == 1

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

        assert result.status == GroundingStatus.RESOLVED
        assert result.canonical_object.canonical_name == "Total Sales"
        assert provider.calls == 0


class _SelectionProvider(LLMProvider):
    def __init__(self, candidate_id: str | None, outcome="RESOLVED"):
        self.candidate_id = candidate_id
        self.outcome = outcome
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
                outcome=self.outcome, candidate_id=self.candidate_id
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

    @pytest.mark.parametrize(
        ("phrase", "expected_start", "expected_end"),
        [
            ("2025年5月销售额", date(2025, 5, 1), date(2025, 5, 31)),
            ("2025年5月份销售额", date(2025, 5, 1), date(2025, 5, 31)),
            ("2025-05 销售额", date(2025, 5, 1), date(2025, 5, 31)),
            ("去年五月", date(2025, 5, 1), date(2025, 5, 31)),
            ("今年5月", date(2026, 5, 1), date(2026, 5, 31)),
            ("上月", date(2026, 7, 1), date(2026, 7, 31)),
            ("上个月", date(2026, 7, 1), date(2026, 7, 31)),
            ("最近半年", date(2026, 3, 1), date(2026, 8, 31)),
            ("今年第一季度", date(2026, 1, 1), date(2026, 3, 31)),
            ("2025年Q1", date(2025, 1, 1), date(2025, 3, 31)),
            ("２０２５年５月份", date(2025, 5, 1), date(2025, 5, 31)),
        ],
    )
    def test_time_fast_path_covers_stable_structures(
        self, phrase, expected_start, expected_end
    ):
        field = next(
            item for item in _catalog().objects if item.canonical_name == "OrderDate"
        )
        result = TimeGrounder(lambda: date(2026, 8, 13)).ground(phrase, field)
        assert result is not None
        assert (result.start_date, result.end_date) == (expected_start, expected_end)

    @pytest.mark.parametrize(
        "phrase",
        [
            "2025年5月份销售额",
            "2025-05 销售额",
            "今年5月",
            "上月",
            "2025年Q1",
            "２０２５年５月份",
        ],
    )
    def test_time_fast_path_marks_supported_variants_explicit(self, phrase):
        assert TimeGrounder.is_explicit(phrase)

    def test_bounded_time_draft_requires_current_input_evidence(self):
        field = next(
            item for item in _catalog().objects if item.canonical_name == "OrderDate"
        )
        grounder = TimeGrounder(lambda: date(2026, 8, 13))
        draft = TimeIntentDraft(
            kind=TimeIntentKind.RECENT_MONTHS,
            expression="过去六个月",
            months=6,
        )
        assert grounder.ground("过去六个月销售额", field, draft) is not None
        assert grounder.ground("销售额", field, draft) is None

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
    async def test_absolute_month_uses_metadata_bound_default_date_role(self, monkeypatch):
        from backend.tests.fixtures.model_overrides import activate_registry, bound_registry

        schema = _rich_temporal_schema()
        activate_registry(monkeypatch, bound_registry(schema, ["desktop_sales_language", "desktop_calendar_roles"]))
        catalog = SemanticCatalogBuilder().build(schema)

        async def no_lookup(*_):
            raise AssertionError("member lookup should not run")

        outcome = await SemanticGroundingService(
            catalog, today=lambda: date(2026, 8, 13)
        ).ground(
            "2025年5月销售额",
            _intent(
                detected_measures=["销售额"],
                detected_time_range="2025年5月",
            ),
            _draft(measures=["Total Sales"], time_range="2025年5月"),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.time_range is not None
        assert outcome.delta.time_range.date_field == "Date"
        assert outcome.delta.dimension_tables["Date"] == "Date"
        assert outcome.delta.time_range.start_date == date(2025, 5, 1)
        assert outcome.delta.time_range.end_date == date(2025, 5, 31)

    @pytest.mark.asyncio
    async def test_explicit_date_role_overrides_model_default(self):
        schema = _schema(two_dates=True)
        glossary = _glossary()
        glossary["schema_fingerprint"] = compute_schema_fingerprint(schema)
        glossary["fields"]["OrderDate"]["temporal_role"] = "default"
        glossary["fields"]["ShipDate"] = {
            "table_name": "Sales",
            "object_type": "field",
            "aliases": ["发货日期"],
        }
        catalog = SemanticCatalogBuilder().build_from_data(schema, glossary)

        async def no_lookup(*_):
            raise AssertionError("date role must not trigger member lookup")

        outcome = await SemanticGroundingService(
            catalog, today=lambda: date(2026, 8, 13)
        ).ground(
            "按发货日期看2025年5月销售额",
            _intent(detected_measures=["销售额"]),
            _draft(measures=["Total Sales"]),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.time_range is not None
        assert outcome.delta.time_range.date_field == "ShipDate"

    @pytest.mark.asyncio
    async def test_model_scoped_default_date_role_resolves_multiple_dates(self):
        schema = _schema(two_dates=True)
        glossary = _glossary()
        glossary["schema_fingerprint"] = compute_schema_fingerprint(schema)
        glossary["fields"]["OrderDate"]["temporal_role"] = "default"
        glossary["fields"]["ShipDate"] = {
            "table_name": "Sales",
            "object_type": "field",
            "aliases": ["发货日期"],
        }
        catalog = SemanticCatalogBuilder().build_from_data(schema, glossary)

        async def no_lookup(*_):
            raise AssertionError("date role must not trigger member lookup")

        outcome = await SemanticGroundingService(
            catalog, today=lambda: date(2026, 8, 13)
        ).ground(
            "2025年5月销售额",
            _intent(detected_measures=["销售额"]),
            _draft(measures=["Total Sales"]),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.time_range is not None
        assert outcome.delta.time_range.date_field == "OrderDate"

    def test_duplicate_model_default_date_roles_are_rejected(self):
        schema = _schema(two_dates=True)
        glossary = _glossary()
        glossary["schema_fingerprint"] = compute_schema_fingerprint(schema)
        glossary["fields"]["OrderDate"]["temporal_role"] = "default"
        glossary["fields"]["ShipDate"] = {
            "table_name": "Sales",
            "object_type": "field",
            "aliases": ["发货日期"],
            "temporal_role": "default",
        }

        with pytest.raises(
            GlossaryCatalogError,
            match="glossary_default_temporal_role_conflict",
        ):
            SemanticCatalogBuilder().build_from_data(schema, glossary)

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
    def test_fresh_question_clears_unmentioned_committed_slots(self):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Product"],
            filters=[{"field": "Category", "operator": "eq", "value": "North"}],
            time_range={
                "date_field": "OrderDate",
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
                "mode": "current_month",
                "grain": "month",
            },
            sort="desc",
            top_n=5,
        )
        delta = GroundedSemanticDelta(
            measures=["Total Sales"],
            dimensions=["Category"],
            sort="desc",
            sort_specified=True,
            top_n=3,
            top_n_specified=True,
        )
        intent = _intent(turn_relation=TurnRelation.UNCLEAR)
        decision = TurnInheritancePolicy.decide(
            "销售额最高的前3个区域是什么？", intent, delta, committed
        )
        assert decision.mode == InheritanceMode.FRESH_QUESTION

        result = StateTransitionService().merge(
            _draft(),
            delta,
            committed,
            inheritance_mode=decision.mode,
        )
        assert result.query_plan.time_range is None
        assert result.query_plan.filters == []
        assert result.query_plan.top_n == 3
        assert result.transitions.time == SlotTransition.CLEAR

    def test_follow_up_and_time_replace_inherit_only_when_explicit(self):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
            dimensions=["Category"],
        )
        follow_delta = GroundedSemanticDelta(
            filters=[StructuredFilter(field="Category", value="South")]
        )
        follow = TurnInheritancePolicy.decide(
            "那华东呢？", _intent(), follow_delta, committed
        )
        replace = TurnInheritancePolicy.decide(
            "改成去年", _intent(),
            GroundedSemanticDelta(time_specified=True), committed,
        )
        assert follow.mode == InheritanceMode.FOLLOW_UP
        assert replace.mode == InheritanceMode.REPLACE

    def test_ambiguous_omission_requires_clarification(self):
        committed = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            measures=["Total Sales"],
        )
        decision = TurnInheritancePolicy.decide(
            "华东", _intent(), GroundedSemanticDelta(), committed
        )
        assert decision.requires_clarification is True
        assert decision.mode is None

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


def _m55_domain_catalog(
    *,
    model_key: str,
    table_name: str,
    measure_name: str,
    measure_alias: str,
    member_field: str,
    member_field_alias: str,
    member_aliases: dict[str, str],
    member_suffixes: list[str],
    ranking_field: str,
    ranking_alias: str,
    runtime_members: list[str],
    include_month_group: bool = False,
):
    columns = [
        ColumnSchema(name=member_field, data_type="String"),
        ColumnSchema(name=ranking_field, data_type="String"),
        ColumnSchema(name="EventDate", data_type="DateTime"),
    ]
    if include_month_group:
        columns.append(ColumnSchema(name="PeriodBucket", data_type="String"))
    schema = SemanticModelSchema(
        name=f"Fixture {model_key}",
        key=model_key,
        tables=[TableSchema(
            name=table_name,
            columns=columns,
            measures=[MeasureSchema(name=measure_name, data_type="Double")],
        )],
    )
    fields = {
        member_field: {
            "table_name": table_name,
            "object_type": "field",
            "aliases": [member_field_alias],
            "member_aliases": member_aliases,
            "member_suffixes": member_suffixes,
        },
        ranking_field: {
            "table_name": table_name,
            "object_type": "field",
            "aliases": [ranking_alias],
        },
        "EventDate": {
            "table_name": table_name,
            "object_type": "field",
            "aliases": ["业务日期"],
        },
    }
    if include_month_group:
        fields["PeriodBucket"] = {
            "table_name": table_name,
            "object_type": "field",
            "aliases": ["月份"],
            "temporal_grouping": {
                "grain": "month",
                "date_field": "EventDate",
                "date_table_name": table_name,
            },
        }
    glossary = {
        "version": 1,
        "semantic_model_key": model_key,
        "schema_fingerprint": compute_schema_fingerprint(schema),
        "measures": {
            measure_name: {
                "table_name": table_name,
                "object_type": "measure",
                "aliases": [measure_alias],
            }
        },
        "fields": fields,
    }
    catalog = SemanticCatalogBuilder().build_from_data(schema, glossary)
    return catalog, runtime_members


class TestSemanticCorrectnessFailureReproducers:
    @staticmethod
    async def _ground_member(
        catalog,
        runtime_members,
        question,
        measure_alias,
        measure_name,
    ):
        calls: list[str] = []

        async def lookup(field, limit):
            calls.append(field.canonical_name)
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key=catalog.semantic_model_key,
                table_name=field.table_name,
                field_name=field.canonical_name,
                values=runtime_members,
                source_mode="real",
            )

        outcome = await SemanticGroundingService(catalog).ground(
            question,
            _intent(detected_measures=[measure_alias]),
            QueryPlan(
                normalized_question=question,
                semantic_model_key=catalog.semantic_model_key,
                measures=[measure_name],
            ),
            None,
            lookup,
        )
        return outcome, calls

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("华南销售额", "South"),
            ("华南区销售额", "South"),
            ("南区销售额", "South"),
        ],
    )
    async def test_model_scoped_member_variants_require_runtime_confirmation(
        self, question, expected
    ):
        catalog, members = _m55_domain_catalog(
            model_key="sales_fixture",
            table_name="SalesFacts",
            measure_name="NetRevenue",
            measure_alias="销售额",
            member_field="MarketArea",
            member_field_alias="区域",
            member_aliases={"华南": "South", "南区": "South"},
            member_suffixes=["区"],
            ranking_field="SkuName",
            ranking_alias="产品",
            runtime_members=["South", "East"],
        )

        outcome, calls = await self._ground_member(
            catalog, members, question, "销售额", "NetRevenue"
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.filters == [
            StructuredFilter(field="MarketArea", value=expected)
        ]
        assert calls == ["MarketArea"]

    @pytest.mark.asyncio
    async def test_explicit_unknown_member_is_no_match_not_broader_query(self):
        catalog, members = _m55_domain_catalog(
            model_key="sales_fixture",
            table_name="SalesFacts",
            measure_name="NetRevenue",
            measure_alias="销售额",
            member_field="MarketArea",
            member_field_alias="区域",
            member_aliases={"华南": "South", "南区": "South"},
            member_suffixes=["区"],
            ranking_field="SkuName",
            ranking_alias="产品",
            runtime_members=["South", "East"],
        )

        outcome, calls = await self._ground_member(
            catalog, members, "火星区销售额", "销售额", "NetRevenue"
        )

        assert outcome.status == GroundingStatus.UNRESOLVED
        assert outcome.delta is None
        assert calls == ["MarketArea"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("question", "expected_sort"),
        [
            ("前三个产品", "desc"),
            ("Top 3 产品", "desc"),
            ("销售额最高的3个产品", "desc"),
            ("销售额最低的3个产品", "asc"),
        ],
    )
    async def test_ranking_grammar_is_independent_of_weak_draft(
        self, question, expected_sort
    ):
        async def no_lookup(*_):
            raise AssertionError("ranking dimension must not trigger member lookup")

        outcome = await SemanticGroundingService(_catalog()).ground(
            question,
            _intent(),
            _draft(),
            StructuredWorkMemory(
                state_status=MemoryStatus.COMMITTED,
                measures=["Total Sales"],
            ),
            no_lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.dimensions == ["Product"]
        assert outcome.delta.top_n == 3
        assert outcome.delta.sort == expected_sort

    @pytest.mark.parametrize(
        ("question", "expected_sort"),
        [
            ("哪个枢纽最准时", "desc"),
            ("哪个承运商延误最严重", "desc"),
            ("哪个节点最慢", "asc"),
            ("哪家机构最差", "asc"),
        ],
    )
    def test_generic_superlative_top1_analysis_contract(
        self, question, expected_sort
    ):
        delta = GroundedSemanticDelta()
        SemanticGroundingService._ground_analysis(question, QueryPlan(
            normalized_question=question,
            semantic_model_key="neutral",
            query_shape=QueryShape.RANKING,
        ), delta)
        assert delta.top_n == 1
        assert delta.top_n_specified is True
        assert delta.sort == expected_sort
        assert delta.sort_specified is True

    @pytest.mark.asyncio
    async def test_temporal_grouping_is_runtime_metadata_driven(self):
        catalog, _ = _m55_domain_catalog(
            model_key="education_fixture",
            table_name="LearningFacts",
            measure_name="PresenceRatio",
            measure_alias="出勤率",
            member_field="CampusNode",
            member_field_alias="校区",
            member_aliases={"东校区": "East Campus"},
            member_suffixes=["校区"],
            ranking_field="GradeBand",
            ranking_alias="年级",
            runtime_members=["East Campus"],
            include_month_group=True,
        )

        async def no_lookup(*_):
            raise AssertionError("temporal grouping must not query members")

        outcome = await SemanticGroundingService(catalog).ground(
            "每个月出勤率趋势",
            _intent(detected_measures=["出勤率"]),
            QueryPlan(
                normalized_question="每个月出勤率趋势",
                semantic_model_key="education_fixture",
                measures=["PresenceRatio"],
            ),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.dimensions == ["PeriodBucket"]
        assert outcome.delta.dimension_order == "asc"

    @pytest.mark.asyncio
    async def test_temporal_grouping_without_runtime_binding_is_controlled(self):
        async def no_lookup(*_):
            raise AssertionError("unsupported grouping must not query members")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "每个月销售额趋势",
            _intent(detected_measures=["销售额"]),
            _draft(measures=["Total Sales"]),
            None,
            no_lookup,
        )

        assert outcome.status == GroundingStatus.UNRESOLVED
        assert outcome.delta is None
        assert outcome.pending_eligible is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "model_key", "table_name", "measure_name", "measure_alias",
            "member_field", "member_alias", "member_suffix", "member_value",
            "ranking_field", "ranking_alias", "question",
        ),
        [
            (
                "education_fixture", "LearningFacts", "LearnerCount", "学生数量",
                "CampusNode", "校区", "校区", "North Campus",
                "GradeBand", "年级", "北校区学生数量",
            ),
            (
                "inventory_fixture", "StockFacts", "OnHand", "当前库存",
                "DepotNode", "仓库", "仓", "Depot-A",
                "ItemClass", "品类", "甲仓当前库存",
            ),
        ],
    )
    async def test_cross_domain_member_authority(
        self,
        model_key,
        table_name,
        measure_name,
        measure_alias,
        member_field,
        member_alias,
        member_suffix,
        member_value,
        ranking_field,
        ranking_alias,
        question,
    ):
        literal = question.removesuffix(measure_alias)
        catalog, members = _m55_domain_catalog(
            model_key=model_key,
            table_name=table_name,
            measure_name=measure_name,
            measure_alias=measure_alias,
            member_field=member_field,
            member_field_alias=member_alias,
            member_aliases={literal: member_value},
            member_suffixes=[member_suffix],
            ranking_field=ranking_field,
            ranking_alias=ranking_alias,
            runtime_members=[member_value],
        )

        outcome, calls = await self._ground_member(
            catalog, members, question, measure_alias, measure_name
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.filters == [
            StructuredFilter(field=member_field, value=member_value)
        ]
        assert calls == [member_field]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "model_key", "table_name", "measure_name", "measure_alias",
            "member_field", "member_alias", "member_suffix",
            "ranking_field", "ranking_alias", "known_member", "unknown_question",
        ),
        [
            (
                "education_fixture", "LearningFacts", "LearnerCount", "学生数量",
                "CampusNode", "校区", "校区", "GradeBand", "年级",
                "North Campus", "火星校区学生数量",
            ),
            (
                "inventory_fixture", "StockFacts", "OnHand", "当前库存",
                "DepotNode", "仓库", "仓", "ItemClass", "品类",
                "Depot-A", "火星仓当前库存",
            ),
        ],
    )
    async def test_cross_domain_unknown_member_and_top_n(
        self,
        model_key,
        table_name,
        measure_name,
        measure_alias,
        member_field,
        member_alias,
        member_suffix,
        ranking_field,
        ranking_alias,
        known_member,
        unknown_question,
    ):
        catalog, members = _m55_domain_catalog(
            model_key=model_key,
            table_name=table_name,
            measure_name=measure_name,
            measure_alias=measure_alias,
            member_field=member_field,
            member_field_alias=member_alias,
            member_aliases={},
            member_suffixes=[member_suffix],
            ranking_field=ranking_field,
            ranking_alias=ranking_alias,
            runtime_members=[known_member],
        )

        unknown, calls = await self._ground_member(
            catalog, members, unknown_question, measure_alias, measure_name
        )
        assert unknown.status == GroundingStatus.UNRESOLVED
        assert calls == [member_field]

        async def no_lookup(*_):
            raise AssertionError("ranking must not query business members")

        ranking = await SemanticGroundingService(catalog).ground(
            f"前三个{ranking_alias}",
            _intent(),
            QueryPlan(
                normalized_question=f"前三个{ranking_alias}",
                semantic_model_key=model_key,
                measures=[measure_name],
                dimensions=[ranking_field],
            ),
            StructuredWorkMemory(
                state_status=MemoryStatus.COMMITTED,
                semantic_model_key=model_key,
                measures=[measure_name],
            ),
            no_lookup,
        )
        assert ranking.status == GroundingStatus.RESOLVED
        assert ranking.delta.dimensions == [ranking_field]
        assert ranking.delta.top_n == 3
        assert ranking.delta.sort == "desc"

    @pytest.mark.asyncio
    async def test_opaque_holdout_model_uses_only_runtime_catalog_authority(self):
        catalog, members = _m55_domain_catalog(
            model_key="holdout_7f31c9",
            table_name="Fact_Q7",
            measure_name="Metric_Q7",
            measure_alias="有效载荷",
            member_field="Node_Q7",
            member_field_alias="节点",
            member_aliases={"青节点": "node-green"},
            member_suffixes=["节点"],
            ranking_field="Band_Q7",
            ranking_alias="层级",
            runtime_members=["node-green", "node-blue"],
        )

        outcome, calls = await self._ground_member(
            catalog, members, "青节点有效载荷", "有效载荷", "Metric_Q7"
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.measures == ["Metric_Q7"]
        assert outcome.delta.filters == [
            StructuredFilter(field="Node_Q7", value="node-green")
        ]
        assert calls == ["Node_Q7"]


class TestM55SchemaMutationGate:
    def test_display_label_and_table_rename_follow_updated_runtime_contract(self):
        catalog, _ = _m55_domain_catalog(
            model_key="renamed_fixture",
            table_name="Fact_Renamed",
            measure_name="Metric_Renamed",
            measure_alias="新展示指标",
            member_field="Group_Renamed",
            member_field_alias="新展示分组",
            member_aliases={},
            member_suffixes=["组"],
            ranking_field="Rank_Renamed",
            ranking_alias="新展示层级",
            runtime_members=[],
        )

        measure = ObjectGrounder(catalog).find_mentions(
            "新展示指标是多少",
            SemanticObjectType.MEASURE,
            "measure",
        )
        stale = ObjectGrounder(catalog).find_mentions(
            "旧展示指标是多少",
            SemanticObjectType.MEASURE,
            "measure",
        )
        assert measure.status == GroundingStatus.RESOLVED
        assert measure.canonical_object.table_name == "Fact_Renamed"
        assert stale.status == GroundingStatus.NOT_MENTIONED

    def test_similar_field_aliases_are_config_conflict_not_guess(self):
        schema = _schema()
        schema.tables[0].columns.extend([
            ColumnSchema(name="RegionPrimary", data_type="String"),
            ColumnSchema(name="RegionSecondary", data_type="String"),
        ])
        glossary = _glossary()
        glossary["schema_fingerprint"] = compute_schema_fingerprint(schema)
        glossary["fields"]["RegionPrimary"] = {
            "table_name": "Sales", "object_type": "field", "aliases": ["片区"]
        }
        glossary["fields"]["RegionSecondary"] = {
            "table_name": "Sales", "object_type": "field", "aliases": ["片区"]
        }

        result = ObjectGrounder(
            SemanticCatalogBuilder().build_from_data(schema, glossary)
        ).resolve_phrase("片区", SemanticObjectType.FIELD, "filter_field")

        assert result.status == GroundingStatus.CONFIG_CONFLICT

    @pytest.mark.asyncio
    async def test_removed_alias_and_changed_member_fail_closed(self):
        catalog, _ = _m55_domain_catalog(
            model_key="mutation_fixture",
            table_name="Fact_M",
            measure_name="Metric_M",
            measure_alias="现行指标",
            member_field="Node_M",
            member_field_alias="节点",
            member_aliases={"旧节点": "old-runtime-member"},
            member_suffixes=["节点"],
            ranking_field="Rank_M",
            ranking_alias="层级",
            runtime_members=["new-runtime-member"],
        )

        outcome, calls = await TestSemanticCorrectnessFailureReproducers._ground_member(
            catalog,
            ["new-runtime-member"],
            "旧节点现行指标",
            "现行指标",
            "Metric_M",
        )
        assert outcome.status == GroundingStatus.UNRESOLVED
        assert calls == ["Node_M"]

        no_alias_glossary = {
            "version": 1,
            "semantic_model_key": catalog.semantic_model_key,
            "schema_fingerprint": catalog.schema_fingerprint,
            "measures": {
                "Metric_M": {
                    "table_name": "Fact_M",
                    "object_type": "measure",
                    "aliases": [],
                }
            },
            "fields": {},
        }
        schema = SemanticModelSchema(
            name="Mutation",
            key="mutation_fixture",
            tables=[TableSchema(
                name="Fact_M",
                columns=[ColumnSchema(name="Node_M", data_type="String")],
                measures=[MeasureSchema(name="Metric_M", data_type="Double")],
            )],
        )
        no_alias = SemanticCatalogBuilder().build_from_data(schema, no_alias_glossary)
        assert ObjectGrounder(no_alias).find_mentions(
            "现行指标", SemanticObjectType.MEASURE, "measure"
        ).status == GroundingStatus.NOT_MENTIONED


class TestM582QueryShapes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "model_key", "table_name", "measure_name", "measure_alias",
            "member_field", "member_field_alias", "member_values",
            "ranking_field", "ranking_alias",
        ),
        [
            (
                "sales_fixture", "SalesFacts", "NetRevenue", "销售额",
                "MarketArea", "区域", (("华南", "South"), ("华东", "East")),
                "SkuName", "产品",
            ),
            (
                "education_fixture", "LearningFacts", "LearnerCount", "学生数量",
                "CampusNode", "校区", (("东校区", "East Campus"), ("西校区", "West Campus")),
                "CourseNode", "课程",
            ),
            (
                "inventory_fixture", "StockFacts", "OnHand", "当前库存",
                "DepotNode", "仓库", (("甲仓", "Depot-A"), ("乙仓", "Depot-B")),
                "ItemClass", "品类",
            ),
            (
                "holdout_7f31c9", "Fact_Q7", "Metric_Q7", "有效载荷",
                "Node_Q7", "节点", (("青节点", "node-green"), ("蓝节点", "node-blue")),
                "Band_Q7", "层级",
            ),
        ],
    )
    async def test_core_query_shapes_are_grounded_from_each_runtime_catalog(
        self,
        model_key,
        table_name,
        measure_name,
        measure_alias,
        member_field,
        member_field_alias,
        member_values,
        ranking_field,
        ranking_alias,
    ):
        alias_map = dict(member_values)
        catalog, runtime_members = _m55_domain_catalog(
            model_key=model_key,
            table_name=table_name,
            measure_name=measure_name,
            measure_alias=measure_alias,
            member_field=member_field,
            member_field_alias=member_field_alias,
            member_aliases=alias_map,
            member_suffixes=[member_field_alias],
            ranking_field=ranking_field,
            ranking_alias=ranking_alias,
            runtime_members=list(alias_map.values()),
            include_month_group=True,
        )

        async def lookup(field, limit):
            assert limit == 100
            assert field.canonical_name == member_field
            return ColumnMembersResult(
                semantic_model_key=model_key,
                table_name=table_name,
                field_name=member_field,
                values=runtime_members,
                source_mode="real",
            )

        cases = [
            (
                f"{measure_alias}是多少",
                QueryShape.SCALAR,
                [measure_name],
                None,
            ),
            (
                f"有哪些{ranking_alias}",
                QueryShape.ENTITY_LIST,
                None,
                [ranking_field],
            ),
            (
                f"各{ranking_alias}{measure_alias}",
                QueryShape.GROUPED,
                [measure_name],
                [ranking_field],
            ),
            (
                f"{measure_alias}最高的是哪个{ranking_alias}",
                QueryShape.RANKING,
                [measure_name],
                [ranking_field],
            ),
            (
                f"{member_values[0][0]}和{member_values[1][0]}的"
                f"{measure_alias}分别是多少",
                QueryShape.MEMBER_SET,
                [measure_name],
                [member_field],
            ),
            (
                f"过去12个月{measure_alias}趋势",
                QueryShape.TREND,
                [measure_name],
                ["PeriodBucket"],
            ),
        ]

        for question, shape, measures, dimensions in cases:
            outcome = await SemanticGroundingService(
                catalog, today=lambda: date(2026, 8, 28)
            ).ground(
                question,
                _intent(
                    normalized_question=question,
                    detected_measures=([measure_alias] if measures else []),
                    detected_dimensions=(
                        [ranking_alias]
                        if dimensions == [ranking_field]
                        else []
                    ),
                    detected_time_range=(
                        "过去12个月" if shape == QueryShape.TREND else None
                    ),
                ),
                QueryPlan(
                    normalized_question=question,
                    semantic_model_key=model_key,
                    measures=(measures or []),
                    dimensions=(
                        [ranking_field]
                        if dimensions == [ranking_field]
                        else []
                    ),
                ),
                None,
                lookup,
                query_shape=shape,
            )

            assert outcome.status == GroundingStatus.RESOLVED, (
                model_key, question, outcome
            )
            assert outcome.delta is not None
            assert outcome.delta.query_shape == shape
            assert outcome.delta.measures == measures
            assert outcome.delta.dimensions == dimensions
            if shape == QueryShape.RANKING:
                assert outcome.delta.top_n == 1
                assert outcome.delta.sort == "desc"
            if shape == QueryShape.MEMBER_SET:
                assert outcome.delta.filters == [StructuredFilter(
                    field=member_field,
                    operator="in",
                    value=list(alias_map.values()),
                )]

    def test_optional_rich_sales_measure_aliases_are_runtime_validated(self, monkeypatch):
        from backend.tests.fixtures.model_overrides import activate_registry, bound_registry

        schema = _schema()
        schema.tables[0].measures.extend([
            MeasureSchema(name="Total Orders", data_type="Int64"),
            MeasureSchema(name="Average Order Value", data_type="Double"),
        ])
        activate_registry(monkeypatch, bound_registry(schema, ["desktop_order_language"]))
        catalog = SemanticCatalogBuilder().build(schema)
        grounder = ObjectGrounder(catalog)

        orders = grounder.find_mentions(
            "总订单数是多少", SemanticObjectType.MEASURE, "measure"
        )
        average = grounder.find_mentions(
            "平均订单金额是多少", SemanticObjectType.MEASURE, "measure"
        )

        assert orders.canonical_object is not None
        assert orders.canonical_object.canonical_name == "Total Orders"
        assert average.canonical_object is not None
        assert average.canonical_object.canonical_name == "Average Order Value"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "model_key", "table_name", "measure_name", "measure_alias",
            "ranking_field", "ranking_alias", "question",
        ),
        [
            (
                "education_fixture", "LearningFacts", "AverageScore", "平均分",
                "StudentNode", "学生", "平均分最高的是哪个学生",
            ),
            (
                "inventory_fixture", "StockFacts", "OnHand", "当前库存",
                "WarehouseNode", "仓库", "当前库存最低的是哪个仓库",
            ),
            (
                "holdout_7f31c9", "Fact_Q7", "Metric_Q7", "有效载荷",
                "Band_Q7", "层级", "有效载荷最高的是哪个层级",
            ),
        ],
    )
    async def test_top_one_shape_is_cross_domain(
        self,
        model_key,
        table_name,
        measure_name,
        measure_alias,
        ranking_field,
        ranking_alias,
        question,
    ):
        catalog, _ = _m55_domain_catalog(
            model_key=model_key,
            table_name=table_name,
            measure_name=measure_name,
            measure_alias=measure_alias,
            member_field="FilterNode",
            member_field_alias="筛选项",
            member_aliases={},
            member_suffixes=["筛选项"],
            ranking_field=ranking_field,
            ranking_alias=ranking_alias,
            runtime_members=[],
        )

        async def no_lookup(*_):
            raise AssertionError("ranking must not query members")

        outcome = await SemanticGroundingService(catalog).ground(
            question,
            _intent(detected_measures=[measure_alias], detected_dimensions=[ranking_alias]),
            QueryPlan(
                normalized_question=question,
                semantic_model_key=model_key,
                measures=[measure_name],
                dimensions=[ranking_field],
            ),
            None,
            no_lookup,
            query_shape=QueryShape.RANKING,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.measures == [measure_name]
        assert outcome.delta.dimensions == [ranking_field]
        assert outcome.delta.top_n == 1
        assert outcome.delta.sort in {"asc", "desc"}

    @pytest.mark.asyncio
    async def test_entity_list_resolves_dimension_without_measure_or_member_lookup(self):
        async def no_lookup(*_):
            raise AssertionError("entity list must not query members")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "我们销售了哪些产品？",
            _intent(detected_dimensions=["产品"]),
            _draft(dimensions=["Product"], query_shape=QueryShape.ENTITY_LIST),
            None,
            no_lookup,
            query_shape=QueryShape.ENTITY_LIST,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.query_shape == QueryShape.ENTITY_LIST
        assert outcome.delta.measures is None
        assert outcome.delta.dimensions == ["Product"]

        transition = StateTransitionService().merge(
            _draft(query_shape=QueryShape.ENTITY_LIST),
            outcome.delta,
            None,
            inheritance_mode=InheritanceMode.FRESH_QUESTION,
        )
        assert transition.query_plan.measures == []
        assert transition.query_plan.dimensions == ["Product"]
        assert transition.query_plan.query_shape == QueryShape.ENTITY_LIST

    @pytest.mark.asyncio
    async def test_implicit_extreme_is_top_one_with_proven_dimension(self):
        async def no_lookup(*_):
            raise AssertionError("ranking dimension must not query members")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "销量最高的是哪款产品？",
            _intent(detected_measures=["销量"], detected_dimensions=["产品"]),
            _draft(measures=["Total Quantity"], dimensions=["Product"]),
            None,
            no_lookup,
            query_shape=QueryShape.RANKING,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.measures == ["Total Quantity"]
        assert outcome.delta.dimensions == ["Product"]
        assert outcome.delta.sort == "desc"
        assert outcome.delta.top_n == 1

    @pytest.mark.asyncio
    async def test_ranking_clarification_keeps_proven_dimension_and_asks_only_measure(self):
        async def no_lookup(*_):
            raise AssertionError("ranking dimension must not query members")

        outcome = await SemanticGroundingService(_catalog()).ground(
            "哪些产品卖得最好？",
            _intent(detected_dimensions=["产品"], detected_measures=["卖得最好"]),
            _draft(dimensions=["Product"]),
            None,
            no_lookup,
            query_shape=QueryShape.RANKING,
        )
        merged = PendingClarificationService().merge(
            previous=None,
            outcome=outcome,
            user_input="哪些产品卖得最好？",
            conversation_id="minimal-ranking",
            request_id="ranking-1",
            semantic_model_key="local_desktop_model",
            schema_fingerprint=compute_schema_fingerprint(_schema()),
            runtime_mode=RuntimeDataMode.REAL,
            intent="data_question",
            committed=None,
        )

        assert outcome.status == GroundingStatus.UNRESOLVED
        assert merged.context.dimensions == ["Product"]
        assert merged.context.missing_slots == ["measure"]
        assert merged.clarification_question == "请明确用于判断排名的业务指标。"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("question", "shape", "expected_dimensions"),
        [
            ("手机和笔记本的销量分别是多少？", QueryShape.MEMBER_SET, ["Product"]),
            ("手机和电脑加起来销量是多少", QueryShape.FILTERED_AGGREGATION, None),
        ],
    )
    async def test_member_set_requires_every_runtime_member(
        self, question, shape, expected_dimensions
    ):
        glossary = _glossary()
        glossary["fields"]["Product"]["member_aliases"] = {
            "手机": "Phone",
            "笔记本": "Laptop",
            "电脑": "Computer",
        }
        catalog = _catalog(glossary)

        async def lookup(field, limit):
            assert field.canonical_name == "Product"
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Product",
                values=["Phone", "Laptop", "Computer"],
                source_mode="real",
            )

        outcome = await SemanticGroundingService(catalog).ground(
            question,
            _intent(detected_measures=["销量"]),
            _draft(measures=["Total Quantity"]),
            None,
            lookup,
            query_shape=shape,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta is not None
        assert outcome.delta.dimensions == expected_dimensions
        assert outcome.delta.filters == [StructuredFilter(
            field="Product",
            operator="in",
            value=(
                ["Phone", "Laptop"]
                if shape == QueryShape.MEMBER_SET
                else ["Phone", "Computer"]
            ),
        )]

    @pytest.mark.asyncio
    async def test_unknown_member_in_set_fails_closed(self):
        glossary = _glossary()
        glossary["fields"]["Product"]["member_aliases"] = {
            "手机": "Phone",
            "笔记本": "Laptop",
        }
        catalog = _catalog(glossary)

        async def lookup(field, limit):
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name=field.canonical_name,
                values=["Phone"],
                source_mode="real",
            )

        outcome = await SemanticGroundingService(catalog).ground(
            "手机和笔记本的销量分别是多少？",
            _intent(detected_measures=["销量"]),
            _draft(measures=["Total Quantity"]),
            None,
            lookup,
            query_shape=QueryShape.MEMBER_SET,
        )

        assert outcome.status == GroundingStatus.UNRESOLVED
        assert outcome.delta is None

    @pytest.mark.asyncio
    async def test_unqualified_member_set_reuses_first_runtime_validated_field(self):
        provider = _SelectionProvider("field:Sales:Product")

        async def lookup(field, limit):
            assert field.canonical_name == "Product"
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Product",
                values=["Printer", "Chair"],
                source_mode="real",
            )

        filters = [
            StructuredFilter(field="Product", value="Printer"),
            StructuredFilter(field="Product", value="Chair"),
        ]
        outcome = await SemanticGroundingService(
            _catalog(),
            selector=BoundedLLMObjectSelector(provider),
        ).ground(
            "Printer 和 Chair 的销售额分别是多少？",
            _intent(detected_measures=["销售额"], detected_filters=[
                {"field": "Product", "value": "Printer"},
                {"field": "Product", "value": "Chair"},
            ]),
            _draft(measures=["Total Sales"], filters=filters),
            None,
            lookup,
            query_shape=QueryShape.MEMBER_SET,
        )

        assert outcome.status == GroundingStatus.RESOLVED
        assert outcome.delta.filters == [StructuredFilter(
            field="Product",
            operator="in",
            value=["Printer", "Chair"],
        )]
        assert provider.calls == 1
        assert any(
            item.method == "member_set_prior_authoritative_field"
            for item in outcome.object_results
        )

    @pytest.mark.parametrize(
        "phrase",
        [
            "2025年8月到2026年1月",
            "2025年8月至2026年1月",
            "从2025年8月到2026年1月",
            "从2025年8月至2026年1月",
            "2025-08 到 2026-01",
            "2025-08 ~ 2026-01",
        ],
    )
    def test_bounded_month_range_variants(self, phrase):
        field = next(
            item for item in _catalog().objects
            if item.canonical_name == "OrderDate"
        )

        result = TimeGrounder().ground(phrase, field)

        assert result is not None
        assert result.start_date == date(2025, 8, 1)
        assert result.end_date == date(2026, 1, 31)
        assert result.grain == "month"

    def test_reversed_bounded_month_range_is_invalid(self):
        field = next(
            item for item in _catalog().objects
            if item.canonical_name == "OrderDate"
        )
        assert TimeGrounder().ground("2026年1月到2025年8月", field) is None

    @pytest.mark.asyncio
    async def test_shape_and_slots_survive_generic_multiturn_sequence(self):
        glossary = _glossary()
        glossary["fields"]["Category"].update({
            "aliases": ["类别", "地区"],
            "member_aliases": {"华南": "South"},
        })
        catalog = _catalog(glossary)
        grounding = SemanticGroundingService(catalog)
        router = QuestionRouter()

        async def lookup(field, limit):
            assert field.canonical_name == "Category"
            assert limit == 100
            return ColumnMembersResult(
                semantic_model_key="local_desktop_model",
                table_name="Sales",
                field_name="Category",
                values=["South", "East"],
                source_mode="real",
            )

        def committed_from(plan, version):
            return StructuredWorkMemory(
                conversation_id="m582-multiturn",
                request_id=f"m582-{version}",
                semantic_model_key="local_desktop_model",
                state_status=MemoryStatus.COMMITTED,
                measures=list(plan.measures),
                dimensions=list(plan.dimensions),
                filters=[item.model_dump(mode="json") for item in plan.filters],
                time_range=plan.time_range,
                sort=plan.sort,
                top_n=plan.top_n,
                last_query_plan=plan.model_dump(mode="json"),
                memory_version=version,
            )

        async def execute(
            question,
            *,
            intent,
            draft,
            committed,
        ):
            decision = router.route(question)
            outcome = await grounding.ground(
                question,
                intent,
                draft.model_copy(update={"query_shape": decision.query_shape}),
                committed,
                lookup,
                query_shape=decision.query_shape,
            )
            assert outcome.status == GroundingStatus.RESOLVED
            assert outcome.delta is not None
            inheritance = TurnInheritancePolicy.decide(
                question, intent, outcome.delta, committed
            )
            assert not inheritance.requires_clarification
            return StateTransitionService().merge(
                draft,
                outcome.delta,
                committed,
                inheritance_mode=inheritance.mode,
            ).query_plan

        plan = await execute(
            "销售额是多少",
            intent=_intent(detected_measures=["销售额"]),
            draft=_draft(measures=["Total Sales"]),
            committed=None,
        )
        assert plan.query_shape == QueryShape.SCALAR
        memory = committed_from(plan, 1)

        plan = await execute(
            "那各地区呢",
            intent=_intent(
                detected_dimensions=["地区"],
                turn_relation=TurnRelation.FOLLOW_UP,
            ),
            draft=_draft(dimensions=["Category"]),
            committed=memory,
        )
        assert plan.query_shape == QueryShape.GROUPED
        assert plan.measures == ["Total Sales"]
        assert plan.dimensions == ["Category"]
        memory = committed_from(plan, 2)

        plan = await execute(
            "最高的是哪个",
            intent=_intent(turn_relation=TurnRelation.FOLLOW_UP),
            draft=_draft(),
            committed=memory,
        )
        assert plan.query_shape == QueryShape.RANKING
        assert plan.measures == ["Total Sales"]
        assert plan.dimensions == ["Category"]
        assert plan.sort == "desc"
        assert plan.top_n == 1
        memory = committed_from(plan, 3)

        plan = await execute(
            "换成销量",
            intent=_intent(
                detected_measures=["销量"],
                turn_relation=TurnRelation.REPLACE,
            ),
            draft=_draft(measures=["Total Quantity"]),
            committed=memory,
        )
        assert plan.query_shape == QueryShape.RANKING
        assert plan.measures == ["Total Quantity"]
        assert plan.dimensions == ["Category"]
        assert plan.top_n == 1
        memory = committed_from(plan, 4)

        plan = await execute(
            "只看华南",
            intent=_intent(turn_relation=TurnRelation.FOLLOW_UP),
            draft=_draft(),
            committed=memory,
        )
        assert plan.query_shape == QueryShape.RANKING
        assert plan.filters == [StructuredFilter(field="Category", value="South")]
        assert plan.measures == ["Total Quantity"]
        assert plan.dimensions == ["Category"]
        assert plan.top_n == 1


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
