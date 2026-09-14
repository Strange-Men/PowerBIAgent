"""Deterministic renderer for the professional sales executive template.

The renderer consumes only a pre-validated ``ReportSpec`` plus the immutable
M5.10 reading/snapshot contracts.  It performs presentation formatting and
chart geometry only: no LLM, Power BI, DAX, network access, aggregation, or
business-rule inference.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from pathlib import Path
import re
from string import Template
from typing import Any, Callable

from backend.app.report.base import ReportRenderer
from backend.app.schemas.data_contracts import ChartSpec, KPISpec, ReportSpec, TableSpec
from backend.app.schemas.report_context import MetricDefinitionStatus


class ExecutiveSalesReportRenderer(ReportRenderer):
    """Render ``sales_executive_report`` as self-contained static HTML."""

    _TEMPLATE_PATH = (
        Path(__file__).with_name("templates") / "sales_executive_report.html"
    )
    _SUPPORTED_TEMPLATES = ("sales_executive_report",)
    _ALLOWED_KPI_FIELDS = frozenset(
        {"Total Sales", "Total Quantity", "Total Orders", "Average Order Value"}
    )
    _ALLOWED_CHART_ROLES = frozenset(
        {
            "time_trend",
            "category_contribution",
            "region_comparison",
            "top_products",
            "top_customers",
        }
    )
    _ALLOWED_VISUAL_TYPES = frozenset({"line", "donut", "column", "hbar"})
    _MAX_SERIES = 200

    @property
    def supported_templates(self) -> list[str]:
        return list(self._SUPPORTED_TEMPLATES)

    async def render(self, report: ReportSpec) -> str:
        self._validate_spec(report)
        context = report.reading_context
        if context is None:  # narrowed by validation; keep type-safe.
            raise ValueError("executive_report_reading_context_required")

        charts = {item.business_role: item for item in report.charts}
        kpi_block = self._kpi_block(report.kpis)
        trend_block = (
            self._panel(
                "hero_sales_trend",
                "02",
                "销售趋势",
                "SALES TREND",
                self._line_chart(charts["time_trend"]),
                extra_class="hero-panel",
            )
            if "time_trend" in charts
            else ""
        )

        structure_cards: list[str] = []
        if "region_comparison" in charts:
            structure_cards.append(
                self._visual_card(charts["region_comparison"], self._column_chart)
            )
        if "category_contribution" in charts:
            category = charts["category_contribution"]
            builder = self._donut_chart if category.visual_type == "donut" else self._hbar_chart
            structure_cards.append(self._visual_card(category, builder))
        structure_block = (
            self._panel(
                "business_structure",
                "03",
                "业务结构分析",
                "BUSINESS STRUCTURE",
                '<div class="executive-grid structure-grid">'
                + "".join(structure_cards)
                + "</div>",
            )
            if structure_cards
            else ""
        )

        ranking_cards: list[str] = []
        if "top_products" in charts:
            ranking_cards.append(
                self._visual_card(charts["top_products"], self._hbar_chart)
            )
        if "top_customers" in charts:
            ranking_cards.append(
                self._visual_card(charts["top_customers"], self._hbar_chart)
            )
        ranking_cards.extend(self._ranking_table(item) for item in report.tables)
        ranking_block = (
            self._panel(
                "ranking",
                "04",
                "经营排名与明细",
                "RANKING & DETAIL",
                '<div class="executive-grid ranking-grid">'
                + "".join(ranking_cards)
                + "</div>",
            )
            if ranking_cards
            else ""
        )

        template = Template(self._TEMPLATE_PATH.read_text(encoding="utf-8"))
        html = template.substitute(
            title=self._text(context.report_title),
            analysis_period=self._text(context.analysis_period.display_text),
            semantic_model=self._text(context.semantic_model),
            freshness=self._text(context.data_freshness.display_text),
            generated_at=self._text(context.generated_at.isoformat()),
            reading_context=self._reading_context(report),
            kpi_block=kpi_block,
            trend_block=trend_block,
            structure_block=structure_block,
            ranking_block=ranking_block,
            audit_footer=self._audit_footer(report),
        )
        self._validate_rendered_html(html)
        return html

    @classmethod
    def _reading_context(cls, report: ReportSpec) -> str:
        context = report.reading_context
        if context is None:
            raise ValueError("executive_report_reading_context_required")
        metric_rows = "".join(
            cls._metric_definition(item) for item in context.metric_definitions
        )
        filter_items = "".join(
            f"<li>{cls._text(item.display_text)}</li>"
            for item in context.active_filters.items
        )
        if not filter_items:
            filter_items = f"<li>{cls._text(context.active_filters.display_text)}</li>"
        return (
            '<section class="reading-context report-panel" '
            'data-section="reading_context" aria-labelledby="reading-context-title">'
            '<div class="panel-heading"><span class="section-number">01</span>'
            '<div><h2 id="reading-context-title">阅读上下文</h2>'
            '<p>READING CONTEXT · 先确认口径，再解读数字</p></div></div>'
            '<div class="context-grid">'
            '<article class="context-card"><h3>当前筛选状态</h3><ul>'
            f"{filter_items}</ul><p class=\"context-period\">分析期间："
            f"{cls._text(context.analysis_period.display_text)}</p></article>"
            '<article class="context-card context-metrics"><h3>指标口径</h3>'
            f'<div class="metric-definition-list">{metric_rows}</div></article>'
            '<article class="context-card context-exception"><h3>异常 / 关注状态</h3>'
            f'<p>{cls._text(context.exception_assessment.message)}</p>'
            f'<span class="status-chip">{cls._text(context.exception_assessment.state.value)}</span>'
            "</article>"
            '<article class="context-card"><h3>数据来源</h3>'
            f'<p>{cls._text(context.data_source.display_name)}</p>'
            f'<span class="source-kind">{cls._text(context.data_source.kind.value)} · '
            f'{cls._text(context.data_source.source_mode)}</span>'
            f'<p class="freshness-text">{cls._text(context.data_freshness.display_text)}</p>'
            "</article></div></section>"
        )

    @classmethod
    def _metric_definition(cls, definition: Any) -> str:
        def facet_text(facet: Any) -> str:
            if facet.status is MetricDefinitionStatus.UNKNOWN:
                return "模型未声明 / UNKNOWN"
            return str(facet.value)

        return (
            '<div class="metric-definition">'
            f'<strong>{cls._text(definition.display_name)}</strong>'
            f'<span>{cls._text(definition.semantic_source)} · '
            f'{cls._text(definition.aggregation)} · {cls._text(definition.unit)}</span>'
            f'<small>税务口径：{cls._text(facet_text(definition.tax_basis))}</small>'
            f'<small>比较口径：{cls._text(facet_text(definition.comparison_basis))}</small>'
            "</div>"
        )

    @classmethod
    def _kpi_block(cls, kpis: list[KPISpec]) -> str:
        if not kpis:
            return ""
        cards = "".join(cls._kpi_card(item) for item in kpis)
        return cls._panel(
            "kpi_summary",
            "02" if not kpis else "KPI",
            "关键指标概览",
            "EXECUTIVE SUMMARY",
            f'<div class="kpi-grid">{cards}</div>',
        )

    @classmethod
    def _kpi_card(cls, kpi: KPISpec) -> str:
        decimals = 2 if kpi.format == "currency" else 0
        return (
            f'<article class="executive-kpi" data-kpi="{cls._text(kpi.field)}">'
            '<span class="kpi-accent" aria-hidden="true"></span>'
            f'<span class="kpi-label">{cls._text(kpi.name)}</span>'
            f'<strong class="kpi-value">{cls._number(kpi.value, decimals)}</strong>'
            f'<small>{cls._text(kpi.field)}</small></article>'
        )

    @classmethod
    def _panel(
        cls,
        section: str,
        number: str,
        title: str,
        subtitle: str,
        body: str,
        *,
        extra_class: str = "",
    ) -> str:
        css = f"report-panel {extra_class}".strip()
        return (
            f'<section class="{css}" data-section="{cls._text(section)}">'
            '<div class="panel-heading">'
            f'<span class="section-number">{cls._text(number)}</span>'
            f'<div><h2>{cls._text(title)}</h2><p>{cls._text(subtitle)}</p></div>'
            f"</div>{body}</section>"
        )

    @classmethod
    def _visual_card(
        cls, chart: ChartSpec, builder: Callable[[ChartSpec], str]
    ) -> str:
        return (
            f'<article class="visual-card" data-business-role="{cls._text(chart.business_role)}">'
            f'<div class="visual-card-heading"><h3>{cls._text(chart.title)}</h3>'
            f'<span>{cls._text(chart.y_field)}</span></div>{builder(chart)}</article>'
        )

    @classmethod
    def _line_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        width, height = 1200, 420
        left, right, top, bottom = 76, 36, 34, 78
        plot_width = width - left - right
        plot_height = height - top - bottom
        values = [cls._decimal(item["value"]) for item in points]
        lower = min(values)
        upper = max(values)
        if lower == upper:
            padding = max(abs(lower) * Decimal("0.1"), Decimal("1"))
        else:
            padding = (upper - lower) * Decimal("0.12")
        y_min = lower - padding
        y_max = upper + padding

        def x_at(index: int) -> Decimal:
            if len(points) == 1:
                return Decimal(left + plot_width / 2)
            return Decimal(left) + Decimal(index) * Decimal(plot_width) / Decimal(
                len(points) - 1
            )

        def y_at(value: Decimal) -> Decimal:
            ratio = (value - y_min) / (y_max - y_min)
            return Decimal(top + plot_height) - ratio * Decimal(plot_height)

        coords = [(x_at(index), y_at(value)) for index, value in enumerate(values)]
        polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
        area = (
            f"{coords[0][0]:.2f},{top + plot_height} {polyline} "
            f"{coords[-1][0]:.2f},{top + plot_height}"
        )
        grid = []
        for index in range(5):
            tick = y_min + (y_max - y_min) * Decimal(index) / Decimal(4)
            y = y_at(tick)
            grid.append(
                f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}"/>'
                f'<text x="{left-10}" y="{y:.2f}" dy="4" text-anchor="end">'
                f"{cls._axis_number(tick)}</text>"
            )
        circles = "".join(
            f'<circle class="trend-point" cx="{x:.2f}" cy="{y:.2f}" r="4" '
            f'data-source-value="{escape(format(value, "f"), quote=True)}">'
            f'<title>{cls._text(points[index]["label"])}：{cls._number(value, 2)}</title>'
            "</circle>"
            for index, ((x, y), value) in enumerate(zip(coords, values))
        )
        ticks = "".join(
            cls._trend_tick_groups(points, coords)
        )
        legend = (
            '<div class="chart-legend"><span class="legend-line"></span>'
            f'<span>{cls._text(chart.y_field)}</span></div>'
        )
        return (
            '<div class="executive-line-chart chart-frame">'
            f"{legend}<svg viewBox=\"0 0 {width} {height}\" "
            'preserveAspectRatio="xMidYMid meet" role="img" '
            f'aria-label="{cls._text(chart.title)}，{len(points)} 个已验证数据点">'
            '<g class="trend-grid">' + "".join(grid) + "</g>"
            f'<polygon class="trend-area" points="{area}"/>'
            f'<polyline class="trend-line" points="{polyline}"/>{circles}{ticks}'
            "</svg></div>"
        )

    @classmethod
    def _trend_tick_groups(
        cls,
        points: list[dict[str, Any]],
        coords: list[tuple[Decimal, Decimal]],
    ) -> list[str]:
        groups: list[str] = []
        for tier, maximum in (("desktop", 12), ("tablet", 8), ("mobile", 4)):
            indexes = cls._tick_indexes(len(points), maximum)
            texts = "".join(
                f'<text x="{coords[index][0]:.2f}" y="385" text-anchor="middle">'
                f'{cls._text(cls._short_period(points[index]["label"]))}</text>'
                for index in indexes
            )
            groups.append(f'<g class="trend-ticks trend-ticks--{tier}">{texts}</g>')
        return groups

    @staticmethod
    def _tick_indexes(count: int, maximum: int) -> tuple[int, ...]:
        if count <= maximum:
            return tuple(range(count))
        indexes = {
            round(index * (count - 1) / (maximum - 1)) for index in range(maximum)
        }
        return tuple(sorted(indexes))

    @staticmethod
    def _short_period(value: Any) -> str:
        rendered = str(value)
        return rendered[:7] if len(rendered) >= 7 else rendered

    @classmethod
    def _column_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        values = [cls._decimal(item["value"]) for item in points]
        maximum = max((abs(value) for value in values), default=Decimal("1")) or Decimal("1")
        columns = "".join(
            (
                '<div class="executive-column" tabindex="0">'
                f'<span class="column-value">{cls._number(value, 2)}</span>'
                '<span class="column-track" aria-hidden="true">'
                f'<span style="height:{(abs(value) * 100 / maximum):.2f}%"></span></span>'
                f'<span class="column-label">{cls._text(item["label"])}</span></div>'
            )
            for item, value in zip(points, values)
        )
        return (
            '<div class="executive-columns chart-frame" '
            f'style="--count:{len(points)}">{columns}</div>'
        )

    @classmethod
    def _donut_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        values = [abs(cls._decimal(item["value"])) for item in points]
        total = sum(values, Decimal("0"))
        if total <= 0:
            raise ValueError("executive_report_donut_total_invalid")
        offset = Decimal("0")
        segments: list[str] = []
        legend: list[str] = []
        for index, (item, value) in enumerate(zip(points, values), start=1):
            percent = (value * Decimal("100") / total).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            segments.append(
                f'<circle class="donut-segment donut-segment-{index}" cx="100" cy="100" r="70" '
                'pathLength="100" '
                f'stroke-dasharray="{percent:.2f} {Decimal("100")-percent:.2f}" '
                f'stroke-dashoffset="{-offset:.2f}"><title>{cls._text(item["label"])} '
                f'{percent:.2f}%</title></circle>'
            )
            legend.append(
                '<li><span class="legend-dot" '
                f'data-color-index="{index}"></span><span>{cls._text(item["label"])}</span>'
                f'<strong>{percent:.2f}%</strong></li>'
            )
            offset += percent
        return (
            '<div class="executive-donut chart-frame"><svg viewBox="0 0 200 200" '
            f'role="img" aria-label="{cls._text(chart.title)}">'
            '<circle class="donut-track" cx="100" cy="100" r="70"></circle>'
            + "".join(segments)
            + f'<text x="100" y="95" text-anchor="middle">{cls._number(total, 0)}</text>'
            '<text class="donut-caption" x="100" y="116" text-anchor="middle">总销售额</text>'
            '</svg><ul class="executive-legend">'
            + "".join(legend)
            + "</ul></div>"
        )

    @classmethod
    def _hbar_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        values = [cls._decimal(item["value"]) for item in points]
        maximum = max((abs(value) for value in values), default=Decimal("1")) or Decimal("1")
        rows = []
        for index, (item, value) in enumerate(zip(points, values), start=1):
            position = item.get("position")
            badge = (
                f'<span class="rank-badge">{cls._text(position)}</span>'
                if isinstance(position, int)
                else f'<span class="rank-badge muted">{index}</span>'
            )
            rows.append(
                '<div class="executive-bar-row" tabindex="0">'
                f'<div class="executive-bar-label">{badge}<span>{cls._text(item["label"])}</span></div>'
                '<div class="executive-bar-track" aria-hidden="true">'
                f'<span style="width:{(abs(value) * 100 / maximum):.2f}%"></span></div>'
                f'<strong>{cls._number(value, 2)}</strong></div>'
            )
        return '<div class="executive-hbars chart-frame">' + "".join(rows) + "</div>"

    @classmethod
    def _ranking_table(cls, table: TableSpec) -> str:
        headers = "".join(f'<th scope="col">{cls._text(item)}</th>' for item in table.columns)
        rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{cls._number(value, 2) if cls._is_number(value) else cls._text(value)}</td>"
                for value in row
            )
            + "</tr>"
            for row in table.rows
        )
        return (
            '<article class="visual-card detail-card" data-business-role="top_customers">'
            f'<div class="visual-card-heading"><h3>{cls._text(table.title)}</h3>'
            '<span>VERIFIED RANKING</span></div><div class="table-wrap"><table>'
            f"<thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div></article>"
        )

    @classmethod
    def _audit_footer(cls, report: ReportSpec) -> str:
        context = report.reading_context
        if context is None:
            raise ValueError("executive_report_reading_context_required")
        items = (
            ("数据来源", f"{context.data_source.display_name} / {context.data_source.kind.value}"),
            ("语义模型", context.semantic_model),
            ("分析期间", context.analysis_period.display_text),
            ("筛选状态", context.active_filters.display_text),
            ("数据新鲜度", context.data_freshness.display_text),
            ("生成时间", context.generated_at.isoformat()),
        )
        body = "".join(
            f'<div><span>{cls._text(label)}</span><strong>{cls._text(value)}</strong></div>'
            for label, value in items
        )
        return (
            '<footer class="audit-footer" data-section="audit_footer" '
            f'aria-label="报表审计信息">{body}</footer>'
        )

    @classmethod
    def _validate_spec(cls, report: ReportSpec) -> None:
        if report.template_key != "sales_executive_report":
            raise ValueError("executive_report_renderer_template_rejected")
        if report.title != "销售经营分析报告":
            raise ValueError("executive_report_title_invalid")
        context = report.reading_context
        snapshot = report.data_snapshot
        if context is None:
            raise ValueError("executive_report_reading_context_required")
        if snapshot is None:
            raise ValueError("executive_report_data_snapshot_required")
        if report.insights or report.filters:
            raise ValueError("executive_report_structure_invalid")
        if (
            report.generated_at != context.generated_at
            or report.semantic_model_key != context.semantic_model
            or report.semantic_model_key != snapshot.semantic_model_identity
            or report.schema_fingerprint != snapshot.schema_fingerprint
            or report.source_mode != snapshot.source_mode
            or report.data_source != context.semantic_model
            or tuple(report.query_result_ids) != snapshot.query_result_ids
            or tuple(report.verified_fact_set_ids) != snapshot.verified_fact_set_ids
            or not report.contract_version
        ):
            raise ValueError("executive_report_provenance_invalid")
        if not report.kpis and not report.charts and not report.tables:
            raise ValueError("executive_report_no_sections")
        cls._validate_kpis(report.kpis)
        cls._validate_charts(report.charts)
        cls._validate_tables(report.tables)
        used_measures = {
            *(item.field for item in report.kpis),
            *(item.y_field for item in report.charts),
        }
        defined_measures = {
            item.canonical_measure for item in context.metric_definitions
        }
        if not used_measures.issubset(defined_measures):
            raise ValueError("executive_report_metric_definition_incomplete")

    @classmethod
    def _validate_kpis(cls, kpis: list[KPISpec]) -> None:
        if len(kpis) > 4:
            raise ValueError("executive_report_kpi_count_invalid")
        seen: set[str] = set()
        for item in kpis:
            if item.field not in cls._ALLOWED_KPI_FIELDS or item.field in seen:
                raise ValueError("executive_report_kpi_field_unregistered")
            seen.add(item.field)
            if item.format not in {"number", "currency"}:
                raise ValueError("executive_report_kpi_format_invalid")
            cls._decimal(item.value)

    @classmethod
    def _validate_charts(cls, charts: list[ChartSpec]) -> None:
        seen: set[str] = set()
        for chart in charts:
            if chart.business_role not in cls._ALLOWED_CHART_ROLES:
                raise ValueError("executive_report_chart_role_unregistered")
            if chart.business_role in seen:
                raise ValueError("executive_report_chart_role_duplicate")
            seen.add(chart.business_role)
            if chart.visual_type not in cls._ALLOWED_VISUAL_TYPES:
                raise ValueError("executive_report_chart_visual_unregistered")
            expected = {
                "time_trend": {"line"},
                "category_contribution": {"donut", "hbar"},
                "region_comparison": {"column", "hbar"},
                "top_products": {"hbar"},
                "top_customers": {"hbar"},
            }[chart.business_role]
            if chart.visual_type not in expected:
                raise ValueError("executive_report_chart_visual_role_invalid")
            points = cls._series(chart)
            positions: list[int] = []
            for item in points:
                if not isinstance(item.get("label"), str) or not item["label"]:
                    raise ValueError("executive_report_chart_series_invalid")
                cls._decimal(item.get("value"))
                position = item.get("position")
                if position is not None:
                    if not isinstance(position, int) or position < 1:
                        raise ValueError("executive_report_chart_series_invalid")
                    positions.append(position)
            if chart.business_role in {"top_products", "top_customers"}:
                if positions != list(range(1, len(points) + 1)):
                    raise ValueError("executive_report_ranking_order_invalid")
            elif positions:
                raise ValueError("executive_report_nonranking_position_invalid")
            if chart.visual_type == "donut" and len(points) < 2:
                raise ValueError("executive_report_donut_requires_two_slices")

    @classmethod
    def _validate_tables(cls, tables: list[TableSpec]) -> None:
        if len(tables) > 1:
            raise ValueError("executive_report_table_count_invalid")
        for table in tables:
            if table.title != "Top 客户" or table.columns != ["排名", "客户", "销售额（元）"]:
                raise ValueError("executive_report_table_binding_invalid")
            if not table.rows or len(table.rows) > 50:
                raise ValueError("executive_report_table_rows_invalid")
            for index, row in enumerate(table.rows, start=1):
                if (
                    len(row) != 3
                    or row[0] != index
                    or not isinstance(row[1], str)
                    or not row[1]
                ):
                    raise ValueError("executive_report_table_rows_invalid")
                cls._decimal(row[2])

    @classmethod
    def _series(cls, chart: ChartSpec) -> list[dict[str, Any]]:
        if not chart.series or len(chart.series) > cls._MAX_SERIES:
            raise ValueError("executive_report_chart_series_invalid")
        return list(chart.series)

    @staticmethod
    def _text(value: Any) -> str:
        return escape(str(value), quote=True)

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if isinstance(value, bool):
            raise ValueError("executive_report_number_invalid")
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("executive_report_number_invalid") from exc
        if not number.is_finite():
            raise ValueError("executive_report_number_invalid")
        return number

    @classmethod
    def _number(cls, value: Any, decimals: int) -> str:
        return escape(format(cls._decimal(value), f",.{decimals}f"), quote=True)

    @classmethod
    def _axis_number(cls, value: Decimal) -> str:
        absolute = abs(value)
        if absolute >= Decimal("1000000"):
            return f"{(value / Decimal('1000000')):.1f}M"
        if absolute >= Decimal("1000"):
            return f"{(value / Decimal('1000')):.1f}K"
        return f"{value:.0f}"

    @staticmethod
    def _validate_rendered_html(html: str) -> None:
        lowered = html.casefold()
        if (
            not html.startswith("<!DOCTYPE html>")
            or "</html>" not in lowered
            or "<script" in lowered
            or "javascript:" in lowered
            or "http://" in lowered
            or "https://" in lowered
            or "<link" in lowered
            or "<iframe" in lowered
            or "<object" in lowered
            or "<embed" in lowered
            or "@import" in lowered
            or "url(" in lowered
            or re.search(r"<[^>]+\ssrc\s*=", lowered) is not None
        ):
            raise ValueError("executive_report_static_html_validation_failed")
