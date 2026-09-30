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
        assert semantic_model_key == "runtime-sales"
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
