"""M3.4 adaptive report planning: NL cases × schemas, weak signals, anti-fake."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from backend.app.report.capability import (
    ALLOWED_SECTION_IDS,
    SectionKey,
    parse_section_ids,
    resolve_requested_sections,
)
from backend.app.report.contracts import ReportDataPlanBuilder
from backend.app.report.intent import ReportIntentDraft, resolve_report_intent
from backend.app.report.plan import ReportPlanError, ReportPlanner
from backend.app.schemas.data_contracts import (
    ColumnSchema,
    MeasureSchema,
    SemanticModelSchema,
    TableSchema,
)


def _simple_schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="local_desktop_model",
        key="local_desktop_model",
        tables=[TableSchema(
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
        )],
    )


def _rich_schema() -> SemanticModelSchema:
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
    )


def _rich_without(*removals: str) -> SemanticModelSchema:
    """Rich schema minus the given columns/tables/measures."""
    schema = _rich_schema()
    sales = next(table for table in schema.tables if table.name == "Sales")
    sales.columns = [
        c for c in sales.columns if c.name not in removals
    ]
    sales.measures = [
        m for m in sales.measures if m.name not in removals
    ]
    if "Date" in removals:
        schema.tables = [t for t in schema.tables if t.name != "Date"]
    if "Region" in removals and any(t.name == "Region" for t in schema.tables):
        schema.tables = [t for t in schema.tables if t.name != "Region"]
    if "Customer" in removals and any(t.name == "Customer" for t in schema.tables):
        schema.tables = [t for t in schema.tables if t.name != "Customer"]
    return schema


def _plan_for(message: str, schema: SemanticModelSchema) -> object:
    signal = resolve_report_intent(message)
    return ReportPlanner().plan("sales_report", schema, signal.requested_ids, signal)


def _section_names(plan) -> list[str]:
    return [item.value for item in plan.resolved_sections]


# ── 5 canonical natural-language cases ─────────────────────────────────────

@pytest.mark.parametrize("schema_factory", [_simple_schema, _rich_schema])
def test_case1_only_sales_amount_produces_minimal_report(schema_factory):
    plan = _plan_for("只看销售额", schema_factory())
    assert _section_names(plan) == ["sales_kpi"]
    assert plan.requirement_keys == ("total_sales",)


def test_case2_trend_request_gets_trend_but_no_region_or_customer():
    plan = _plan_for("看看销售趋势", _rich_schema())
    assert _section_names(plan) == ["sales_kpi", "time_trend"]
    assert plan.requirement_keys == ("total_sales", "monthly_sales")
    assert "region_comparison" not in _section_names(plan)
    assert "top_customers" not in _section_names(plan)

    # Simple schema cannot resolve the trend → KPI-only report, no mock trend.
    simple = _plan_for("看看销售趋势", _simple_schema())
    assert _section_names(simple) == ["sales_kpi"]
    assert simple.requirement_keys == ("total_sales",)


def test_case3_region_request_gets_region_comparison():
    plan = _plan_for("按区域看销售表现", _rich_schema())
    assert _section_names(plan) == ["sales_kpi", "region_comparison"]
    assert plan.requirement_keys == ("total_sales", "sales_by_region")


def test_case4_top_customer_request_gets_top_customers():
    plan = _plan_for("看看头部客户", _rich_schema())
    assert _section_names(plan) == ["sales_kpi", "top_customers"]
    assert plan.requirement_keys == ("total_sales", "top_customers")


def test_case5_full_report_on_rich_uses_full_capability_set():
    plan = _plan_for("生成完整销售分析报表", _rich_schema())
    assert _section_names(plan) == [
        "sales_kpi",
        "quantity_kpi",
        "orders_kpi",
        "aov_kpi",
        "time_trend",
        "category_contribution",
        "region_comparison",
        "top_products",
        "top_customers",
    ]
    assert len(plan.requirement_keys) == 9


def test_case5_full_report_on_simple_never_mocks_missing_capabilities():
    plan = _plan_for("生成完整销售分析报表", _simple_schema())
    assert _section_names(plan) == [
        "sales_kpi",
        "quantity_kpi",
        "category_contribution",
        "top_products",
    ]
    assert plan.requirement_keys == (
        "total_sales",
        "total_quantity",
        "sales_by_category",
        "top_products",
    )
    assert plan.unavailable_sections == (
        SectionKey.ORDERS_KPI,
        SectionKey.AOV_KPI,
        SectionKey.TIME_TREND,
        SectionKey.REGION_COMPARISON,
        SectionKey.TOP_CUSTOMERS,
    )


def test_full_request_default_matches_baseline_message():
    plan = _plan_for("生成销售分析报表", _simple_schema())
    assert _section_names(plan) == [
        "sales_kpi",
        "quantity_kpi",
        "category_contribution",
        "top_products",
    ]


# ── Missing capability → unavailable, never invented ───────────────────────

def test_missing_region_capability_is_unavailable_not_invented():
    plan = _plan_for("按区域看销售表现", _rich_without("Region"))
    assert _section_names(plan) == ["sales_kpi"]
    assert plan.unavailable_sections == (SectionKey.REGION_COMPARISON,)


def test_missing_customer_capability_is_unavailable_not_invented():
    plan = _plan_for("看看头部客户", _rich_without("Customer"))
    assert _section_names(plan) == ["sales_kpi"]
    assert plan.unavailable_sections == (SectionKey.TOP_CUSTOMERS,)


def test_missing_orders_and_aov_measures_drop_only_those_kpis():
    schema = _rich_without("Total Orders", "Average Order Value")
    plan = _plan_for("生成完整销售分析报表", schema)
    assert "orders_kpi" not in _section_names(plan)
    assert "aov_kpi" not in _section_names(plan)
    assert "sales_kpi" in _section_names(plan)
    assert "time_trend" in _section_names(plan)
    assert set(plan.unavailable_sections) == {
        SectionKey.ORDERS_KPI,
        SectionKey.AOV_KPI,
    }


def test_missing_date_capability_drops_trend_only():
    plan = _plan_for("生成完整销售分析报表", _rich_without("Date"))
    assert "time_trend" not in _section_names(plan)
    assert "category_contribution" in _section_names(plan)


def test_request_with_zero_resolvable_sections_fails_closed():
    schema = _rich_without(
        "Region", "Customer", "Total Orders", "Average Order Value",
        "Date", "Category", "Product", "Total Sales", "Total Quantity",
    )
    signal = resolve_report_intent("按区域看销售表现")
    with pytest.raises(ReportPlanError) as error:
        ReportPlanner().plan("sales_report", schema, signal.requested_ids, signal)
    assert error.value.code == "sales_report_no_resolved_sections"


# ── Bounded LLM weak signal ────────────────────────────────────────────────

def test_llm_draft_unknown_ids_are_discarded():
    draft = ReportIntentDraft(report_section_ids=[
        "sales_kpi",
        "forged_arbitrary_section",
        "top_customers",
        "<script>alert(1)</script>",
        "",
    ])
    signal = resolve_report_intent("看看销售趋势", llm_draft=draft)
    assert signal.llm_used is True
    assert signal.llm_draft_ids == ("sales_kpi", "top_customers")
    # Deterministic signal remains the floor.
    assert signal.requested_ids == ("sales_kpi", "time_trend", "top_customers")


def test_scope_limiter_ignores_llm_additions():
    draft = ReportIntentDraft(report_section_ids=[
        "sales_kpi",
        "time_trend",
        "region_comparison",
        "top_customers",
    ])
    signal = resolve_report_intent("只看销售额", llm_draft=draft)
    assert signal.scope_limited is True
    assert signal.requested_ids == ("sales_kpi",)


def test_llm_draft_failure_fails_closed_to_deterministic():
    signal = resolve_report_intent("看看销售趋势", llm_draft="not a draft at all")
    assert signal.llm_used is False
    assert signal.requested_ids == ("sales_kpi", "time_trend")


def test_parse_section_ids_accepts_only_registry_ids():
    assert parse_section_ids(["sales_kpi", "time_trend"]) == (
        "sales_kpi",
        "time_trend",
    )
    assert parse_section_ids(["nope", 42, None, {}]) == ()
    assert parse_section_ids("sales_kpi") == ()
    assert "sales_kpi" in ALLOWED_SECTION_IDS
    assert len(ALLOWED_SECTION_IDS) == 9


# ── Planner determinism and provenance ─────────────────────────────────────

def test_planner_is_repeatable_and_records_provenance():
    schema = _rich_schema()
    first = _plan_for("生成完整销售分析报表", schema)
    second = _plan_for("生成完整销售分析报表", schema)
    assert first.data_plan == second.data_plan
    assert first.resolved_sections == second.resolved_sections
    assert first.schema_fingerprint == second.schema_fingerprint
    assert first.signal.requested_ids == second.signal.requested_ids
    assert len(first.schema_fingerprint) == 64
    # No LLM draft can alter the deterministic plan fingerprint surface.
    assert first.signal.llm_used is False


def test_unavailable_sections_are_recorded_not_rendered():
    plan = _plan_for("按区域看销售表现", _rich_without("Region"))
    assert [item.value for item in plan.unavailable_sections] == [
        "region_comparison"
    ]
    assert plan.requirement_keys == ("total_sales",)


def test_requirement_dedup_single_query_shared_by_two_sections():
    # sales_kpi + time_trend both need total_sales → one query only.
    plan = _plan_for("看看销售趋势", _rich_schema())
    assert plan.requirement_keys == ("total_sales", "monthly_sales")


def test_builder_rejects_unavailable_subset_directly():
    with pytest.raises(Exception) as error:
        ReportDataPlanBuilder().build(
            "sales_report",
            _simple_schema(),
            requirement_keys=("top_customers",),
        )
    assert error.value.code == "report_requirement_unavailable"


# ── Anti-fake: no authority leaks in planning modules ──────────────────────

def test_planning_modules_have_no_llm_or_powerbi_or_execution_authority():
    import backend.app.report.intent as intent_module
    import backend.app.report.plan as plan_module
    import backend.app.report.policy as policy_module
    import backend.app.report.capability as capability_module

    for module in (intent_module, plan_module, policy_module, capability_module):
        source = Path(inspect.getsourcefile(module) or "").read_text(
            encoding="utf-8"
        )
        assert "PowerBIAdapter" not in source
        assert "ToolGateway" not in source
        assert "VerifiedFactSetBuilder" not in source
        assert "QueryResult(" not in source
    capability_source = Path(
        inspect.getsourcefile(capability_module) or ""
    ).read_text(encoding="utf-8")
    assert "LLMProvider" not in capability_source
    intent_source = Path(
        inspect.getsourcefile(intent_module) or ""
    ).read_text(encoding="utf-8")
    assert "LLMProvider" not in intent_source


def test_no_oracle_values_in_planning_modules():
    import backend.app.report.intent as intent_module
    import backend.app.report.plan as plan_module
    import backend.app.report.policy as policy_module
    import backend.app.report.capability as capability_module

    combined = "\n".join(
        Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")
        for module in (intent_module, plan_module, policy_module, capability_module)
    )
    for forbidden in ("500" + "821", "35" + "8", "694" + "3997", "expected_total"):
        assert forbidden not in combined


def test_resolve_requested_sections_keeps_registry_order():
    capabilities = {
        key: type("Info", (), {"available": True})()
        for key in SectionKey
    }
    resolved, unavailable = resolve_requested_sections(
        ("top_customers", "sales_kpi", "time_trend"), capabilities
    )
    assert [item.value for item in resolved] == [
        "top_customers",
        "sales_kpi",
        "time_trend",
    ]
    assert unavailable == ()


# ── Fact-level re-gate: data-empty sections are dropped, never rendered ────

def test_empty_grouped_result_drops_section_at_fact_gate():
    """A section whose requirement returned zero verified rows is dropped."""
    from backend.app.facts import VerifiedFactSetBuilder
    from backend.app.report.assembly import (
        SalesReportDataAssembler,
        SalesReportSpecBuilder,
    )
    from datetime import date

    schema = _rich_schema()
    plan = _plan_for("生成完整销售分析报表", schema)

    from backend.app.schemas.data_contracts import QueryResult

    def result(key: str, columns: list[str], rows: list[list]):
        return QueryResult(
            result_id=f"qr_{key}",
            semantic_model_key="local_desktop_model",
            columns=columns,
            rows=rows,
            row_count=len(rows),
            source_mode="real",
        )

    results = {
        "total_sales": result("ts", ["[Total Sales]"], [[1200.5]]),
        "total_quantity": result("tq", ["[Total Quantity]"], [[9]]),
        "total_orders": result("to", ["[Total Orders]"], [[8]]),
        "average_order_value": result("aov", ["[Average Order Value]"], [[150.0]]),
        # region query returns zero verified rows → section must drop
        "sales_by_region": result("sr", ["Sales[Region]", "[Total Sales]"], []),
        "monthly_sales": result(
            "ms", ["Date[YearMonth]", "[Total Sales]"],
            [[date(2024, 1, 1), 100.0], [date(2024, 2, 1), 200.0]],
        ),
        "sales_by_category": result(
            "sc", ["Sales[Category]", "[Total Sales]"],
            [["办公用品", 700.25], ["家具", 500.25]],
        ),
        "top_products": result(
            "tp", ["Sales[Product]", "[Total Sales]"],
            [["产品 A", 800.0], ["产品 B", 400.5]],
        ),
        "top_customers": result(
            "tc", ["Sales[Customer]", "[Total Sales]"],
            [["客户甲", 600.0], ["客户乙", 300.25]],
        ),
    }
    fact_sets = {
        q.requirement_key: VerifiedFactSetBuilder().build(q.query_plan, results[q.requirement_key])
        for q in plan.data_plan.queries
    }
    fact_row_counts = {k: v.row_count for k, v in fact_sets.items()}
    still, dropped = ReportPlanner().apply_fact_evidence(plan, schema, fact_row_counts)
    assert SectionKey.REGION_COMPARISON in dropped
    assert SectionKey.REGION_COMPARISON not in still
    assert SectionKey.TIME_TREND in still

    # Remaining sections assemble and render; the dropped one is absent.
    from backend.app.report.capability import (
        ANALYSIS_SECTION_ORDER,
        KPI_SECTION_ORDER,
        SECTION_REQUIREMENTS,
    )
    remaining_keys: list[str] = []
    for section in (*KPI_SECTION_ORDER, *ANALYSIS_SECTION_ORDER):
        if section not in still:
            continue
        for key in SECTION_REQUIREMENTS[section]:
            if key not in remaining_keys:
                remaining_keys.append(key)
    execution_plan = ReportDataPlanBuilder().build(
        "sales_report", schema, requirement_keys=tuple(remaining_keys)
    )
    filtered = {q.requirement_key: results[q.requirement_key] for q in execution_plan.queries}
    filtered_facts = {k: fact_sets[k] for k in filtered}
    data = SalesReportDataAssembler().build(execution_plan, filtered, filtered_facts)
    spec = SalesReportSpecBuilder().build(data)
    assert "region_comparison" not in {c.business_role for c in spec.charts}
    assert "time_trend" in {c.business_role for c in spec.charts}


def test_assembler_rejects_empty_required_query_when_requested_directly():
    """Direct assembly of a plan with an empty result still fails closed."""
    from backend.app.facts import VerifiedFactSetBuilder
    from backend.app.report.assembly import (
        SalesReportAssemblyError,
        SalesReportDataAssembler,
    )
    from backend.app.schemas.data_contracts import QueryResult

    schema = _rich_schema()
    plan = ReportDataPlanBuilder().build(
        "sales_report", schema, requirement_keys=("sales_by_region",)
    )
    empty = QueryResult(
        result_id="qr_sr",
        semantic_model_key="local_desktop_model",
        columns=["Sales[Region]", "[Total Sales]"],
        rows=[],
        row_count=0,
        source_mode="real",
    )
    facts = VerifiedFactSetBuilder().build(plan.queries[0].query_plan, empty)
    with pytest.raises(SalesReportAssemblyError, match="required_query_empty"):
        SalesReportDataAssembler().build(
            plan, {"sales_by_region": empty}, {"sales_by_region": facts}
        )
