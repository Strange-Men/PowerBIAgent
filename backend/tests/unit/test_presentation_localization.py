from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.dax.builder import DeterministicDAXBuilder
from backend.app.facts import VerifiedFactSetBuilder
from backend.app.facts.verified import FactBoundedAnswerBuilder
from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.formatter import (
    PresentationFormatKind,
    PresentationFormatter,
)
from backend.app.presentation.localization import (
    BoundedLLMDisplayTranslator,
    DisplayLocalization,
    DisplayLocalizationError,
    DisplayLocalizationService,
    DisplayLocalizationSource,
    DisplayTranslationCandidate,
    JsonDisplayLocalizationRegistry,
    localize_member_text,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectSource,
    SemanticObjectType,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    ColumnSchema,
    MeasureSchema,
    QueryResult,
    SemanticModelSchema,
    TableSchema,
)


class _Translator:
    def __init__(self, translations: dict[str, str]):
        self.translations = translations
        self.calls: list[tuple[tuple[DisplayTranslationCandidate, ...], str]] = []

    async def translate(
        self,
        candidates: tuple[DisplayTranslationCandidate, ...],
        locale: str,
    ) -> dict[str, str]:
        self.calls.append((candidates, locale))
        return {
            candidate.object_identity: self.translations[candidate.object_identity]
            for candidate in candidates
            if candidate.object_identity in self.translations
        }


def _object(
    object_id: str,
    canonical_name: str,
    *,
    object_type: SemanticObjectType = SemanticObjectType.FIELD,
    display_name: str | None = None,
    aliases: tuple[str, ...] = (),
    source: SemanticObjectSource = SemanticObjectSource.RUNTIME,
    data_type: str = "string",
    format_string: str | None = None,
    table_name: str = "Facts",
) -> CatalogObject:
    return CatalogObject(
        object_id=object_id,
        canonical_name=canonical_name,
        object_type=object_type,
        table_name=table_name,
        data_type=data_type,
        display_name=display_name,
        format_string=format_string,
        aliases=aliases,
        source=source,
    )


def _catalog(
    *objects: CatalogObject,
    semantic_model_key: str = "model",
) -> SemanticCatalog:
    return SemanticCatalog(
        semantic_model_key=semantic_model_key,
        schema_fingerprint="a" * 64,
        objects=objects,
    )


