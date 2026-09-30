"""M5.10.7 schema-aware report-template eligibility tests."""

from __future__ import annotations

import pytest

from backend.app.application.report_template_compatibility_service import (
    ReportTemplateCompatibilityService,
)
from backend.app.config.settings import Settings
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.report.registry import (
    ReportTemplateAvailability,
    ReportTemplateDescriptor,
    ReportTemplateRegistry,
)
from backend.app.schemas.data_contracts import (
    ColumnSchema,
    DAXRequest,
    MeasureSchema,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
    TableSchema,
)


def _schema(*, supported_sections: str) -> SemanticModelSchema:
    measures: list[MeasureSchema] = []
    columns: list[ColumnSchema] = []
    date_columns: list[ColumnSchema] = []
    if supported_sections in {"partial", "full"}:
        measures.append(MeasureSchema(name="Total Sales", data_type="Double"))
    if supported_sections == "none":
        # Sales identity is present, but its type cannot satisfy the contract.
        measures.append(MeasureSchema(name="Total Sales", data_type="String"))
    if supported_sections == "full":
        measures.extend([
            MeasureSchema(name="Total Quantity", data_type="Int64"),
            MeasureSchema(name="Total Orders", data_type="Int64"),
            MeasureSchema(name="Average Order Value", data_type="Double"),
        ])
        columns.extend([
            ColumnSchema(name="Category", data_type="String"),
            ColumnSchema(name="Region", data_type="String"),
            ColumnSchema(name="Product", data_type="String"),
            ColumnSchema(name="Customer", data_type="String"),
        ])
        date_columns.append(ColumnSchema(name="YearMonth", data_type="Date"))
    return SemanticModelSchema(
        name="Runtime Sales",
        key="runtime-sales",
        tables=[
            TableSchema(name="Sales", columns=columns, measures=measures),
            TableSchema(name="Date", columns=date_columns),
        ],
    )


class _SchemaOnlyAdapter(PowerBIAdapter):
    def __init__(self, schema: SemanticModelSchema) -> None:
        self.schema = schema
        self.schema_calls = 0
        self.dax_calls = 0

    async def health_check(self) -> bool:
        return True

    async def get_semantic_model_schema(self, semantic_model_key: str) -> SemanticModelSchema:
        self.schema_calls += 1
        assert semantic_model_key == self.schema.key
        return self.schema

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        raise AssertionError("compatibility discovery must not execute DAX")

    async def normalize_result(self, raw: object) -> QueryResult:
        raise AssertionError("compatibility discovery must not normalize query results")

    async def normalize_error(self, raw: object) -> PowerBIError:
        raise AssertionError("compatibility discovery must not normalize query errors")

    @property
    def provider_name(self) -> str:
        return "schema-only"

    @property
    def is_mock(self) -> bool:
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("supported_sections", "expected_status", "expected_count", "selectable"),
    [
        ("full", "compatible", 9, True),
        ("partial", "partial", 1, True),
        ("none", "incompatible", 0, False),
    ],
)
async def test_schema_projection_reuses_registered_capabilities_without_dax(
    supported_sections: str,
    expected_status: str,
    expected_count: int,
    selectable: bool,
) -> None:
    adapter = _SchemaOnlyAdapter(_schema(supported_sections=supported_sections))
    service = ReportTemplateCompatibilityService(adapter, Settings())

    catalog = await service.discover("runtime-sales")

    assert adapter.schema_calls == 1
    assert adapter.dax_calls == 0
    assert len(catalog.items) == 2
    assert {item.template_key for item in catalog.items} == {"sales_report", "sales_executive_report"}
    assert catalog.reason_code is None
    assert catalog.items[0].display_name == "简易销售分析模板"
    assert {
        (item.compatibility_status.value, item.available_section_count, item.selectable)
        for item in catalog.items
    } == {(expected_status, expected_count, selectable)}
    assert all(item.total_section_count == 9 for item in catalog.items)


@pytest.mark.asyncio
async def test_registry_unavailable_template_remains_visible_but_not_selectable() -> None:
    registry = ReportTemplateRegistry((
        ReportTemplateDescriptor(
            template_key="sales_report",
            display_name="简易模板",
            description="不可用模板",
            renderer_key="simple_report",
            availability=ReportTemplateAvailability.UNAVAILABLE,
            domains=frozenset({"sales"}),
        ),
    ))
    service = ReportTemplateCompatibilityService(
        _SchemaOnlyAdapter(_schema(supported_sections="full")),
        Settings(),
        registry=registry,
    )

    catalog = await service.discover("runtime-sales")

    assert len(catalog.items) == 1
    assert catalog.items[0].compatibility_status.value == "unavailable"
    assert catalog.items[0].selectable is False
    assert catalog.items[0].reason_code == "report_template_unavailable"


