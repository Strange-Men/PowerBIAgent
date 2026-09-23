"""M5.10.6 final-acceptance residual corpus.

This corpus captures the four user-acceptance residuals discovered after the
published FIX.  It is intentionally RED before any production repair.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.app.facts import FactBoundedAnswerBuilder, VerifiedFactSetBuilder
from backend.app.facts.availability import (
    AvailableDataHorizon,
    DataAvailabilityContext,
    DataHorizonStatus,
)
from backend.app.intent.semantic_interpreter import (
    LLMSemanticInterpreter,
    SemanticCoverageDecision,
    SemanticEvidenceSpan,
    SemanticFilterMention,
    SemanticFrame,
    SemanticInterpretationError,
    SemanticInterpretationMode,
    UNDERSTANDING_SYSTEM_PROMPT,
)
from backend.app.llm.base import LLMProvider, LLMResponse
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector,
    CandidateSelection,
    GroundingStatus,
    SemanticGroundingService,
    TimeGrounder,
)
from backend.app.query_plan.model_semantic_context import (
    ModelSemanticContext,
    RuntimeObject,
    RuntimeRelationship,
    RuntimeTable,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    ColumnMembersResult,
    QueryResult,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


class _FrameProvider(LLMProvider):
    def __init__(self, frame: SemanticFrame) -> None:
        self.frame = frame

    async def generate(self, request, output_type):
        if output_type is SemanticFrame:
            structured = self.frame
        else:
            assert output_type is SemanticCoverageDecision
            structured = SemanticCoverageDecision(decision="ACCEPT")
        return LLMResponse(content="{}", structured=structured, model="residual-red")

    @property
    def provider_name(self) -> str:
        return "residual-red"

    @property
    def is_mock(self) -> bool:
        return False


class _AmbiguousFieldProvider(LLMProvider):
    async def generate(self, request, output_type):
        assert output_type is CandidateSelection
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(outcome="AMBIGUOUS"),
            model="residual-red",
        )

    @property
    def provider_name(self) -> str:
        return "residual-red"

    @property
    def is_mock(self) -> bool:
        return False


class _DimensionOwnerProvider(LLMProvider):
    async def generate(self, request, output_type):
        assert output_type is CandidateSelection
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(
                outcome="RESOLVED",
                candidate_id="field:Product:Product",
                matched_phrase="Product",
            ),
            model="residual-red",
        )

    @property
    def provider_name(self) -> str:
        return "residual-red"

    @property
    def is_mock(self) -> bool:
        return False


class _FactOwnerProvider(LLMProvider):
    async def generate(self, request, output_type):
        assert output_type is CandidateSelection
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(
                outcome="RESOLVED",
                candidate_id="field:Sales:Product",
                matched_phrase="Product",
            ),
            model="residual-red",
        )

    @property
    def provider_name(self) -> str:
        return "residual-red"

    @property
    def is_mock(self) -> bool:
        return False


class _SelectedCandidateProvider(LLMProvider):
    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id

    async def generate(self, request, output_type):
        assert output_type is CandidateSelection
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(
                outcome="RESOLVED",
                candidate_id=self.candidate_id,
                matched_phrase="Category",
            ),
            model="residual-red",
        )

    @property
    def provider_name(self) -> str:
        return "residual-red"

    @property
    def is_mock(self) -> bool:
        return False


class _UnresolvedCandidateProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request, output_type):
        assert output_type is CandidateSelection
        self.calls += 1
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(outcome="UNRESOLVED"),
            model="residual-red",
        )

    @property
    def provider_name(self) -> str:
        return "residual-red"

    @property
    def is_mock(self) -> bool:
        return False


def _catalog() -> SemanticCatalog:
    return SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="0" * 64,
        objects=(
            CatalogObject(
                object_id="measure:Sales:Total Sales",
                canonical_name="Total Sales",
                object_type=SemanticObjectType.MEASURE,
                table_name="Sales",
                data_type="decimal",
                aliases=("销售额",),
            ),
            CatalogObject(
                object_id="field:Sales:Region",
                canonical_name="Region",
                object_type=SemanticObjectType.FIELD,
                table_name="Sales",
                data_type="string",
                aliases=("地区",),
            ),
            CatalogObject(
                object_id="field:Sales:Category",
                canonical_name="Category",
                object_type=SemanticObjectType.FIELD,
                table_name="Sales",
                data_type="string",
                aliases=("类别",),
            ),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "member"),
    [
        ("2025年5月South销售额是多少", "South"),
        ("Could you briefly show 2025年5月华南销售额?", "华南"),
    ],
)
async def test_compound_member_cannot_be_reused_as_filter_field(
    question: str,
    member: str,
) -> None:
    """A member token is not independent evidence for a field token."""

    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        member_mentions=(member,),
        filter_mentions=(
            SemanticFilterMention(
                field_mention=member,
                member_mention=member,
                evidence_span=member,
            ),
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="销售额"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="member", text=member),
            SemanticEvidenceSpan(slot="filter", text=member),
        ),
    )

    with pytest.raises(
        SemanticInterpretationError,
        match="semantic_filter_field_not_independent",
    ):
        await LLMSemanticInterpreter(_FrameProvider(frame)).interpret(question)


@pytest.mark.asyncio
async def test_literal_runtime_member_proves_unique_filter_field_before_llm_guess() -> None:
    """An exact runtime member uniquely owned by one field must bind deterministically."""

    service = SemanticGroundingService(
        _catalog(),
        selector=BoundedLLMObjectSelector(_AmbiguousFieldProvider()),
    )
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        member_mentions=("South",),
        filter_mentions=(
            SemanticFilterMention(
                field_mention=None,
                member_mention="South",
                evidence_span="South",
            ),
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="销售额"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="member", text="South"),
            SemanticEvidenceSpan(slot="filter", text="South"),
        ),
    )

    async def lookup(field, _limit):
        values = (
            ["North", "South", "East", "West"]
            if field.canonical_name == "Region"
            else ["Furniture", "Technology"]
        )
        return ColumnMembersResult(
            semantic_model_key="model",
            table_name=field.table_name,
            field_name=field.canonical_name,
            values=values,
            source_mode="real",
        )

    outcome = await service.ground_frame(
        "2025年5月South销售额是多少",
        frame,
        None,
        lookup,
    )

    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.filters == [StructuredFilter(field="Region", value="South")]
    assert outcome.member_results[0].method == "runtime_exact"


@pytest.mark.asyncio
async def test_same_name_grouping_uses_bounded_runtime_owner_selection() -> None:
    catalog = SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="1" * 64,
        objects=(
            CatalogObject(
                object_id="measure:Sales:Total Sales",
                canonical_name="Total Sales",
                object_type=SemanticObjectType.MEASURE,
                table_name="Sales",
                data_type="decimal",
                aliases=("销售额",),
            ),
            CatalogObject(
                object_id="field:Sales:Product",
                canonical_name="Product",
                object_type=SemanticObjectType.FIELD,
                table_name="Sales",
                data_type="string",
            ),
            CatalogObject(
                object_id="field:Product:Product",
                canonical_name="Product",
                object_type=SemanticObjectType.FIELD,
                table_name="Product",
                data_type="string",
            ),
        ),
    )
    service = SemanticGroundingService(
        catalog,
        selector=BoundedLLMObjectSelector(_DimensionOwnerProvider()),
    )
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.GROUPED,
        measure_mentions=("销售额",),
        dimension_mentions=("Product",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="Product"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="dimension", text="Product"),
        ),
    )

    async def lookup(_field, _limit):
        raise AssertionError("grouping does not require member lookup")

    outcome = await service.ground_frame(
        "Product 按销售额分组",
        frame,
        None,
        lookup,
    )

    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.dimensions == ["Product"]
    assert outcome.delta.dimension_tables == {"Product": "Product"}


@pytest.mark.asyncio
async def test_active_many_to_one_relationship_overrides_wrong_same_name_owner() -> None:
    """Runtime relationship metadata, not an LLM choice, owns duplicate fields."""

    context = ModelSemanticContext(
        semantic_model_key="model",
        runtime_identity="model",
        schema_fingerprint="2" * 64,
        metadata_source="local_mcp",
        tables=(RuntimeTable(name="Sales"), RuntimeTable(name="Product")),
        columns=(
            RuntimeObject(
                object_id="field:Sales:Product",
                canonical_name="Product",
                object_type="field",
                table_name="Sales",
                data_type="string",
            ),
            RuntimeObject(
                object_id="field:Product:Product",
                canonical_name="Product",
                object_type="field",
                table_name="Product",
                data_type="string",
            ),
        ),
        measures=(),
        relationships=(RuntimeRelationship(
            from_object_id="field:Sales:Product",
            to_object_id="field:Product:Product",
            is_active=True,
            from_cardinality="Many",
            to_cardinality="One",
        ),),
        hierarchies=(),
        temporal_candidates=(),
    )
    catalog = SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="2" * 64,
        context=context,
        objects=(
            CatalogObject(
                object_id="measure:Sales:Total Sales",
                canonical_name="Total Sales",
                object_type=SemanticObjectType.MEASURE,
                table_name="Sales",
                data_type="decimal",
                aliases=("销售额",),
            ),
            CatalogObject(
                object_id="field:Sales:Product",
                canonical_name="Product",
                object_type=SemanticObjectType.FIELD,
                table_name="Sales",
                data_type="string",
            ),
            CatalogObject(
                object_id="field:Product:Product",
                canonical_name="Product",
                object_type=SemanticObjectType.FIELD,
                table_name="Product",
                data_type="string",
            ),
        ),
    )
    service = SemanticGroundingService(
        catalog,
        selector=BoundedLLMObjectSelector(_FactOwnerProvider()),
    )
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.GROUPED,
        measure_mentions=("销售额",),
        dimension_mentions=("Product",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="Product"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="dimension", text="Product"),
        ),
    )

    async def lookup(_field, _limit):
        raise AssertionError("grouping does not require member lookup")

    outcome = await service.ground_frame(
        "Product 按销售额分组", frame, None, lookup
    )

    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.dimension_tables == {"Product": "Product"}
    assert any(
        item.method == "runtime_relationship_dimension_owner"
        for item in outcome.object_results
    )


def _category_owner_catalog(*, dimension_tables: tuple[str, ...], relationships: tuple[RuntimeRelationship, ...]) -> SemanticCatalog:
    columns = [
        RuntimeObject(
            object_id="field:Sales:Category",
            canonical_name="Category",
            object_type="field",
            table_name="Sales",
            data_type="string",
        )
    ]
    objects = [
        CatalogObject(
            object_id="measure:Sales:Total Sales",
            canonical_name="Total Sales",
            object_type=SemanticObjectType.MEASURE,
            table_name="Sales",
            data_type="decimal",
            aliases=("sales amount",),
        ),
        CatalogObject(
            object_id="field:Sales:Category",
            canonical_name="Category",
            object_type=SemanticObjectType.FIELD,
            table_name="Sales",
            data_type="string",
        ),
    ]
    for table_name in dimension_tables:
        columns.extend((
            RuntimeObject(
                object_id=f"field:Sales:{table_name}Key",
                canonical_name=f"{table_name}Key",
                object_type="field",
                table_name="Sales",
                data_type="string",
            ),
            RuntimeObject(
                object_id=f"field:{table_name}:Key",
                canonical_name="Key",
                object_type="field",
                table_name=table_name,
                data_type="string",
            ),
            RuntimeObject(
                object_id=f"field:{table_name}:Category",
                canonical_name="Category",
                object_type="field",
                table_name=table_name,
                data_type="string",
            ),
        ))
        objects.append(CatalogObject(
            object_id=f"field:{table_name}:Category",
            canonical_name="Category",
            object_type=SemanticObjectType.FIELD,
            table_name=table_name,
            data_type="string",
        ))
    context = ModelSemanticContext(
        semantic_model_key="model",
        runtime_identity="model",
        schema_fingerprint="3" * 64,
        metadata_source="local_mcp",
        tables=tuple(RuntimeTable(name=name) for name in ("Sales", *dimension_tables)),
        columns=tuple(columns),
        measures=(),
        relationships=relationships,
        hierarchies=(),
        temporal_candidates=(),
    )
    return SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="3" * 64,
        context=context,
        objects=tuple(objects),
    )


def _category_frame() -> SemanticFrame:
    return SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.GROUPED,
        measure_mentions=("sales amount",),
        dimension_mentions=("Category",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="按 Category 展示"),
            SemanticEvidenceSpan(slot="measure", text="sales amount"),
            SemanticEvidenceSpan(slot="dimension", text="Category"),
        ),
    )


async def _ground_category(catalog: SemanticCatalog, selected_id: str):
    async def lookup(_field, _limit):
        raise AssertionError("grouping does not require member lookup")

    return await SemanticGroundingService(
        catalog,
        selector=BoundedLLMObjectSelector(_SelectedCandidateProvider(selected_id)),
    ).ground_frame(
        "请按 Category 展示 sales amount",
        _category_frame(),
        None,
        lookup,
    )


@pytest.mark.asyncio
async def test_same_name_dimension_endpoints_use_active_one_side_owner() -> None:
    relationship = RuntimeRelationship(
        from_object_id="field:Sales:Category",
        to_object_id="field:Product:Category",
        is_active=True,
        from_cardinality="Many",
        to_cardinality="One",
    )
    outcome = await _ground_category(
        _category_owner_catalog(
            dimension_tables=("Product",), relationships=(relationship,)
        ),
        "field:Sales:Category",
    )

    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.dimension_tables == {"Category": "Product"}


@pytest.mark.asyncio
async def test_same_name_columns_across_unrelated_tables_remain_ambiguous() -> None:
    outcome = await _ground_category(
        _category_owner_catalog(
            dimension_tables=("Product",), relationships=()
        ),
        "field:Product:Category",
    )

    assert outcome.status is GroundingStatus.AMBIGUOUS
    assert outcome.clarification_reason is not None


@pytest.mark.asyncio
async def test_non_key_same_name_column_uses_unique_active_measure_owner_path() -> None:
    relationship = RuntimeRelationship(
        from_object_id="field:Sales:ProductKey",
        to_object_id="field:Product:Key",
        is_active=True,
        from_cardinality="Many",
        to_cardinality="One",
    )
    outcome = await _ground_category(
        _category_owner_catalog(
            dimension_tables=("Product",), relationships=(relationship,)
        ),
        "field:Sales:Category",
    )

    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.dimension_tables == {"Category": "Product"}
    assert any(
        item.method == "runtime_measure_relationship_dimension_owner"
        for item in outcome.object_results
    )


@pytest.mark.asyncio
async def test_two_equally_valid_active_dimension_owners_remain_ambiguous() -> None:
    relationships = tuple(
        RuntimeRelationship(
            from_object_id=f"field:Sales:{table_name}Key",
            to_object_id=f"field:{table_name}:Key",
            is_active=True,
            from_cardinality="Many",
            to_cardinality="One",
        )
        for table_name in ("Product", "LegacyProduct")
    )
    outcome = await _ground_category(
        _category_owner_catalog(
            dimension_tables=("Product", "LegacyProduct"),
            relationships=relationships,
        ),
        "field:Product:Category",
    )

    assert outcome.status is GroundingStatus.AMBIGUOUS
    assert outcome.clarification_reason is not None


@pytest.mark.asyncio
async def test_normalized_literal_member_binds_unique_runtime_field_before_llm() -> None:
    dimension_tables = ("Region", "Product", "Customer")
    relationships = tuple(
        RuntimeRelationship(
            from_object_id=f"field:Sales:{table_name}",
            to_object_id=f"field:{table_name}:{table_name}",
            is_active=True,
            from_cardinality="Many",
            to_cardinality="One",
        )
        for table_name in dimension_tables
    )
    columns = tuple(
        RuntimeObject(
            object_id=f"field:{owner}:{name}",
            canonical_name=name,
            object_type="field",
            table_name=owner,
            data_type="string",
        )
        for owner, name in (
            ("Sales", "Region"),
            ("Sales", "Product"),
            ("Sales", "Customer"),
            ("Region", "Region"),
            ("Product", "Product"),
            ("Customer", "Customer"),
        )
    )
    context = ModelSemanticContext(
        semantic_model_key="model",
        runtime_identity="model",
        schema_fingerprint="4" * 64,
        metadata_source="local_mcp",
        tables=tuple(RuntimeTable(name=name) for name in ("Sales", *dimension_tables)),
        columns=columns,
        measures=(),
        relationships=relationships,
        hierarchies=(),
        temporal_candidates=(),
    )
    catalog = SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="4" * 64,
        context=context,
        objects=(
            CatalogObject(
                object_id="measure:Sales:Total Sales",
                canonical_name="Total Sales",
                object_type=SemanticObjectType.MEASURE,
                table_name="Sales",
                data_type="decimal",
                aliases=("sales amount",),
            ),
            *tuple(
                CatalogObject(
                    object_id=f"field:{table_name}:{table_name}",
                    canonical_name=table_name,
                    object_type=SemanticObjectType.FIELD,
                    table_name=table_name,
                    data_type="string",
                )
                for table_name in dimension_tables
            ),
        ),
    )
    provider = _UnresolvedCandidateProvider()
    service = SemanticGroundingService(
        catalog, selector=BoundedLLMObjectSelector(provider)
    )
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("sales amount",),
        member_mentions=("north",),
        filter_mentions=(SemanticFilterMention(
            field_mention=None,
            member_mention="north",
            evidence_span="north",
        ),),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="amount"),
            SemanticEvidenceSpan(slot="measure", text="sales amount"),
            SemanticEvidenceSpan(slot="member", text="north"),
            SemanticEvidenceSpan(slot="filter", text="north"),
        ),
    )

    async def lookup(field, _limit):
        values = {
            "Region": ["North", "South"],
            "Product": ["Chair", "Desk"],
            "Customer": ["Alice", "Bob"],
        }[field.canonical_name]
        return ColumnMembersResult(
            semantic_model_key="model",
            table_name=field.table_name,
            field_name=field.canonical_name,
            values=values,
            source_mode="real",
        )

    outcome = await service.ground_frame(
        "north sales amount", frame, None, lookup
    )

    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.filters == [
        StructuredFilter(field="Region", operator="eq", value="North")
    ]
    assert outcome.member_results[0].method == "runtime_normalized"
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("2025年五月销售额", date(2025, 5, 1), date(2025, 5, 31)),
        ("2025年后6个月的销售走势", date(2025, 7, 1), date(2025, 12, 31)),
        ("2025 H2 sales trend", date(2025, 7, 1), date(2025, 12, 31)),
    ],
)
def test_time_grounder_proves_named_month_and_half_year_boundaries(
    text: str,
    start: date,
    end: date,
) -> None:
    date_field = CatalogObject(
        object_id="field:Date:Date",
        canonical_name="Date",
        object_type=SemanticObjectType.FIELD,
        table_name="Date",
        data_type="datetime",
    )

    result = TimeGrounder(today=lambda: date(2026, 9, 20)).ground(
        text, date_field
    )

    assert result is not None
    assert result.start_date == start
    assert result.end_date == end
    assert result.grain == "month"


def test_horizon_answer_uses_verified_user_facing_measure_not_canonical_name() -> None:
    plan = CanonicalQueryPlan(
        normalized_question="2026年销售额是多少",
        semantic_model_key="model",
        query_shape=QueryShape.SCALAR,
        measures=["Total Sales"],
        time_range=TimeRangeSpec(
            date_field="Order Date",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            mode=TimeRangeMode.CURRENT_YEAR,
            grain="month",
        ),
    )
    result = QueryResult(
        result_id="r1",
        semantic_model_key="model",
        columns=["[Total Sales]"],
        rows=[[100]],
        row_count=1,
        source_mode="real",
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    availability = DataAvailabilityContext(
        observed_data_coverage=facts.observed_data_coverage,
        available_data_horizon=AvailableDataHorizon(
            status=DataHorizonStatus.KNOWN,
            latest_period=date(2026, 3, 31),
            grain="month",
            semantic_model_key="model",
            measure="Total Sales",
            temporal_dimension="Order Date",
            source_result_id="horizon-result",
            source_fact_set_id="horizon-facts",
        ),
    )

    answer = FactBoundedAnswerBuilder().build(
        plan,
        result,
        facts,
        data_availability=availability,
        user_facing_measure_labels={"Total Sales": "销售额"},
    )

    assert "销售额" in answer.answer
    assert "Total Sales" not in answer.answer


def test_general_frame_has_bounded_current_external_fact_requirement() -> None:
    """Runtime needs a structured signal before accepting a GENERAL answer."""

    assert "general_fact_scope" in SemanticFrame.model_fields
    assert "REQUIRES_CURRENT_EXTERNAL_FACTS" in UNDERSTANDING_SYSTEM_PROMPT
    assert "nearby" in UNDERSTANDING_SYSTEM_PROMPT.casefold()
    assert "cannot verify" in UNDERSTANDING_SYSTEM_PROMPT.casefold()
