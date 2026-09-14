"""Serve 18 deterministic executive-report fixtures for responsive QA.

No LLM, Power BI, persistence, filesystem report artifact, or network asset is
used.  Every response is rendered in memory from an explicit TEST_FIXTURE
snapshot and exposes renderer duration/HTML size as response headers.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
import json
import sys
from urllib.parse import parse_qs, urlparse


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.report.executive import ExecutiveSalesReportRenderer
from backend.app.report.reading_context import ReportReadingContextBuilder
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
UPDATED = datetime(2026, 9, 11, 6, 0, tzinfo=timezone.utc)
SCENARIO_NAMES = (
    "full",
    "kpi_only",
    "trend_only",
    "region_category",
    "ranking",
    "missing_optional",
    "no_filter",
    "multiple_filters",
    "unknown_freshness",
    "long_product",
    "long_customer",
    "category_gt_8",
    "points_1",
    "points_2",
    "points_6",
    "points_12",
    "points_24",
    "points_60",
)
POINT_SCENARIOS = {
    "points_1": 1,
    "points_2": 2,
    "points_6": 6,
    "points_12": 12,
    "points_24": 24,
    "points_60": 60,
}


def _trend(point_count: int) -> list[dict[str, object]]:
    return [
        {
            "label": (
                f"{2024 + (10 + index) // 12}-"
                f"{(10 + index) % 12 + 1:02d}"
            ),
            "value": 720_000 + (index % 9) * 83_000 + index * 11_500,
            "position": None,
        }
        for index in range(point_count)
    ]


def _filters(scenario: str) -> ActiveFilterContext:
    if scenario == "no_filter":
        return ActiveFilterContext(
            state=ActiveFilterState.NO_ADDITIONAL_FILTERS,
            display_text="无额外筛选",
        )
    items = [
        ReportFilterItem(
            field="Region",
            operator="eq",
            values=("South",),
            display_text="Region eq South",
        )
    ]
    if scenario == "multiple_filters":
        items.extend((
            ReportFilterItem(
                field="Category",
                operator="in_set",
                values=("Office", "Technology"),
                display_text="Category in_set Office、Technology",
            ),
            ReportFilterItem(
                field="Customer Segment",
                operator="eq",
                values=("Enterprise",),
                display_text="Customer Segment eq Enterprise",
            ),
        ))
    return ActiveFilterContext(
        state=ActiveFilterState.APPLIED,
        items=tuple(items),
        display_text="；".join(item.display_text for item in items),
    )


def _charts(scenario: str, point_count: int) -> list[ChartSpec]:
    product_label = (
        "超长名称企业级智能协作终端旗舰套装（含扩展坞、驻场部署与三年服务保障）"
        if scenario == "long_product"
        else "企业级智能协作终端"
    )
    categories = (
        [
            {"label": f"业务品类 {index:02d}", "value": 2_100_000 - index * 92_000, "position": None}
            for index in range(1, 11)
        ]
        if scenario == "category_gt_8"
        else [
            {"label": "办公设备", "value": 7_000_000, "position": None},
            {"label": "技术服务", "value": 5_480_320, "position": None},
            {"label": "企业家具", "value": 3_260_000, "position": None},
        ]
    )
    charts = [
        ChartSpec(
            type="line",
            title=f"月度销售趋势（{point_count} 个数据点）",
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
                {"label": "华东", "value": 4_300_000, "position": None},
                {"label": "华南", "value": 3_800_000, "position": None},
                {"label": "华北", "value": 2_900_000, "position": None},
                {"label": "西部", "value": 1_480_320, "position": None},
            ],
        ),
        ChartSpec(
            type="bar",
            title="品类销售贡献",
            x_field="Category",
            y_field="Total Sales",
            visual_type="hbar" if len(categories) > 8 else "donut",
            business_role="category_contribution",
            layout_hint="half",
            series=categories,
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
                {"label": product_label, "value": 1_820_000, "position": 1},
                {"label": "智能会议显示设备", "value": 1_450_000, "position": 2},
                {"label": "移动协作工作站", "value": 1_080_000, "position": 3},
            ],
        ),
    ]
    if scenario == "kpi_only":
        return []
    if scenario in {"trend_only", *POINT_SCENARIOS}:
        return charts[:1]
    if scenario == "region_category":
        return charts[1:3]
    if scenario in {"ranking", "long_product", "long_customer"}:
        return charts[3:]
    if scenario == "missing_optional":
        return [charts[0], charts[2]]
    return charts


def build_fixture(scenario: str = "full") -> ReportSpec:
    if scenario not in SCENARIO_NAMES:
        raise ValueError(f"unsupported executive visual scenario: {scenario}")
    point_count = POINT_SCENARIOS.get(scenario, 6)
    ids = tuple(f"qr-{index}" for index in range(1, 10))
    fact_ids = tuple(f"vfs-{index}" for index in range(1, 10))
    snapshot = ReportDataSnapshot(
        semantic_model_identity="fixture:sales-executive",
        schema_fingerprint="e" * 64,
        query_result_ids=ids,
        verified_fact_set_ids=fact_ids,
        source_mode="mock",
        source_kind=ReportDataSourceKind.TEST_FIXTURE,
        data_updated_at=None if scenario == "unknown_freshness" else UPDATED,
        queried_at=NOW,
        snapshot_at=NOW,
    )
    context = ReportReadingContextBuilder().build(
        report_title="销售经营分析报告",
        analysis_period=ReportAnalysisPeriod(
            state=AnalysisPeriodState.BOUNDED,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30),
            display_text="2025-01-01 至 2025-06-30",
        ),
        active_filters=_filters(scenario),
        metric_definition_keys=(
            "total_sales", "total_quantity", "total_orders", "average_order_value"
        ),
        exception_assessment=ExceptionAssessment.cannot_determine(),
        snapshot=snapshot,
        generated_at=NOW,
    )
    customer = (
        "超长名称跨区域企业集团重点战略客户（亚太区总部与十二家全资子公司联合采购）"
        if scenario == "long_customer"
        else "华东重点企业客户"
    )
    tables = [] if scenario in {"kpi_only", "trend_only", "region_category", "missing_optional", *POINT_SCENARIOS} else [
        TableSpec(
            title="Top 客户",
            columns=["排名", "客户", "销售额（元）"],
            rows=[[1, customer, 1_650_000], [2, "XYZ 集团", 1_280_000]],
        )
    ]
    return ReportSpec(
        title=context.report_title,
        template_key="sales_executive_report",
        kpis=[
            KPISpec(name="总销售额", field="Total Sales", value=12_480_320, format="currency"),
            KPISpec(name="总销量", field="Total Quantity", value=235_420, format="number"),
            KPISpec(name="总订单数", field="Total Orders", value=8_932, format="number"),
            KPISpec(name="平均订单金额", field="Average Order Value", value=1_397, format="currency"),
        ] if scenario != "trend_only" else [],
        charts=_charts(scenario, point_count),
        tables=tables,
        data_source=context.semantic_model,
        generated_at=NOW,
        source_mode="mock",
        contract_version="1.0-foundation",
        semantic_model_key=context.semantic_model,
        schema_fingerprint=snapshot.schema_fingerprint,
        query_result_ids=list(ids),
        verified_fact_set_ids=list(fact_ids),
        reading_context=context,
        data_snapshot=snapshot,
    )


async def render_fixture(scenario: str) -> tuple[str, float]:
    started = perf_counter()
    html = await ExecutiveSalesReportRenderer().render(build_fixture(scenario))
    return html, (perf_counter() - started) * 1000


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        parsed = urlparse(self.path)
        if parsed.path == "/manifest.json":
            content = json.dumps(
                {"scenarios": SCENARIO_NAMES}, ensure_ascii=False
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        scenario = parse_qs(parsed.query).get("scenario", ["full"])[0]
        try:
            html, elapsed_ms = asyncio.run(render_fixture(scenario))
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        content = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Renderer-Ms", f"{elapsed_ms:.3f}")
        self.send_header("X-Html-Bytes", str(len(content)))
        self.send_header("X-Visual-Scenario", scenario)
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"executive report visual smoke listening on http://{args.host}:{args.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