def _logistics_schema() -> SemanticModelSchema:
    return SemanticModelSchema(name="Sales display name is not authority", key="runtime-logistics", tables=[
        TableSchema(name="Shipment", columns=[
            ColumnSchema(name="Carrier", data_type="String"),
            ColumnSchema(name="Route", data_type="String"),
            ColumnSchema(name="Delivery Date", data_type="Date"),
        ], measures=[MeasureSchema(name="Total Shipments", data_type="Int64")]),
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", [
    _logistics_schema(),
    SemanticModelSchema(name="Sales", key="unknown", tables=[
        TableSchema(name="Metrics", measures=[MeasureSchema(name="Amount", data_type="Double")]),
    ]),
])
async def test_non_sales_catalog_is_normal_empty_state(schema: SemanticModelSchema) -> None:
    adapter = _SchemaOnlyAdapter(schema)
    service = ReportTemplateCompatibilityService(adapter, Settings())
    catalog = await service.discover(schema.key)
    assert catalog.items == []
    assert catalog.reason_code == "no_eligible_report_template"
    assert adapter.schema_calls == 1 and adapter.dax_calls == 0


def test_profile_uses_visible_canonical_metadata_and_allows_multiple_domains() -> None:
    from backend.app.application.semantic_model_profile import build_semantic_model_profile

    sales = _schema(supported_sections="partial")
    profile = build_semantic_model_profile(sales)
    assert profile.semantic_model_key == sales.key
    assert profile.domains == frozenset({"sales"})
    assert build_semantic_model_profile(_logistics_schema()).domains == frozenset({"logistics"})
    combined = sales.model_copy(update={"tables": sales.tables + _logistics_schema().tables})
    assert build_semantic_model_profile(combined).domains == frozenset({"sales", "logistics"})
    hidden = sales.model_copy(update={"tables": [sales.tables[0].model_copy(update={"is_hidden": True})]})
    assert build_semantic_model_profile(hidden).domains == frozenset()


@pytest.mark.asyncio
async def test_schema_failure_is_not_no_eligible_template() -> None:
    class UnavailableAdapter(_SchemaOnlyAdapter):
        async def get_semantic_model_schema(self, semantic_model_key: str) -> SemanticModelSchema:
            raise TimeoutError("schema unavailable")

    catalog = await ReportTemplateCompatibilityService(
        UnavailableAdapter(_logistics_schema()), Settings(),
    ).discover("runtime-logistics")
    assert catalog.items == []
    assert catalog.reason_code == "semantic_model_schema_unavailable"


@pytest.mark.asyncio
async def test_new_logistics_descriptor_enters_existing_contract_validation() -> None:
    registry = ReportTemplateRegistry((ReportTemplateDescriptor(
        template_key="logistics_overview", display_name="物流概览", description="物流",
        renderer_key="future_logistics", availability=ReportTemplateAvailability.AVAILABLE,
        domains=frozenset({"logistics"}),
    ),))
    catalog = await ReportTemplateCompatibilityService(
        _SchemaOnlyAdapter(_logistics_schema()), Settings(), registry=registry,
    ).discover("runtime-logistics")
    assert [item.template_key for item in catalog.items] == ["logistics_overview"]
    # Matching scope does not grant a contract or bypass the existing validator.
    assert catalog.items[0].selectable is False
    assert catalog.items[0].reason_code == "report_template_unknown"


@pytest.mark.parametrize("mutation", ["hidden_measure", "system_measure", "quantity_only", "wrong_owner"])
def test_unproven_sales_identity_is_fail_closed(mutation: str) -> None:
    from backend.app.application.semantic_model_profile import build_semantic_model_profile

    sales = _schema(supported_sections="partial")
    table = sales.tables[0]
    if mutation == "wrong_owner":
        table = table.model_copy(update={"name": "Shipment"})
    else:
        measure = table.measures[0]
        update = {
            "hidden_measure": {"is_hidden": True},
            "system_measure": {"is_system_managed": True},
            "quantity_only": {"name": "Total Quantity"},
        }[mutation]
        table = table.model_copy(update={"measures": [measure.model_copy(update=update)]})
    assert build_semantic_model_profile(sales.model_copy(update={"tables": [table]})).domains == frozenset()
