"""M3.4 sales_report capability-driven contract and anti-bypass gates.

The template is a fixed *allowed capability catalog* (ADR-011): the runtime
schema decides which registered capabilities resolve; the planner picks the
requested subset; unknown/legacy templates still fail closed.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import backend.app.report.contracts as contract_module
from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
from backend.app.report.contracts import (
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
    """Simple M3 baseline model (Sales table only, OrderDate as Int64)."""
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


def _rich_schema() -> SemanticModelSchema:
    """Rich star-schema model: Date/Product/Customer/Region + 4 measures."""
    sales_columns = [
        ColumnSchema(name="OrderID", data_type="Int64"),
        ColumnSchema(name="OrderDate", data_type="DateTime"),
        ColumnSchema(name="Product", data_type="String"),
        ColumnSchema(name="Category", data_type="String"),
        ColumnSchema(name="Customer", data_type="String"),
        ColumnSchema(name="Region", data_type="String"),
        ColumnSchema(name="Quantity", data_type="Int64"),
        ColumnSchema(name="UnitPrice", data_type="Double"),
        ColumnSchema(name="SalesAmount", data_type="Double"),
    ]
    sales_measures = [
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
        MeasureSchema(
            name="Total Orders",
            expression="COUNTROWS(Sales)",
            data_type="Int64",
        ),
        MeasureSchema(
            name="Average Order Value",
            expression="DIVIDE([Total Sales], [Total Orders])",
            data_type="Double",
        ),
    ]
    return SemanticModelSchema(
        name="local_desktop_model",
        key="local_desktop_model",
        tables=[
            TableSchema(name="Sales", columns=sales_columns, measures=sales_measures),
            TableSchema(
                name="Date",
                columns=[
                    ColumnSchema(name="Date", data_type="DateTime"),
                    ColumnSchema(name="YearMonth", data_type="DateTime"),
                ],
            ),
            TableSchema(
                name="Product",
                columns=[
                    ColumnSchema(name="Product", data_type="String"),
                    ColumnSchema(name="Category", data_type="String"),
                ],
            ),
            TableSchema(
                name="Customer",
                columns=[ColumnSchema(name="Customer", data_type="String")],
            ),
            TableSchema(
                name="Region",
                columns=[ColumnSchema(name="Region", data_type="String")],
            ),
        ],
        relationships=[],
    )


def test_production_contract_resolves_on_simple_runtime_schema():
    schema = _schema()
    validation = ReportContractValidator().validate("sales_report", schema)
    assert validation.status == ReportAvailabilityStatus.AVAILABLE
    assert validation.available is True
    # Simple schema resolves exactly the four M3-baseline capabilities.
    available = {
        item.requirement_key
        for item in validation.requirement_availability
        if item.available
    }
    assert available == {
        "total_sales",
        "total_quantity",
        "sales_by_category",
        "top_products",
    }
    assert compute_schema_fingerprint(schema)


def test_production_contract_resolves_full_catalog_on_rich_schema():
    validation = ReportContractValidator().validate("sales_report", _rich_schema())
    assert validation.available is True
    available = {
        item.requirement_key
        for item in validation.requirement_availability
        if item.available
    }
    assert available == {
        "total_sales",
        "total_quantity",
        "total_orders",
        "average_order_value",
        "monthly_sales",
        "sales_by_category",
        "sales_by_region",
        "top_products",
        "top_customers",
    }


def test_opaque_instance_uses_explicit_registry_binding_scope():
    opaque_key = f"local_desktop:{'a' * 64}"
    schema = _rich_schema().model_copy(update={"key": opaque_key})

    default_validation = ReportContractValidator().validate(
        "sales_report", schema
    )
    assert (
        default_validation.status
        == ReportAvailabilityStatus.SEMANTIC_MODEL_MISMATCH
    )

    validator = ReportContractValidator(
        binding_scope_key="local_desktop_model"
    )
    validation = validator.validate("sales_report", schema)
    assert validation.available is True
    plan = ReportDataPlanBuilder(validator=validator).build(
        "sales_report",
        schema,
        requirement_keys=("total_sales",),
    )
    assert plan.semantic_model_key == opaque_key
    assert plan.queries[0].query_plan.semantic_model_key == opaque_key


@pytest.mark.parametrize(
    ("template_key", "status"),
    [
        ("unknown", ReportAvailabilityStatus.UNKNOWN_TEMPLATE),
        ("sales_weekly", ReportAvailabilityStatus.UNKNOWN_TEMPLATE),
        ("satisfaction", ReportAvailabilityStatus.UNKNOWN_TEMPLATE),
        ("operating_overview", ReportAvailabilityStatus.UNKNOWN_TEMPLATE),
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


def test_sales_report_capability_catalog_is_exact_and_repeatable():
    requirements = SALES_REPORT_CONTRACT.query_requirements
    assert [item.key for item in requirements] == [
        "total_sales",
        "total_quantity",
        "total_orders",
        "average_order_value",
        "monthly_sales",
        "sales_by_category",
        "sales_by_region",
        "top_products",
        "top_customers",
    ]
    # Full catalog on the simple schema → exactly the four baseline queries.
    first = ReportDataPlanBuilder().build(
        "sales_report",
        _schema(),
        requirement_keys=(
            "total_sales",
            "total_quantity",
            "sales_by_category",
            "top_products",
        ),
    )
    second = ReportDataPlanBuilder().build(
        "sales_report",
        _schema(),
        requirement_keys=(
            "total_sales",
            "total_quantity",
            "sales_by_category",
            "top_products",
        ),
    )
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


def test_requested_requirement_subset_is_built_deterministically():
    plan = ReportDataPlanBuilder().build(
        "sales_report",
        _rich_schema(),
        requirement_keys=("total_sales", "monthly_sales"),
    )
    assert [item.requirement_key for item in plan.queries] == [
        "total_sales",
        "monthly_sales",
    ]
    trend = plan.queries[1].query_plan
    assert trend.dimensions == ["YearMonth"]
    assert trend.dimension_tables == {"YearMonth": "Date"}
    assert trend.dimension_order == "asc"
    region = ReportDataPlanBuilder().build(
        "sales_report",
        _rich_schema(),
        requirement_keys=("sales_by_region",),
    ).queries[0].query_plan
    assert region.dimension_tables == {"Region": "Sales"}


def test_unknown_requirement_key_fails_closed():
    with pytest.raises(ReportContractError) as error:
        ReportDataPlanBuilder().build(
            "sales_report",
            _schema(),
            requirement_keys=("total_sales", "does_not_exist"),
        )
    assert error.value.code == "report_requirement_key_unknown"


def test_unavailable_requirement_fails_closed():
    """Simple schema cannot resolve the trend requirement — no partial plan."""
    with pytest.raises(ReportContractError) as error:
        ReportDataPlanBuilder().build(
            "sales_report",
            _schema(),
            requirement_keys=("monthly_sales",),
        )
    assert error.value.code == "report_requirement_unavailable"
    assert any("monthly_sales" in item for item in error.value.errors)


def test_missing_total_sales_resolves_section_unavailable_not_partial_plan():
    schema = _schema()
    schema.tables[0].measures = [
        item for item in schema.tables[0].measures if item.name != "Total Sales"
    ]
    validation = ReportContractValidator().validate("sales_report", schema)
    assert validation.available is True  # template/model still valid
    by_key = {
        item.requirement_key: item
        for item in validation.requirement_availability
    }
    assert by_key["total_sales"].available is False
    assert any("Sales.Total Sales" in item for item in by_key["total_sales"].missing)
    with pytest.raises(ReportContractError) as error:
        ReportDataPlanBuilder().build(
            "sales_report", schema, requirement_keys=("total_sales",)
        )
    assert error.value.code == "report_requirement_unavailable"


@pytest.mark.parametrize("missing_field", ["Category", "Product", "Region", "Customer"])
def test_missing_section_dimension_never_creates_a_partial_or_fake_plan(missing_field):
    schema = _rich_schema()
    schema.tables[0].columns = [
        item for item in schema.tables[0].columns if item.name != missing_field
    ]
    by_key = {
        item.requirement_key: item
        for item in ReportContractValidator()
        .validate("sales_report", schema)
        .requirement_availability
    }
    expected = {
        "Category": "sales_by_category",
        "Product": "top_products",
        "Region": "sales_by_region",
        "Customer": "top_customers",
    }[missing_field]
    assert by_key[expected].available is False
    with pytest.raises(ReportContractError) as error:
        ReportDataPlanBuilder().build(
            "sales_report", schema, requirement_keys=(expected,)
        )
    assert error.value.code == "report_requirement_unavailable"


def test_rich_extra_fields_do_not_auto_create_arbitrary_sections():
    """Star-schema duplicates are resolved via explicit table hints only."""
    validation = ReportContractValidator().validate("sales_report", _rich_schema())
    by_key = {
        item.requirement_key: item
        for item in validation.requirement_availability
    }
    # Only registry requirements exist; extra dim tables change nothing.
    assert set(by_key) == {
        item.key for item in SALES_REPORT_CONTRACT.query_requirements
    }
    # Ambiguous column resolved by hint, not by guessing a table.
    assert by_key["sales_by_region"].available is True


def test_report_data_plan_api_has_no_llm_draft_or_result_input():
    parameters = tuple(inspect.signature(ReportDataPlanBuilder.build).parameters)
    assert parameters == ("self", "template_key", "schema", "requirement_keys")


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
