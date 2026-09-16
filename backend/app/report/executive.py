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
from backend.app.report.executive_contract import EXECUTIVE_TEMPLATE_CONTRACT
from backend.app.report.presentation import (
    ProfessionalReportPresenter,
    ReportPresentationProjection,
)
from backend.app.schemas.data_contracts import ChartSpec, KPISpec, ReportSpec, TableSpec


class ExecutiveSalesReportRenderer(ReportRenderer):
    """Render ``sales_executive_report`` as self-contained static HTML."""

    _TEMPLATE_PATH = (
        Path(__file__).with_name("templates") / "sales_executive_report.html"
    )
    _SUPPORTED_TEMPLATES = (EXECUTIVE_TEMPLATE_CONTRACT.template_key,)
    _ALLOWED_KPI_FIELDS = frozenset(
        item.field for item in EXECUTIVE_TEMPLATE_CONTRACT.kpi_slots
    )
    _ALLOWED_CHART_ROLES = frozenset(
        item.business_role
        for item in EXECUTIVE_TEMPLATE_CONTRACT.visual_slots
        if item.visual_type != "table"
    )
    _ALLOWED_VISUAL_TYPES = frozenset(
        item.visual_type
        for item in EXECUTIVE_TEMPLATE_CONTRACT.visual_slots
        if item.visual_type != "table"
    )
    _MAX_SERIES = 200
    _KPI_ICON_PATHS = {
        "sales": (
            '<path d="M4 17V11M10 17V7M16 17V3"/>'
            '<path d="M2 20h20"/>'
        ),
        "quantity": (
            '<path d="m4 7 8-4 8 4-8 4-8-4Z"/>'
            '<path d="M4 7v10l8 4 8-4V7M12 11v10"/>'
        ),
        "orders": (
            '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z"/>'
            '<path d="M9 8h6M9 12h6"/>'
        ),
        "average": (
            '<circle cx="9" cy="12" r="5"/>'
            '<path d="M14 7h5v10h-5M7 12h4M9 10v4"/>'
        ),
    }

    @property
    def supported_templates(self) -> list[str]:
        return list(self._SUPPORTED_TEMPLATES)

    async def render(self, report: ReportSpec) -> str:
        self._validate_spec(report)
        context = report.reading_context
        if context is None:  # narrowed by validation; keep type-safe.
            raise ValueError("executive_report_reading_context_required")
        projection = ProfessionalReportPresenter().project(report)

        charts = {item.business_role: item for item in report.charts}
        kpi_block = self._kpi_block(report.kpis, projection)
        trend_block = (
            self._panel(
                "hero_sales_trend",
                "02",
                "销售趋势",
                "SALES TREND",
                self._line_chart(charts["time_trend"], projection),
                extra_class="hero-panel",
            )
            if "time_trend" in charts
            else ""
        )

        structure_cards: list[str] = []
        if "region_comparison" in charts:
            structure_cards.append(
                self._visual_card(
                    charts["region_comparison"], self._column_chart, projection
                )
            )
        if "category_contribution" in charts:
            structure_cards.append(
                self._visual_card(
                    charts["category_contribution"], self._donut_chart, projection
                )
            )
        if "top_products" in charts:
            structure_cards.append(
                self._visual_card(
                    charts["top_products"], self._hbar_chart, projection
                )
            )
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

        customer_cards = [self._ranking_table(item) for item in report.tables]
        customer_block = (
            self._panel(
                "customer_analysis",
                "04",
                "客户分析",
                "CUSTOMER ANALYSIS",
                '<div class="executive-grid customer-grid">'
                + "".join(customer_cards)
                + "</div>",
                extra_class="customer-analysis--ranking-only",
            )
            if customer_cards
            else ""
        )

        section_blocks = {
            "kpi_summary": kpi_block,
            "hero_sales_trend": trend_block,
            "business_structure": structure_block,
            "customer_analysis": customer_block,
            "detail": "",
        }
        content_blocks = "".join(
            section_blocks[section]
            for section in EXECUTIVE_TEMPLATE_CONTRACT.section_order
            if section_blocks[section]
        )

        template = Template(self._TEMPLATE_PATH.read_text(encoding="utf-8"))
        html = template.substitute(
            title=self._text(context.report_title),
            analysis_period=self._text(projection.analysis_period_display),
            semantic_model=self._text(projection.model_display_name),
            source_display=self._text(projection.source_display_name),
            freshness=self._text(projection.freshness_display),
            generated_at=self._text(projection.generated_at_display),
            theme_variables=EXECUTIVE_TEMPLATE_CONTRACT.css_variables(),
            layout_contract=self._text(EXECUTIVE_TEMPLATE_CONTRACT.contract_key),
            detail_state="detail_unavailable",
            reading_context=self._reading_context(report, projection),
            content_blocks=content_blocks,
            audit_footer=self._audit_footer(report, projection),
        )
        self._validate_rendered_html(html)
        return html

    @classmethod
    def _reading_context(
        cls,
        report: ReportSpec,
        projection: ReportPresentationProjection,
    ) -> str:
        context = report.reading_context
        if context is None:
            raise ValueError("executive_report_reading_context_required")
        return (
            '<section class="reading-context context-strip" '
            'data-section="reading_context" aria-labelledby="reading-context-title">'
            '<div class="context-grid">'
            '<article class="context-card context-card--filter"><span>当前筛选</span>'
            f'<strong>{cls._text(projection.filter_display)}</strong>'
            '<span>实际数据覆盖：'
            f'{cls._text(projection.observed_coverage_display)}</span></article>'
            '<article class="context-card context-card--definition">'
            '<span id="reading-context-title">指标口径</span>'
            f'<strong>{cls._text(projection.metric_summary)}</strong></article>'
            '<article class="context-card context-card--exception"><span>经营状态</span>'
            f'<strong>{cls._text(projection.exception_display)}</strong></article>'
            '</div></section>'
        )

    @classmethod
    def _metric_definition(cls, definition: Any) -> str:
        return (
            '<div class="metric-definition">'
            f'<strong>{cls._text(definition.display_name)}</strong>'
            f'<code>{cls._text(definition.canonical_source)}</code>'
            f'<span>{cls._text(definition.aggregation_display)} · '
            f'{cls._text(definition.unit_display)}</span>'
            f'<small>税务口径：{cls._text(definition.tax_basis_display)}</small>'
            f'<small>比较基准：{cls._text(definition.comparison_basis_display)}</small>'
            "</div>"
        )

    @classmethod
    def _kpi_block(
        cls,
        kpis: list[KPISpec],
        projection: ReportPresentationProjection,
    ) -> str:
        if not kpis:
            return ""
        cards = "".join(cls._kpi_card(item, projection) for item in kpis)
        return cls._panel(
            "kpi_summary",
            "01",
            "关键指标概览",
            "EXECUTIVE SUMMARY",
            f'<div class="kpi-grid">{cards}</div>',
        )

    @classmethod
    def _kpi_card(
        cls,
        kpi: KPISpec,
        projection: ReportPresentationProjection,
    ) -> str:
        decimals = 2 if kpi.format == "currency" else 0
        slot = EXECUTIVE_TEMPLATE_CONTRACT.kpi_for_field(kpi.field)
        icon = cls._KPI_ICON_PATHS[slot.icon]
        return (
            f'<article class="executive-kpi" data-kpi="{cls._text(kpi.field)}" '
            f'data-kpi-tone="{slot.tone}">'
            '<span class="kpi-icon" aria-hidden="true"><svg viewBox="0 0 24 24" '
            f'focusable="false">{icon}</svg></span><div class="kpi-copy">'
            f'<span class="kpi-label">{cls._text(kpi.name)}</span>'
            f'<strong class="kpi-value">{cls._number(kpi.value, decimals)}</strong>'
            f'<small>{cls._text(projection.metric_unit(kpi.field))}</small></div></article>'
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
        cls,
        chart: ChartSpec,
        builder: Callable[[ChartSpec], str],
        projection: ReportPresentationProjection,
    ) -> str:
        return (
            f'<article class="visual-card" data-business-role="{cls._text(chart.business_role)}">'
            f'<div class="visual-card-heading"><h3>{cls._text(chart.title)}</h3>'
            f'<span>{cls._text(projection.metric_label(chart.y_field))} · '
            f'{cls._text(projection.metric_unit(chart.y_field))}</span></div>'
            f'{builder(chart)}</article>'
        )

    @classmethod
    def _line_chart(
        cls,
        chart: ChartSpec,
        projection: ReportPresentationProjection,
    ) -> str:
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
            f'<span>{cls._text(projection.metric_label(chart.y_field))}</span></div>'
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
        limits = (
            ("desktop", EXECUTIVE_TEMPLATE_CONTRACT.desktop_trend_label_limit),
            ("tablet", EXECUTIVE_TEMPLATE_CONTRACT.tablet_trend_label_limit),
            ("mobile", EXECUTIVE_TEMPLATE_CONTRACT.mobile_trend_label_limit),
        )
        for tier, maximum in limits:
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
        legend_limit = EXECUTIVE_TEMPLATE_CONTRACT.donut_legend_limit
        for index, (item, value) in enumerate(zip(points, values), start=1):
            color_index = (index - 1) % legend_limit + 1
            percent = (value * Decimal("100") / total).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            segments.append(
                f'<circle class="donut-segment donut-color-{color_index}" cx="100" cy="100" r="70" '
                'pathLength="100" '
                f'stroke-dasharray="{percent:.2f} {Decimal("100")-percent:.2f}" '
                f'stroke-dashoffset="{-offset:.2f}"><title>{cls._text(item["label"])} '
                f'{percent:.2f}%</title></circle>'
            )
            if index <= legend_limit:
                legend.append(
                    '<li><span class="legend-dot" '
                    f'data-color-index="{color_index}"></span><span>{cls._text(item["label"])}</span>'
                    f'<strong>{percent:.2f}%</strong></li>'
                )
            offset += percent
        legend_note = (
            f'<p class="legend-note">还有 {len(points) - legend_limit} 项未在图例展开</p>'
            if len(points) > legend_limit
            else ""
        )
        return (
            '<div class="executive-donut chart-frame"><svg viewBox="0 0 200 200" '
            f'role="img" aria-label="{cls._text(chart.title)}">'
            '<circle class="donut-track" cx="100" cy="100" r="70"></circle>'
            + "".join(segments)
            + f'<text x="100" y="95" text-anchor="middle">{cls._number(total, 0)}</text>'
            '<text class="donut-caption" x="100" y="116" text-anchor="middle">总销售额</text>'
            '</svg><ul class="executive-legend">'
            + "".join(legend)
            + f"</ul>{legend_note}</div>"
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
                f'<span class="rank-badge">#{cls._text(position)}</span>'
                if isinstance(position, int)
                else f'<span class="rank-badge muted">#{index}</span>'
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
            + f'<td class="rank-cell">{cls._number(row[0], 0)}</td>'
            + f"<td>{cls._text(row[1])}</td>"
            + f'<td class="number-cell">{cls._number(row[2], 2)}</td>'
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
    def _audit_footer(
        cls,
        report: ReportSpec,
        projection: ReportPresentationProjection,
    ) -> str:
        context = report.reading_context
        if context is None:
            raise ValueError("executive_report_reading_context_required")
        items = (
            ("模型标识", projection.canonical_model_identity),
            ("来源类型", projection.canonical_source_kind.value),
            ("运行模式", projection.canonical_source_mode),
            ("查询取得时间", projection.canonical_queried_at),
            ("快照时间", projection.canonical_snapshot_at),
            ("生成时间", projection.canonical_generated_at),
        )
        body = "".join(
            f'<div><span>{cls._text(label)}</span><strong>{cls._text(value)}</strong></div>'
            for label, value in items
        )
        return (
            '<footer class="audit-footer" data-section="audit_footer" '
            f'aria-label="报表审计信息">{body}'
            '<div class="audit-definitions"><span>指标定义</span>'
            '<div class="metric-definition-list">'
            + "".join(
                cls._metric_definition(item)
                for item in projection.metric_definitions
            )
            + "</div></div></footer>"
        )

    @classmethod
    def _validate_spec(cls, report: ReportSpec) -> None:
        if report.template_key != EXECUTIVE_TEMPLATE_CONTRACT.template_key:
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
            expected = EXECUTIVE_TEMPLATE_CONTRACT.visual_for_role(
                chart.business_role
            ).visual_type
            if chart.visual_type != expected:
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
            if chart.business_role == "top_products":
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
            if table.title != "Top 客户" or table.columns != ["排名", "客户", "销售额"]:
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
            or re.search(r"(?:href|src)\s*=\s*[\"']?\s*javascript:", lowered)
            is not None
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