@pytest.mark.asyncio
async def test_verified_member_aliases_localize_answer_and_table_only() -> None:
    catalog = _catalog(
        CatalogObject(
            object_id="field:Sales:Region", canonical_name="Region",
            object_type=SemanticObjectType.FIELD, table_name="Sales",
            data_type="string", display_name="区域",
            member_aliases={"南区": "South", "北区": "North"},
            source=SemanticObjectSource.GLOSSARY,
        ),
        CatalogObject(
            object_id="measure:Sales:Total Sales", canonical_name="Total Sales",
            object_type=SemanticObjectType.MEASURE, table_name="Sales",
            data_type="decimal", display_name="销售额",
        ),
    )
    plan = CanonicalQueryPlan(
        normalized_question="各区域销售额", semantic_model_key="model",
        measures=["Total Sales"], dimensions=["Region"],
        dimension_tables={"Region": "Sales"},
    )
    result = QueryResult(
        query_id="localized-members", semantic_model_key="model",
        source_mode="real", columns=["Sales[Region]", "[Total Sales]"],
        rows=[["South", 10], ["North", 8]], row_count=2,
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    plan_before = plan.model_dump(mode="json")
    facts_before = facts.model_dump(mode="json")
    localization = DisplayLocalizationService(catalog)
    bindings = await localization.resolve_fields(
        result.columns, locale="zh-CN", table_hints=plan.dimension_tables
    )
    labels = await localization.resolve_member_labels(
        {"Region": {"South", "North"}}, locale="zh-CN",
        table_hints=plan.dimension_tables,
    )
    answer = FactBoundedAnswerBuilder().build(
        plan, result, facts,
        display_bindings=dict(zip(result.columns, bindings, strict=True)),
        user_facing_member_values=labels,
    )
    presentation = StructuredPresentationBuilder.build_answer(
        plan, result, facts, answer.answer,
        display_bindings=dict(zip(result.columns, bindings, strict=True)),
        display_values=labels,
    )
    assert labels == {("Region", "South"): "南区", ("Region", "North"): "北区"}
    assert "South" not in answer.summary and "North" not in answer.summary
    assert localize_member_text("区域South和区域North", labels) == "区域南区和区域北区"
    assert presentation.datasets[0].rows == result.rows
    assert [row[0] for row in presentation.datasets[0].formatted_rows] == ["南区", "北区"]
    chart = next(block for block in presentation.blocks if block.type == "chart")
    assert chart.data_reference == presentation.datasets[0].result_id
    assert plan.model_dump(mode="json") == plan_before
    assert facts.model_dump(mode="json") == facts_before


@pytest.mark.asyncio
async def test_bounded_member_translation_failure_is_fail_soft() -> None:
    class _FailingProvider:
        async def generate(self, request, output_type):
            raise AssertionError("display provider unavailable")

    candidate = DisplayTranslationCandidate(
        object_identity="member:field:Sales:Region:test",
        object_type=SemanticObjectType.FIELD,
        canonical_name="South",
        table_name="Sales",
    )

    translations = await BoundedLLMDisplayTranslator(
        _FailingProvider()  # type: ignore[arg-type]
    ).translate((candidate,), "zh-CN")

    assert translations == {}


@pytest.mark.asyncio
async def test_verified_runtime_members_use_bounded_cached_display_translation(
    tmp_path: Path,
) -> None:
    class _VerifiedMemberTranslator:
        def __init__(self) -> None:
            self.calls = 0

        async def translate(self, candidates, locale):
            self.calls += 1
            assert locale == "zh-CN"
            expected = {"South": "南区", "North": "北区"}
            return {
                item.object_identity: expected[item.canonical_name]
                for item in candidates
            }

    region = _object("field:Sales:Region", "Region", table_name="Sales")
    catalog = _catalog(region)
    registry = JsonDisplayLocalizationRegistry(tmp_path / "member-display.json")
    translator = _VerifiedMemberTranslator()
    values = {"Region": {"South", "North"}}

    labels = await DisplayLocalizationService(
        catalog,
        registry=registry,
        translator=translator,
    ).resolve_member_labels(
        values,
        locale="zh-CN",
        table_hints={"Region": "Sales"},
    )
    cached = await DisplayLocalizationService(
        catalog,
        registry=registry,
        translator=_Translator({}),
    ).resolve_member_labels(
        values,
        locale="zh-CN",
        table_hints={"Region": "Sales"},
    )

    assert labels == {("Region", "South"): "南区", ("Region", "North"): "北区"}
    assert cached == labels
    assert translator.calls == 1
    assert values == {"Region": {"South", "North"}}


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        (1234, PresentationFormatKind.INTEGER, "1,234"),
        (6943997.509999986, PresentationFormatKind.DECIMAL, "6,943,997.51"),
        (0.125, PresentationFormatKind.PERCENTAGE, "12.5%"),
        (1234.5, PresentationFormatKind.AMOUNT, "1,234.50"),
        ("2025-01-02T00:00:00", PresentationFormatKind.DATE, "2025年1月2日"),
        ("2025-01-01T00:00:00", PresentationFormatKind.MONTH, "2025年1月"),
        (None, PresentationFormatKind.AUTO, "—"),
    ],
)
def test_deterministic_presentation_formatter(
    value: object,
    kind: PresentationFormatKind,
    expected: str,
) -> None:
    assert PresentationFormatter(locale="zh-CN").format(value, kind) == expected


@pytest.mark.asyncio
async def test_localization_priority_metadata_then_glossary() -> None:
    catalog = _catalog(
        _object("field:Facts:Region", "Region", display_name="销售区域"),
        _object(
            "measure:Facts:Revenue",
            "Revenue",
            object_type=SemanticObjectType.MEASURE,
            aliases=("收入",),
            source=SemanticObjectSource.RUNTIME_GLOSSARY,
            data_type="decimal",
        ),
    )
    translator = _Translator({})
    service = DisplayLocalizationService(catalog, translator=translator)

    resolved = await service.resolve_fields(
        ["Facts[Region]", "[Revenue]"], locale="zh-CN"
    )

    assert [item.canonical_name for item in resolved] == ["Region", "Revenue"]
    assert [item.display_name for item in resolved] == ["销售区域", "收入"]
    assert [item.source for item in resolved] == [
        DisplayLocalizationSource.POWERBI_METADATA,
        DisplayLocalizationSource.MODEL_GLOSSARY,
    ]
    assert translator.calls == []


