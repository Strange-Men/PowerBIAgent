"""M5.10.1 professional renderer, identity, and factual-parity contracts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.app.report.assembly import (
    GroupedValue,
    KpiValue,
    SalesReportData,
    SalesReportSpecBuilder,
    SectionProjection,
    TopNValue,
    TrendPoint,
)
from backend.app.report.executive import ExecutiveSalesReportRenderer
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.reading_context import ReportReadingContextBuilder
from backend.app.report.registry import build_report_dispatcher
from backend.app.schemas.data_contracts import ChartSpec, KPISpec, ReportSpec, TableSpec
from backend.app.schemas.report_context import (
    ActiveFilterContext,
    ActiveFilterState,
    AnalysisPeriodState,
    ExceptionAssessment,
    ReportAnalysisPeriod,
    ReportDataSnapshot,
    ReportDataSourceKind,
    ReportFilterItem,
)


NOW = datetime(2026, 9, 11, 8, 30, tzinfo=timezone.utc)


def _snapshot(
    *,
    semantic_model_identity: str = "local_desktop:model-a",
    query_result_ids: tuple[str, ...] | None = None,
    verified_fact_set_ids: tuple[str, ...] | None = None,
) -> ReportDataSnapshot:
    return ReportDataSnapshot(
        semantic_model_identity=semantic_model_identity,
        schema_fingerprint="a" * 64,
        query_result_ids=(
            query_result_ids
            or tuple(f"result-{index}" for index in range(1, 10))
        ),
        verified_fact_set_ids=(
            verified_fact_set_ids
            or tuple(f"facts-{index}" for index in range(1, 10))
        ),
        source_mode="real",
        source_kind=ReportDataSourceKind.LOCAL_MCP,
        data_updated_at=None,
        queried_at=NOW,
        snapshot_at=NOW,
    )


def _context(
    *,
    no_filters: bool = False,
    semantic_model_identity: str = "local_desktop:model-a",
    query_result_ids: tuple[str, ...] | None = None,
    verified_fact_set_ids: tuple[str, ...] | None = None,
):
    snapshot = _snapshot(
        semantic_model_identity=semantic_model_identity,
        query_result_ids=query_result_ids,
        verified_fact_set_ids=verified_fact_set_ids,
    )
    filters = (
        ActiveFilterContext(
            state=ActiveFilterState.NO_ADDITIONAL_FILTERS,
            display_text="无额外筛选",
        )
        if no_filters
        else ActiveFilterContext(
            state=ActiveFilterState.APPLIED,
            items=(
                ReportFilterItem(
                    field="Region",
                    operator="eq",
                    values=("South",),
                    display_text="Region eq South",
                ),
                ReportFilterItem(
                    field="Category",
                    operator="in_set",
                    values=("Office", "Technology"),
                    display_text="Category in_set Office、Technology",
                ),
            ),
            display_text="Region eq South；Category in_set Office、Technology",
        )
    )
    context = ReportReadingContextBuilder().build(
        report_title="销售经营分析报告",
        analysis_period=ReportAnalysisPeriod(
            state=AnalysisPeriodState.BOUNDED,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30),
            display_text="2025-01-01 至 2025-06-30",
        ),
        active_filters=filters,
        metric_definition_keys=(
            "total_sales",
            "total_quantity",
            "total_orders",
            "average_order_value",
        ),
        exception_assessment=ExceptionAssessment.cannot_determine(),
        snapshot=snapshot,
        generated_at=NOW,
    )
    return context, snapshot


def _trend(count: int = 6) -> list[dict[str, object]]:
    return [
        {
            "label": f"2025-{index + 1:02d}",
            "value": 1_000_000 + index * 125_000,
            "position": None,
        }
        for index in range(count)
    ]


def _report(*, point_count: int = 6, no_filters: bool = False) -> ReportSpec:
    context, snapshot = _context(no_filters=no_filters)
    return ReportSpec(
        title=context.report_title,
        template_key="sales_executive_report",
        kpis=[
            KPISpec(name="总销售额", field="Total Sales", value=12_480_320, format="currency"),
            KPISpec(name="总销量", field="Total Quantity", value=235_420, format="number"),
            KPISpec(name="总订单数", field="Total Orders", value=8_932, format="number"),
            KPISpec(name="平均订单金额", field="Average Order Value", value=1_397, format="currency"),
        ],
        charts=[
            ChartSpec(
                type="line",
                title="月度销售趋势",
                x_field="YearMonth",
                y_field="Total Sales",
                visual_type="line",
                business_role="time_trend",
                layout_hint="full",
                series=_trend(point_count),
            ),
            ChartSpec(
                type="bar",
                title="区域销售对比",
                x_field="Region",
                y_field="Total Sales",
                visual_type="column",
                business_role="region_comparison",
                layout_hint="half",
                series=[
                    {"label": "华东", "value": 2_180_000, "position": None},
                    {"label": "华南", "value": 1_920_000, "position": None},
                ],
            ),
            ChartSpec(
                type="bar",
                title="品类销售贡献",
                x_field="Category",
                y_field="Total Sales",
                visual_type="donut",
                business_role="category_contribution",
                layout_hint="half",
                series=[
                    {"label": "办公设备", "value": 7_000_000, "position": None},
                    {"label": "技术服务", "value": 5_480_320, "position": None},
                ],
            ),
            ChartSpec(
                type="bar",
                title="Top 产品",
                x_field="Product",
                y_field="Total Sales",
                visual_type="hbar",
                business_role="top_products",
                layout_hint="full",
                series=[
                    {
                        "label": "超长名称企业级智能协作终端旗舰套装（含扩展坞与三年服务）",
                        "value": 1_820_000,
                        "position": 1,
                    },
                    {"label": "MacBook Pro", "value": 1_450_000, "position": 2},
                ],
            ),
        ],
        tables=[
            TableSpec(
                title="Top 客户",
                columns=["排名", "客户", "销售额（元）"],
                rows=[
                    [1, "超长名称跨区域企业集团重点战略客户（亚太区）", 1_650_000],
                    [2, "XYZ 集团", 1_280_000],
                ],
            )
        ],
        data_source=context.semantic_model,
        generated_at=NOW,
        source_mode="real",
        contract_version="1.0",
        semantic_model_key=context.semantic_model,
        schema_fingerprint=snapshot.schema_fingerprint,
        query_result_ids=list(snapshot.query_result_ids),
        verified_fact_set_ids=list(snapshot.verified_fact_set_ids),
        reading_context=context,
        data_snapshot=snapshot,
    )


@pytest.mark.asyncio
async def test_executive_renderer_renders_all_p0_reading_context_fields_in_html():
    html = await ExecutiveSalesReportRenderer().render(_report())
    reading_context = html.split(
        'data-section="reading_context"', maxsplit=1
    )[1].split("</section>", maxsplit=1)[0]
    main_visual = html.split('data-section="audit_footer"', maxsplit=1)[0]
    audit_footer = html.split('data-section="audit_footer"', maxsplit=1)[1]

    assert 'data-template-key="sales_executive_report"' in html
    assert "销售经营分析报告" in html
    assert "SALES EXECUTIVE REPORT" in html
    assert "2025-01-01 至 2025-06-30" in html
    assert "区域等于South" in html
    assert "品类属于Office、Technology" in html
    assert "总销售额" in html
    assert "Sales[Total Sales]" in html
    assert "暂无可验证异常基准" in html
    assert "当前 Power BI Desktop 模型" in html
    assert "Power BI Desktop · 实时查询" in html
    assert "暂不可获取" in html
    assert "2026-09-11 08:30 UTC" in html
    for required in (
        "2025-01-01 至 2025-06-30",
        "区域等于South",
        "品类属于Office、Technology",
        "暂无可验证异常基准",
            "暂不可获取",
            "Power BI 度量值",
            "未声明",
        "未设置",
    ):
        assert required in reading_context
    for internal in (
        "local_desktop:model-a",
        "local_mcp",
        "cannot_determine",
        "UNKNOWN",
        "semantic_measure",
        NOW.isoformat(),
    ):
        assert internal not in main_visual
    assert "local_desktop:model-a" in audit_footer
    assert "local_mcp" in audit_footer
    assert NOW.isoformat() in audit_footer


@pytest.mark.asyncio
async def test_executive_renderer_has_fixed_information_architecture_and_60_point_capacity():
    html = await ExecutiveSalesReportRenderer().render(_report(point_count=60))

    order = [
        html.index('data-section="reading_context"'),
        html.index('data-section="kpi_summary"'),
        html.index('data-section="hero_sales_trend"'),
        html.index('data-section="business_structure"'),
        html.index('data-section="ranking"'),
        html.index('data-section="audit_footer"'),
    ]
    assert order == sorted(order)
    assert html.count('class="trend-point"') == 60
    assert 'viewBox="0 0 1200 420"' in html
    assert "Forecast" not in html
    assert "YoY" not in html
    assert "MoM" not in html


@pytest.mark.asyncio
async def test_executive_renderer_escapes_unsafe_text_and_has_no_external_runtime():
    report = _report().model_copy(
        update={
            "tables": [
                TableSpec(
                    title="Top 客户",
                    columns=["排名", "客户", "销售额（元）"],
                    rows=[
                        [1, '<img src=x onerror="alert(1)">', 10],
                        [2, '<script>alert(1)</script>', 9],
                        [3, 'javascript:alert(1)', 8],
                        [4, '\"</style><svg onload=alert(1)>', 7],
                        [5, '超长多语言Σテスト한국어' * 80, 6],
                    ],
                )
            ]
        }
    )
    html = await ExecutiveSalesReportRenderer().render(report)

    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "javascript:alert(1)" in html
    assert "&lt;svg onload=alert(1)&gt;" in html
    lowered = html.casefold()
    for forbidden in (
        "<script",
        'href="javascript:',
        'src="javascript:',
        "http://",
        "https://",
        "<link",
        "<iframe",
        "@import",
        "url(",
    ):
        assert forbidden not in lowered


@pytest.mark.asyncio
async def test_executive_renderer_only_accepts_its_template_and_registered_roles():
    renderer = ExecutiveSalesReportRenderer()
    with pytest.raises(ValueError, match="executive_report_renderer_template_rejected"):
        await renderer.render(_report().model_copy(update={"template_key": "sales_report"}))

    forged = _report().model_copy(
        update={
            "charts": [
                _report().charts[0].model_copy(update={"business_role": "forecast"})
            ]
        }
    )
    with pytest.raises(ValueError, match="executive_report_chart_role_unregistered"):
        await renderer.render(forged)


@pytest.mark.asyncio
async def test_renderer_registry_miswire_cannot_fall_back_across_template_identity():
    dispatcher = build_report_dispatcher(
        SalesReportRenderer(),
        # Mutation C: deliberately bind the simple renderer to the executive key.
        SalesReportRenderer(),
    )

    with pytest.raises(ValueError, match="sales_report_renderer_template_rejected"):
        await dispatcher.render(_report())


@pytest.mark.asyncio
async def test_executive_renderer_omits_missing_optional_sections_and_reflows():
    report = _report(no_filters=True).model_copy(
        update={"charts": [_report().charts[0]], "tables": []}
    )
    html = await ExecutiveSalesReportRenderer().render(report)

    assert "无额外筛选" in html
    assert 'data-section="hero_sales_trend"' in html
    assert 'data-section="business_structure"' not in html
    assert 'data-section="ranking"' not in html


def _report_data(template_key: str) -> SalesReportData:
    return SalesReportData(
        template_key=template_key,
        contract_version="2.0" if template_key == "sales_report" else "1.0",
        semantic_model_key="model-a",
        schema_fingerprint="a" * 64,
        kpis=(
            KpiValue(
                requirement_key="total_sales",
                label="总销售额",
                measure="Total Sales",
                value=Decimal("100.00"),
                format="currency",
            ),
        ),
        sections=(
            SectionProjection(
                requirement_key="monthly_sales",
                shape="grouped",
                measure="Total Sales",
                dimension="YearMonth",
                kind="trend",
                values=[TrendPoint(period="2025-01", value=Decimal("40"))],
            ),
            SectionProjection(
                requirement_key="sales_by_region",
                shape="grouped",
                measure="Total Sales",
                dimension="Region",
                kind="grouped",
                values=[GroupedValue(label="South", value=Decimal("100"))],
            ),
            SectionProjection(
                requirement_key="top_products",
                shape="ordered_top_n",
                measure="Total Sales",
                dimension="Product",
                kind="top_n",
                values=[TopNValue(result_position=1, label="Product A", value=Decimal("60"))],
            ),
            SectionProjection(
                requirement_key="top_customers",
                shape="ordered_top_n",
                measure="Total Sales",
                dimension="Customer",
                kind="top_n",
                values=[TopNValue(result_position=1, label="Customer A", value=Decimal("70"))],
            ),
        ),
        query_result_ids=("r1", "r2", "r3", "r4", "r5"),
        verified_fact_set_ids=("f1", "f2", "f3", "f4", "f5"),
        source_mode="real",
        generated_at=NOW,
    )


def test_simple_and_executive_spec_projection_have_exact_shared_fact_parity():
    simple = SalesReportSpecBuilder().build(_report_data("sales_report"))
    context, snapshot = _context(
        semantic_model_identity="model-a",
        query_result_ids=("r1", "r2", "r3", "r4", "r5"),
        verified_fact_set_ids=("f1", "f2", "f3", "f4", "f5"),
    )
    executive = SalesReportSpecBuilder().build(
        _report_data("sales_executive_report"),
        reading_context=context,
        data_snapshot=snapshot,
    )

    assert [(item.field, item.value) for item in simple.kpis] == [
        (item.field, item.value) for item in executive.kpis
    ]
    simple_series = {
        item.business_role: item.series for item in simple.charts
    }
    executive_series = {
        item.business_role: item.series for item in executive.charts
    }
    for role in ("time_trend", "region_comparison", "top_products"):
        assert simple_series[role] == executive_series[role]
    simple_customers = [
        (index, row[0], row[1])
        for table in simple.tables
        if table.title == "关键明细"
        for index, row in enumerate(table.rows, start=1)
    ]
    executive_customers = [
        tuple(row)
        for table in executive.tables
        if table.title == "Top 客户"
        for row in table.rows
    ]
    assert simple_customers == executive_customers
    assert simple.query_result_ids == executive.query_result_ids
    assert simple.verified_fact_set_ids == executive.verified_fact_set_ids
    assert executive.template_key == "sales_executive_report"
    assert executive.reading_context == context
    assert executive.data_snapshot == snapshot
