"""Mock 报表渲染器 — 使用固定最小内存模板

M0.3：仅生成最小静态 HTML，禁止外部脚本/JS/自由 HTML。
M3.4：正式实现位于 SalesReportRenderer（design system renderer）；本类仅保留 Mock compatibility。
"""

from datetime import datetime

from backend.app.report.base import ReportRenderer
from backend.app.schemas.data_contracts import ReportSpec


class MockReportRenderer(ReportRenderer):
    """Mock 报表渲染器

    只负责：
    - 校验 template_key
    - 使用固定、安全、最小的内存模板
    - 生成静态 HTML 字符串
    - 禁止 JavaScript 和外部脚本
    - 不写入文件
    """

    # M0-M2 test compatibility only. M3 production availability is owned by
    # DEFAULT_TEMPLATE_CATALOG and contains only sales_report.
    ALLOWED_TEMPLATES = {"sales_weekly", "satisfaction", "operating_overview"}

    @property
    def supported_templates(self) -> list[str]:
        return list(self.ALLOWED_TEMPLATES)

    async def render(self, report: ReportSpec) -> str:
        """渲染 ReportSpec 为最小安全 HTML

        Raises:
            ValueError: template_key 不在白名单
        """
        if report.template_key not in self.ALLOWED_TEMPLATES:
            raise ValueError(
                f"Template '{report.template_key}' not allowed. "
                f"Available: {self.ALLOWED_TEMPLATES}"
            )

        return self._build_html(report)

    def _build_html(self, report: ReportSpec) -> str:
        """构建安全的最小 HTML 报表"""
        kpi_html = ""
        for kpi in report.kpis:
            kpi_html += f"""
            <div class="kpi">
                <span class="kpi-label">{self._escape(kpi.name)}</span>
                <span class="kpi-value">{self._escape(str(kpi.value))}</span>
            </div>"""

        chart_html = ""
        for chart in report.charts:
            chart_html += f"""
            <div class="chart" data-type="{self._escape(chart.type)}">
                <h3>{self._escape(chart.title)}</h3>
                <p>x: {self._escape(chart.x_field)}, y: {self._escape(chart.y_field)}</p>
            </div>"""

        table_html = ""
        for table in report.tables:
            headers = "".join(f"<th>{self._escape(c)}</th>" for c in table.columns)
            rows_html = ""
            for row in table.rows:
                cells = "".join(f"<td>{self._escape(str(c))}</td>" for c in row)
                rows_html += f"<tr>{cells}</tr>"
            table_html += f"""
            <div class="table-container">
                <h3>{self._escape(table.title)}</h3>
                <table><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table>
            </div>"""

        insights_html = ""
        for insight in report.insights:
            insights_html += f"<li>{self._escape(insight)}</li>"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{self._escape(report.title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; }}
.kpi {{ display: inline-block; margin: 10px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; }}
.kpi-label {{ display: block; font-size: 0.85em; color: #666; }}
.kpi-value {{ display: block; font-size: 1.5em; font-weight: bold; }}
.chart {{ margin: 20px 0; padding: 15px; border: 1px solid #eee; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
.source-tag {{ color: #999; font-size: 0.8em; margin-top: 20px; }}
</style>
</head>
<body>
<h1>{self._escape(report.title)}</h1>
<p class="summary">{self._escape(report.summary)}</p>

<section class="kpis">{kpi_html}</section>
<section class="charts">{chart_html}</section>
<section class="tables">{table_html}</section>

<h3>分析洞察</h3>
<ul>{insights_html}</ul>

<p class="source-tag">数据来源：{self._escape(report.data_source)} | 生成时间：{report.generated_at or datetime.utcnow().isoformat()} | 模式：{report.source_mode}</p>
</body>
</html>"""
        return html

    @staticmethod
    def _escape(text: str) -> str:
        """基础 HTML 转义"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )
