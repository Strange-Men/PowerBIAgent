"""Serve deterministic simple-report fixtures for manual responsive QA.

This harness never calls an LLM, Power BI, persistence, or the report
repository. It creates no report artifact and leaves no durable resource.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.report.fixed import SalesReportRenderer
from backend.app.schemas.data_contracts import ChartSpec, KPISpec, ReportSpec


SUPPORTED_POINT_COUNTS = frozenset({1, 2, 6, 12, 15, 24, 60})


def _series(point_count: int) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for index in range(point_count):
        month_offset = 9 + index
        year = 2025 + month_offset // 12
        month = month_offset % 12 + 1
        value = (
            9_999_999.99
            if index == 0
            else 8_888_888.88
            if index == point_count - 1
            else 480_000 + (index % 7) * 73_500
        )
        values.append({
            "label": f"{year}-{month:02d}-01T00:00:00",
            "value": value,
        })
    return values


def build_fixture(point_count: int) -> ReportSpec:
    ids = ["trend", "category", "region", "products"]
    return ReportSpec(
        title="销售分析报表",
        template_key="sales_report",
        kpis=[
            KPISpec(name="总销售额", field="Total Sales", value=18_888_888.87, format="currency"),
            KPISpec(name="总销量", field="Total Quantity", value=15_240, format="number"),
        ],
        charts=[
            ChartSpec(
                type="line",
                title=f"月度销售趋势（{point_count} 个数据点）",
                x_field="Order Month",
                y_field="Total Sales",
                visual_type="line",
                business_role="time_trend",
                layout_hint="full",
                series=_series(point_count),
            ),
            ChartSpec(
                type="donut",
                title="品类销售贡献",
                x_field="Category",
                y_field="Total Sales",
                visual_type="donut",
                business_role="category_contribution",
                layout_hint="half",
                series=[
                    {"label": "企业办公与远程协作设备及配套服务", "value": 7_000_000},
                    {"label": "家具", "value": 5_000_000},
                    {"label": "技术服务", "value": 3_000_000},
                ],
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
                    {"label": "华东区域", "value": 8_600_000},
                    {"label": "华南区域", "value": 6_200_000},
                    {"label": "华北区域", "value": 4_300_000},
                    {"label": "西部区域", "value": 2_100_000},
                ],
            ),
            ChartSpec(
                type="bar",
                title="Top 产品销售额",
                x_field="Product",
                y_field="Total Sales",
                visual_type="hbar",
                business_role="top_products",
                layout_hint="full",
                series=[
                    {"label": "超长名称企业级协作终端旗舰套装", "value": 3_800_000, "position": 1},
                    {"label": "智能办公终端", "value": 2_900_000, "position": 2},
                    {"label": "会议室显示设备", "value": 2_100_000, "position": 3},
                ],
            ),
        ],
        data_source="visual-smoke-fixture",
        generated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        source_mode="mock",
        contract_version="2.0",
        semantic_model_key="visual-smoke-fixture",
        schema_fingerprint="0" * 64,
        query_result_ids=[f"qr_{key}" for key in ids],
        verified_fact_set_ids=[f"vfs_{key}" for key in ids],
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        query = parse_qs(urlparse(self.path).query)
        try:
            point_count = int(query.get("points", ["12"])[0])
        except ValueError:
            point_count = 12
        if point_count not in SUPPORTED_POINT_COUNTS:
            self.send_error(400, "unsupported point count")
            return
        html = asyncio.run(SalesReportRenderer().render(build_fixture(point_count)))
        content = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"report visual smoke listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