@pytest.mark.asyncio
async def test_localization_uses_plan_table_hint_for_duplicate_column_name() -> None:
    catalog = _catalog(
        _object("field:Sales:Region", "Region", table_name="Sales"),
        _object("field:Region:Region", "Region", table_name="Region"),
    )

    resolved = await DisplayLocalizationService(catalog).resolve_fields(
        ["Region"],
        locale="zh-CN",
        table_hints={"Region": "Sales"},
    )

    assert len(resolved) == 1
    assert resolved[0].object_identity == "field:Sales:Region"


@pytest.mark.asyncio
async def test_persisted_registry_precedes_bounded_translation(tmp_path: Path) -> None:
    catalog = _catalog(_object("field:Facts:Campus", "Campus"))
    registry = JsonDisplayLocalizationRegistry(tmp_path / "display.json")
    seed_service = DisplayLocalizationService(catalog, registry=registry)
    seed = seed_service.binding_for_registry(
        object_identity="field:Facts:Campus",
        locale="zh-CN",
        display_name="校区",
    )
    registry.put(seed)
    translator = _Translator({"field:Facts:Campus": "校园"})

    resolved = await DisplayLocalizationService(
        catalog, registry=registry, translator=translator
    ).resolve_fields(["Facts[Campus]"], locale="zh-CN")

    assert resolved[0].display_name == "校区"
    assert resolved[0].source == DisplayLocalizationSource.REGISTRY
    assert translator.calls == []


@pytest.mark.asyncio
async def test_bounded_translation_is_persisted_and_schema_scoped(
    tmp_path: Path,
) -> None:
    registry = JsonDisplayLocalizationRegistry(tmp_path / "display.json")
    original = _catalog(_object("field:Facts:Warehouse", "Warehouse"))
    translator = _Translator({"field:Facts:Warehouse": "仓库"})

    first = await DisplayLocalizationService(
        original, registry=registry, translator=translator
    ).resolve_fields(["Facts[Warehouse]"], locale="zh-CN")
    second = await DisplayLocalizationService(
        original, registry=registry, translator=_Translator({})
    ).resolve_fields(["Facts[Warehouse]"], locale="zh-CN")

    assert first[0].source == DisplayLocalizationSource.BOUNDED_TRANSLATION
    assert first[0].display_name == "仓库"
    assert second[0].source == DisplayLocalizationSource.REGISTRY
    assert second[0].display_name == "仓库"

    mutated = _catalog(
        _object("field:Facts:WarehouseV2", "Warehouse", display_name="仓储点")
    )
    invalidated = await DisplayLocalizationService(
        mutated, registry=registry, translator=_Translator({})
    ).resolve_fields(["Facts[Warehouse]"], locale="zh-CN")
    assert invalidated[0].source == DisplayLocalizationSource.POWERBI_METADATA
    assert invalidated[0].display_name == "仓储点"
    assert invalidated[0].schema_identity != first[0].schema_identity


@pytest.mark.asyncio
async def test_unknown_runtime_object_cannot_reach_translator() -> None:
    translator = _Translator({"invented": "虚构字段"})
    service = DisplayLocalizationService(
        _catalog(_object("field:Facts:Known", "Known")),
        translator=translator,
    )

    with pytest.raises(DisplayLocalizationError, match="display_object_unknown"):
        await service.resolve_fields(["Facts[Invented]"], locale="zh-CN")
    assert translator.calls == []


def test_localization_contract_keeps_canonical_identity() -> None:
    binding = DisplayLocalization(
        semantic_model_key="model",
        object_identity="field:Facts:Region",
        object_type=SemanticObjectType.FIELD,
        canonical_name="Region",
        locale="zh-CN",
        display_name="区域",
        source=DisplayLocalizationSource.MODEL_GLOSSARY,
        schema_identity="b" * 64,
        data_type="string",
    )
    assert binding.canonical_name == "Region"
    assert binding.display_name == "区域"


