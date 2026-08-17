"""M3 sales_report deterministic contract and anti-bypass gates."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import backend.app.report.contracts as contract_module
from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
from backend.app.report.contracts import (
    M3_SALES_SCHEMA_FINGERPRINT,
    SALES_REPORT_CONTRACT,
    ReportAvailabilityStatus,
    ReportContractError,
    ReportContractValidator,
    ReportDataPlanBuilder,
)
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.schemas.data_contracts import (
    ColumnSchema,
    MeasureSchema,
    SemanticModelSchema,
    TableSchema,
    UserContext,
)


def _schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="local_desktop_model",
        key="local_desktop_model",
        tables=[
            TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="OrderID", data_type="Int64"),
                    ColumnSchema(name="OrderDate", data_type="Int64"),
                    ColumnSchema(name="Category", data_type="String"),
                    ColumnSchema(name="Product", data_type="String"),
                    ColumnSchema(name="Quantity", data_type="Int64"),
                    ColumnSchema(name="UnitPrice", data_type="Double"),
                    ColumnSchema(name="SalesAmount", data_type="Double"),
                ],
                measures=[
                    MeasureSchema(
                        name="Total Sales",
                        expression="SUM(Sales[SalesAmount])",
                        data_type="Double",
                    ),
                    MeasureSchema(
                        name="Total Quantity",
                        expression="SUM(Sales[Quantity])",
                        data_type="Int64",
                    ),
                ],
            )
        ],
    )


def test_production_contract_is_bound_to_m3_runtime_schema():
    schema = _schema()
    assert compute_schema_fingerprint(schema) == M3_SALES_SCHEMA_FINGERPRINT
    validation = ReportContractValidator().validate("sales_report", schema)
    assert validation.status == ReportAvailabilityStatus.AVAILABLE
    assert validation.available is True


@pytest.mark.parametrize(
    ("template_key", "status"),
    [
        ("unknown", ReportAvailabilityStatus.UNKNOWN_TEMPLATE),
        ("sales_weekly", ReportAvailabilityStatus.TEMPLATE_NOT_AVAILABLE),
        ("satisfaction", ReportAvailabilityStatus.TEMPLATE_NOT_AVAILABLE),
        ("operating_overview", ReportAvailabilityStatus.TEMPLATE_NOT_AVAILABLE),
    ],
)
def test_unknown_and_legacy_templates_fail_closed(template_key, status):
    validation = ReportContractValidator().validate(template_key, _schema())
    assert validation.status == status
    assert validation.available is False
    with pytest.raises(ReportContractError):
        ReportDataPlanBuilder().build(template_key, _schema())


def test_production_permission_and_validation_defaults_only_expose_sales_report():
    assert UserContext().allowed_templates == ["sales_report"]
    validation = ValidationService()
    assert validation._allowed_templates == ("sales_report",)


def test_sales_report_requirements_and_data_plan_are_exact_and_repeatable():
    requirements = SALES_REPORT_CONTRACT.query_requirements
    assert [item.model_dump(mode="json") for item in requirements] == [
        {
            "key": "total_sales",
            "shape": "scalar",
            "measures": ["Total Sales"],
            "dimensions": [],
            "sort": None,
            "top_n": None,
        },
        {
            "key": "total_quantity",
            "shape": "scalar",
            "measures": ["Total Quantity"],
            "dimensions": [],
            "sort": None,
            "top_n": None,
        },
        {
            "key": "sales_by_category",
            "shape": "grouped",
            "measures": ["Total Sales"],
            "dimensions": ["Category"],
            "sort": None,
            "top_n": None,
        },
        {
            "key": "top_products",
            "shape": "ordered_top_n",
            "measures": ["Total Sales"],
            "dimensions": ["Product"],
            "sort": "desc",
            "top_n": 5,
        },
    ]
    first = ReportDataPlanBuilder().build("sales_report", _schema())
    second = ReportDataPlanBuilder().build("sales_report", _schema())
    assert first == second
    assert first.template_key == "sales_report"
    assert [item.requirement_key for item in first.queries] == [
        "total_sales",
        "total_quantity",
        "sales_by_category",
        "top_products",
    ]
    assert all(
        item.query_plan.requested_template == "sales_report"
        and item.query_plan.grounding_authority == "semantic_catalog"
        and item.query_plan.filters == []
        and item.query_plan.time_range is None
        for item in first.queries
    )


def test_missing_total_sales_fails_closed_without_data_plan():
    schema = _schema()
    schema.tables[0].measures = [
        item for item in schema.tables[0].measures if item.name != "Total Sales"
    ]
    validation = ReportContractValidator().validate("sales_report", schema)
    assert validation.status == ReportAvailabilityStatus.SCHEMA_INCOMPATIBLE
    assert any("measure:Sales.Total Sales" in item for item in validation.errors)
    with pytest.raises(ReportContractError):
        ReportDataPlanBuilder().build("sales_report", schema)


@pytest.mark.parametrize("missing_field", ["Category", "Product"])
def test_missing_section_dimension_never_creates_a_partial_or_fake_plan(missing_field):
    schema = _schema()
    schema.tables[0].columns = [
        item for item in schema.tables[0].columns if item.name != missing_field
    ]
    validation = ReportContractValidator().validate("sales_report", schema)
    assert validation.status == ReportAvailabilityStatus.SCHEMA_INCOMPATIBLE
    assert any(f"field:Sales.{missing_field}" in item for item in validation.errors)
    with pytest.raises(ReportContractError) as error:
        ReportDataPlanBuilder().build("sales_report", schema)
    assert error.value.code == ReportAvailabilityStatus.SCHEMA_INCOMPATIBLE.value


def test_schema_fingerprint_mismatch_fails_closed():
    schema = _schema()
    total_sales = schema.tables[0].measures[0]
    schema.tables[0].measures[0] = total_sales.model_copy(
        update={"expression": "SUMX(Sales, Sales[SalesAmount])"}
    )
    validation = ReportContractValidator().validate("sales_report", schema)
    assert validation.status == ReportAvailabilityStatus.SCHEMA_FINGERPRINT_MISMATCH
    assert validation.runtime_schema_fingerprint != M3_SALES_SCHEMA_FINGERPRINT


def test_report_data_plan_api_has_no_llm_draft_or_result_input():
    parameters = tuple(inspect.signature(ReportDataPlanBuilder.build).parameters)
    assert parameters == ("self", "template_key", "schema")


def test_contract_module_has_no_result_or_execution_pipeline_authority():
    source_path = Path(inspect.getsourcefile(contract_module) or "")
    source = source_path.read_text(encoding="utf-8")
    prohibited = (
        "QueryResult",
        "KnownAnswer",
        "known_answer",
        "LocalMCPPowerBIAdapter",
        "PowerBIAdapter",
        "ToolGateway",
        "DeterministicDAXBuilder",
        "RestrictedDAXVerifier",
        "VerifiedFactSetBuilder",
    )
    assert all(token not in source for token in prohibited)


def test_real_smoke_reuses_sealed_m2_execution_and_fact_components():
    smoke_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "manual_smoke"
        / "sales_report_contract_smoke.py"
    )
    source = smoke_path.read_text(encoding="utf-8")
    for required in (
        "create_default_tool_gateway",
        "LocalMCPPowerBIAdapter",
        "DeterministicDAXBuilder",
        "validate_dax_query_plan_consistency",
        "VerifiedFactSetBuilder",
    ):
        assert required in source
    assert "MockPowerBIAdapter" not in source
    assert "QueryResult(" not in source