@pytest.mark.parametrize(
    (
        "model_key",
        "table_name",
        "dimension",
        "measure",
        "dimension_label",
        "measure_label",
        "measure_type",
        "format_string",
        "value",
        "formatted_value",
        "translation_owned",
    ),
    [
        (
            "sales_model",
            "Sales",
            "Region",
            "Revenue",
            "区域",
            "销售额",
            "decimal",
            "¥#,0.00",
            6943997.509999986,
            "6,943,997.51",
            False,
        ),
        (
            "education_model",
            "Students",
            "Campus",
            "Student Count",
            "校区",
            "学生人数",
            "int64",
            "#,0",
            1234,
            "1,234",
            False,
        ),
        (
            "inventory_model",
            "Inventory",
            "Warehouse",
            "Stock Rate",
            "仓库",
            "库存率",
            "decimal",
            "0.0%",
            0.825,
            "82.5%",
            False,
        ),
        (
            "unknown_holdout_model",
            "Telemetry",
            "FluxBand",
            "Quantum Yield",
            "通量带",
            "量子产出",
            "decimal",
            None,
            98.75,
            "98.75",
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_cross_domain_display_projection_cannot_mutate_authority(
    model_key: str,
    table_name: str,
    dimension: str,
    measure: str,
    dimension_label: str,
    measure_label: str,
    measure_type: str,
    format_string: str | None,
    value: float,
    formatted_value: str,
    translation_owned: bool,
) -> None:
    source = (
        SemanticObjectSource.RUNTIME
        if translation_owned
        else SemanticObjectSource.RUNTIME_GLOSSARY
    )
    dimension_id = f"field:{table_name}:{dimension}"
    measure_id = f"measure:{table_name}:{measure}"
    catalog = _catalog(
        _object(
            dimension_id,
            dimension,
            aliases=() if translation_owned else (dimension_label,),
            source=source,
            table_name=table_name,
        ),
        _object(
            measure_id,
            measure,
            object_type=SemanticObjectType.MEASURE,
            aliases=() if translation_owned else (measure_label,),
            source=source,
            data_type=measure_type,
            format_string=format_string,
            table_name=table_name,
        ),
        semantic_model_key=model_key,
    )
    translator = _Translator(
        {dimension_id: dimension_label, measure_id: measure_label}
        if translation_owned
        else {}
    )
    schema = SemanticModelSchema(
        name=model_key,
        key=model_key,
        tables=[TableSchema(
            name=table_name,
            columns=[ColumnSchema(name=dimension, data_type="string")],
            measures=[MeasureSchema(
                name=measure,
                expression="1",
                data_type=measure_type,
                format_string=format_string,
            )],
        )],
    )
    plan = CanonicalQueryPlan(
        normalized_question="cross-domain display verification",
        semantic_model_key=model_key,
        measures=[measure],
        dimensions=[dimension],
        dimension_tables={dimension: table_name},
    )
    result = QueryResult(
        query_id=f"query-{model_key}",
        semantic_model_key=model_key,
        source_mode="real",
        columns=[f"{table_name}[{dimension}]", f"[{measure}]"],
        rows=[["A", value]],
        row_count=1,
    )
    plan_before = plan.model_dump(mode="json")
    dax_before = DeterministicDAXBuilder().build(plan, schema).dax
    facts = VerifiedFactSetBuilder().build(plan, result)
    facts_before = facts.model_dump(mode="json")

    bindings = await DisplayLocalizationService(
        catalog,
        translator=translator,
    ).resolve_fields(result.columns, locale="zh-CN")
    presentation = StructuredPresentationBuilder.build_answer(
        plan,
        result,
        facts,
        "跨域展示结论。",
        display_bindings=dict(zip(result.columns, bindings, strict=True)),
    )

    assert [item.canonical_name for item in bindings] == [dimension, measure]
    assert [item.display_name for item in bindings] == [
        dimension_label,
        measure_label,
    ]
    assert presentation.datasets[0].columns == result.columns
    assert presentation.datasets[0].rows == result.rows
    assert presentation.datasets[0].formatted_rows == [["A", formatted_value]]
    assert plan.model_dump(mode="json") == plan_before
    assert DeterministicDAXBuilder().build(plan, schema).dax == dax_before
    assert facts.model_dump(mode="json") == facts_before
    assert VerifiedFactSetBuilder().build(plan, result) == facts
