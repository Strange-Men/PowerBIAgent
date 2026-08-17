"""Production adaptive renderer for the sales_report design system.

The design system is fixed (ADR-011): KPI cards, line, donut, column and
horizontal-bar visuals, fixed layout slots, theme tokens and security rules.
*Which* sections render is decided earlier by the deterministic planner and
capability engine — this renderer never decides business content, never calls
an LLM, never touches Power BI, and never invents numbers.  Unavailable
sections emit nothing; no placeholders, no mock charts.

All geometry is projected from the verified ``series`` values of the
ReportSpec (which the assembler proved against the FactSets).  Text is HTML
escaped; the output is self-contained static UTF-8 HTML with inline SVG and
no JS/CDN/external resources.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from pathlib import Path
from string import Template
from typing import Any

from backend.app.report.base import ReportRenderer
from backend.app.report.capability import SectionKey
from backend.app.report.policy import (
    LayoutPolicy,
    ThemePolicy,
    VisualType,
)
from backend.app.schemas.data_contracts import ChartSpec, KPISpec, ReportSpec


class SalesReportRenderer(ReportRenderer):
    """Render a validated adaptive ReportSpec as self-contained static HTML."""

    _TEMPLATE_PATH = Path(__file__).with_name("templates") / "sales_report.html"
    _SUPPORTED_TEMPLATES = ("sales_report",)
    _ALLOWED_KPI_FIELDS = frozenset({
        "Total Sales",
        "Total Quantity",
        "Total Orders",
        "Average Order Value",
    })
    # Charts may only carry analysis-section roles.  KPI sections are KPI
    # cards; a chart claiming a KPI role is rejected (structure integrity).
    _ALLOWED_CHART_ROLES = frozenset({
        SectionKey.TIME_TREND.value,
        SectionKey.CATEGORY_CONTRIBUTION.value,
        SectionKey.REGION_COMPARISON.value,
        SectionKey.TOP_PRODUCTS.value,
        SectionKey.TOP_CUSTOMERS.value,
    })
    _ALLOWED_VISUAL_TYPES = frozenset(item.value for item in VisualType)
    _ALLOWED_LAYOUT_HINTS = frozenset({"full", "half"})
    _MAX_SERIES = 200
    _LINE_WIDTH = 600
    _LINE_HEIGHT = 220

    @property
    def supported_templates(self) -> list[str]:
        return list(self._SUPPORTED_TEMPLATES)

    async def render(self, report: ReportSpec) -> str:
        self._validate_spec(report)
        template = Template(self._TEMPLATE_PATH.read_text(encoding="utf-8"))

        charts_by_role = {item.business_role: item for item in report.charts}

        # ── Fixed layout slots (LayoutPolicy).  Every block is built by the
        # renderer only when its sections exist — empty sections never render.
        kpi_block = (
            '<section class="kpi-grid" aria-label="关键指标">'
            + "\n".join(self._kpi_card(item) for item in report.kpis)
            + "</section>"
            if report.kpis
            else ""
        )
        trend_block = (
            self._wide_section(
                SectionKey.TIME_TREND,
                charts_by_role[SectionKey.TIME_TREND.value],
                self._line_chart,
            )
            if SectionKey.TIME_TREND.value in charts_by_role
            else ""
        )
        pair_one_block = self._pair_block(
            charts_by_role,
            (SectionKey.CATEGORY_CONTRIBUTION, SectionKey.REGION_COMPARISON),
        )
        pair_two_block = self._pair_block(
            charts_by_role,
            (SectionKey.TOP_PRODUCTS, SectionKey.TOP_CUSTOMERS),
        )

        generated_at = report.generated_at
        if generated_at is None:
            raise ValueError("sales_report_generated_at_required")
        footer_items = [
            f"数据来源：{self._text(report.data_source)}",
            f"执行模式：{self._text(report.source_mode)}",
            f"合同版本：{self._text(report.contract_version)}",
            f"生成时间：{self._text(generated_at.isoformat())}",
        ]
        html = template.substitute(
            title=self._text(report.title),
            kpi_block=kpi_block,
            trend_block=trend_block,
            pair_one_block=pair_one_block,
            pair_two_block=pair_two_block,
            footer=" · ".join(footer_items),
        )
        self._validate_rendered_html(html)
        return html

    # ── Layout helpers ──

    @staticmethod
    def _chart_body(chart: ChartSpec) -> str:
        if chart.visual_type == VisualType.DONUT.value:
            return SalesReportRenderer._donut_chart(chart)
        if chart.visual_type == VisualType.COLUMN.value:
            return SalesReportRenderer._column_chart(chart)
        return SalesReportRenderer._hbar_chart(chart)

    @classmethod
    def _wide_section(
        cls,
        key: SectionKey,
        chart: ChartSpec,
        body_builder: Any,
    ) -> str:
        body = body_builder(chart)
        return (
            f'<section class="section-card wide" data-section="{key.value}">'
            f'<h2 class="section-title">{cls._text(chart.title)}</h2>'
            f"{body}"
            "</section>"
        )

    @classmethod
    def _half_section(cls, key: SectionKey, chart: ChartSpec) -> str:
        return (
            f'<section class="section-card half" data-section="{key.value}">'
            f'<h2 class="section-title">{cls._text(chart.title)}</h2>'
            f"{cls._chart_body(chart)}"
            "</section>"
        )

    @classmethod
    def _pair_block(
        cls,
        charts_by_role: dict[str, ChartSpec],
        pair: tuple[SectionKey, SectionKey],
    ) -> str:
        """Render a layout pair.  Two sections → two half cards in a grid;
        one section → one full-width card; none → nothing."""
        present = [
            (key, charts_by_role[key.value])
            for key in pair
            if key.value in charts_by_role
        ]
        if not present:
            return ""
        if len(present) == 1:
            key, chart = present[0]
            return cls._wide_section(key, chart, cls._chart_body)
        rendered = [
            cls._half_section(key, chart) for key, chart in present
        ]
        return '<div class="pair" aria-label="对比区块">' + "\n".join(rendered) + "</div>"

    # ── KPI cards ──

    @classmethod
    def _kpi_card(cls, kpi: KPISpec) -> str:
        decimals = 2 if kpi.format == "currency" else 0
        return (
            f'<article class="kpi-card" data-kpi="{cls._text(kpi.field)}">'
            f'<span class="kpi-label">{cls._text(kpi.name)}</span>'
            f'<span class="kpi-value">{cls._number(kpi.value, decimals=decimals)}</span>'
            "</article>"
        )

    # ── Line chart (time series) ──

    @classmethod
    def _line_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        width = cls._LINE_WIDTH
        height = cls._LINE_HEIGHT
        pad_left, pad_right = 46, 16
        pad_top, pad_bottom = 14, 34
        plot_w = width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom

        values = [Decimal(str(item["value"])) for item in points]
        minimum = min(values)
        maximum = max(values)
        span = maximum - minimum
        if span == 0:
            span = Decimal("1")
        # 8% headroom so the top label never clips
        upper = maximum + span * Decimal("0.08")
        lower = minimum - span * Decimal("0.08")

        def scale_x(index: int) -> str:
            x = (
                pad_left
                if len(points) == 1
                else pad_left + index * plot_w / (len(points) - 1)
            )
            return f"{x:.2f}"

        def scale_y(value: Decimal) -> str:
            ratio = (value - lower) / (upper - lower)
            y = pad_top + plot_h - ratio * plot_h
            return f"{y:.2f}"

        coords = [
            (scale_x(index), scale_y(value))
            for index, value in enumerate(values)
        ]
        line_points = " ".join(f"{x},{y}" for x, y in coords)
        if len(coords) >= 2:
            area_points = (
                f"{pad_left},{pad_top + plot_h} "
                + line_points
                + f" {scale_x(len(points) - 1)},{pad_top + plot_h}"
            )
            area = (
                f'<polygon points="{area_points}" fill="{ThemePolicy.SEQUENTIAL_100}" '
                f'stroke="none" aria-hidden="true"/>'
            )
        else:
            area = ""

        circles = []
        for index, (value, (x, y)) in enumerate(zip(values, coords)):
            circles.append(
                f'<circle cx="{x}" cy="{y}" r="3.5" '
                f'fill="{ThemePolicy.SEQUENTIAL_400}" stroke="{ThemePolicy.SURFACE}" '
                f'stroke-width="1.5" '
                f'data-point="{index + 1}" '
                f'data-source-value="{escape(format(value, "f"), quote=True)}" '
                f'aria-label="{cls._text(chart.y_field)}={cls._number(value, decimals=2)}"/>'
            )

        labels: list[str] = []
        labeled_indexes: set[int] = set()
        for index in (0, len(points) - 1):
            if index not in labeled_indexes:
                labeled_indexes.add(index)
                labels.append(cls._axis_period_label(
                    points[index]["label"],
                    scale_x(index),
                ))
        middle = len(points) // 2
        if len(points) > 2 and middle not in labeled_indexes:
            labels.append(cls._axis_period_label(
                points[middle]["label"], scale_x(middle)
            ))

        direct_labels = ""
        if points:
            # Selective direct labels: first, last, and the maximum point.
            direct: list[tuple[int, str]] = []
            max_index = max(range(len(values)), key=lambda i: values[i])
            for index in sorted({0, len(points) - 1, max_index}):
                direct.append((index, values[index]))
            for index, value in direct:
                x, y = coords[index]
                anchor = (
                    "end" if index == 0 else "start" if index == len(points) - 1 else "middle"
                )
                dy = "-6" if index == max_index else "14"
                direct_labels += (
                    f'<text x="{x}" y="{y}" dy="{dy}" text-anchor="{anchor}" '
                    f'class="chart-direct-label">'
                    f"{cls._number(value, decimals=2)}</text>"
                )

        return (
            f'<div class="chart chart-line" data-chart="time_trend">'
            f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{cls._text(chart.title)}">'
            f'{area}{"".join(circles)}'
            f'<polyline points="{line_points}" fill="none" '
            f'stroke="{ThemePolicy.SEQUENTIAL_550}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            f"{''.join(labels)}{direct_labels}"
            "</svg>"
            "</div>"
        )

    @classmethod
    def _axis_period_label(cls, period: str, x: str) -> str:
        anchor = "start" if float(x) < 60 else "middle"
        return (
            f'<text x="{x}" y="{cls._LINE_HEIGHT - 8}" text-anchor="{anchor}" '
            f'class="chart-axis-label">{cls._text(period)}</text>'
        )

    # ── Donut chart (category composition) ──

    @classmethod
    def _donut_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        total = sum((Decimal(str(item["value"])) for item in points), Decimal("0"))
        if total <= 0:
            raise ValueError("sales_report_donut_total_invalid")
        colors = ThemePolicy.CATEGORICAL
        if len(points) > len(colors):
            raise ValueError("sales_report_donut_too_many_slices")

        arcs: list[str] = []
        legend: list[str] = []
        cumulative = Decimal("0")
        for index, item in enumerate(points):
            percent = (Decimal(str(item["value"])) * Decimal("100") / total).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            color = colors[index]
            arcs.append(
                f'<circle class="donut-segment" data-slice="{index + 1}" '
                f'data-slice-percent="{format(percent, ".2f")}" '
                f'data-source-value="{escape(format(Decimal(str(item["value"])), "f"), quote=True)}" '
                f'cx="130" cy="130" r="86" fill="none" '
                f'stroke="{color}" stroke-width="34" pathLength="100" '
                f'stroke-dasharray="{format(percent, ".2f")} 100" '
                f'stroke-dashoffset="{format(-cumulative, ".2f")}" '
                f'stroke-linecap="butt"/>'
            )
            cumulative += percent
            legend.append(
                f'<li class="donut-legend-item">'
                f'<span class="legend-swatch" style="background:{color}" aria-hidden="true"></span>'
                f'<span class="legend-label">{cls._text(item["label"])}</span>'
                f'<span class="legend-value">{cls._number(item["value"], decimals=2)}</span>'
                f'<span class="legend-percent">{format(percent, ".2f")}%</span>'
                f"</li>"
            )

        return (
            f'<div class="chart chart-donut" data-chart="{cls._text(chart.business_role)}">'
            f'<div class="donut-svg">'
            f'<svg viewBox="0 0 260 260" role="img" aria-label="{cls._text(chart.title)}">'
            f'<circle cx="130" cy="130" r="86" fill="none" '
            f'stroke="{ThemePolicy.TRACK}" stroke-width="34" aria-hidden="true"/>'
            f'{"".join(arcs)}'
            "</svg>"
            "</div>"
            f'<ul class="donut-legend">{"".join(legend)}</ul>'
            "</div>"
        )

    # ── Column chart (region comparison) ──

    @classmethod
    def _column_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        values = [Decimal(str(item["value"])) for item in points]
        maximum = max((abs(value) for value in values), default=Decimal("0"))
        bars: list[str] = []
        for index, (item, value) in enumerate(zip(points, values)):
            percent = (
                Decimal("0")
                if maximum == 0
                else (abs(value) * Decimal("100") / maximum).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
            state_class = " negative" if value < 0 else " zero" if value == 0 else ""
            bars.append(
                f'<div class="column-item{state_class}" data-column="{index + 1}">'
                f'<span class="column-value">{cls._number(value, decimals=2)}</span>'
                f'<div class="column-track" aria-hidden="true">'
                f'<span class="column-fill" style="height: {format(percent, ".2f")}%" '
                f'data-source-value="{escape(format(value, "f"), quote=True)}" '
                f'data-column-percent="{format(percent, ".2f")}"></span>'
                "</div>"
                f'<span class="column-label">{cls._text(item["label"])}</span>'
                "</div>"
            )
        return (
            f'<div class="chart chart-column" data-chart="{cls._text(chart.business_role)}">'
            f'{"".join(bars)}'
            "</div>"
        )

    # ── Horizontal bar chart (Top N / ranking) ──

    @classmethod
    def _hbar_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        values = [Decimal(str(item["value"])) for item in points]
        maximum = max((abs(value) for value in values), default=Decimal("0"))
        rows: list[str] = []
        for index, (item, value) in enumerate(zip(points, values)):
            percent = (
                Decimal("0")
                if maximum == 0
                else (abs(value) * Decimal("100") / maximum).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
            state_class = " negative" if value < 0 else " zero" if value == 0 else ""
            position = item.get("position")
            position_html = (
                f'<span class="result-position">结果序号 {cls._text(str(position))}</span>'
                if isinstance(position, int)
                else ""
            )
            rows.append(
                f'<div class="bar-row{state_class}" '
                f'data-source-value="{escape(format(value, "f"), quote=True)}" '
                f'data-bar-percent="{format(percent, ".2f")}" '
                f'aria-label="{cls._text(item["label"])}，{cls._text(chart.y_field)} '
                f'{cls._number(value, decimals=2)}">'
                f'<div class="bar-label">{position_html}'
                f'<span class="bar-name">{cls._text(item["label"])}</span></div>'
                '<div class="bar-track" aria-hidden="true">'
                f'<span class="bar-fill" style="width: {format(percent, ".2f")}%"></span>'
                "</div>"
                f'<div class="bar-value">{cls._number(value, decimals=2)}</div>'
                "</div>"
            )
        return (
            f'<div class="chart chart-hbar" data-chart="{cls._text(chart.business_role)}">'
            f'{"".join(rows)}'
            "</div>"
        )

    # ── Shared helpers ──

    @staticmethod
    def _series(chart: ChartSpec) -> list[dict[str, Any]]:
        if not chart.series:
            raise ValueError("sales_report_chart_series_empty")
        if len(chart.series) > SalesReportRenderer._MAX_SERIES:
            raise ValueError("sales_report_chart_series_oversized")
        return list(chart.series)

    @staticmethod
    def _text(value: Any) -> str:
        return escape(str(value), quote=True)

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if isinstance(value, bool):
            raise ValueError("sales_report_number_invalid")
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("sales_report_number_invalid") from exc
        if not number.is_finite():
            raise ValueError("sales_report_number_invalid")
        return number

    @classmethod
    def _number(cls, value: Any, *, decimals: int) -> str:
        number = cls._decimal(value)
        return escape(format(number, f",.{decimals}f"), quote=True)

    @classmethod
    def _validate_spec(cls, report: ReportSpec) -> None:
        if report.template_key != "sales_report":
            raise ValueError("sales_report_renderer_template_rejected")
        if report.title != "销售分析报表":
            raise ValueError("sales_report_title_invalid")
        if report.tables or report.insights or report.filters:
            raise ValueError("sales_report_structure_invalid")
        if (
            not report.contract_version
            or not report.semantic_model_key
            or len(report.schema_fingerprint) != 64
            or not report.query_result_ids
            or len(report.query_result_ids) != len(set(report.query_result_ids))
            or not report.verified_fact_set_ids
            or len(report.verified_fact_set_ids) != len(set(report.verified_fact_set_ids))
            or len(report.query_result_ids) != len(report.verified_fact_set_ids)
            or report.source_mode not in {"mock", "real"}
            or report.data_source != report.semantic_model_key
            or report.generated_at is None
        ):
            raise ValueError("sales_report_provenance_invalid")
        if not report.kpis and not report.charts:
            raise ValueError("sales_report_no_sections")
        cls._validate_kpis(report.kpis)
        cls._validate_charts(report.charts)

    @classmethod
    def _validate_kpis(cls, kpis: list[KPISpec]) -> None:
        seen_fields: set[str] = set()
        for kpi in kpis:
            if not kpi.name:
                raise ValueError("sales_report_kpi_name_invalid")
            if kpi.field not in cls._ALLOWED_KPI_FIELDS:
                raise ValueError("sales_report_kpi_field_unregistered")
            if kpi.field in seen_fields:
                raise ValueError("sales_report_kpi_duplicate_field")
            seen_fields.add(kpi.field)
            if kpi.format not in {"number", "currency"}:
                raise ValueError("sales_report_kpi_format_invalid")
            cls._decimal(kpi.value)

    @classmethod
    def _validate_charts(cls, charts: list[ChartSpec]) -> None:
        seen_roles: set[str] = set()
        for chart in charts:
            if chart.business_role not in cls._ALLOWED_CHART_ROLES:
                raise ValueError("sales_report_chart_role_unregistered")
            if chart.business_role in seen_roles:
                raise ValueError("sales_report_chart_duplicate_role")
            seen_roles.add(chart.business_role)
            if chart.visual_type not in cls._ALLOWED_VISUAL_TYPES:
                raise ValueError("sales_report_chart_visual_unregistered")
            if chart.layout_hint not in cls._ALLOWED_LAYOUT_HINTS:
                raise ValueError("sales_report_chart_layout_hint_invalid")
            if not chart.title:
                raise ValueError("sales_report_chart_title_invalid")
            if not chart.x_field or not chart.y_field:
                raise ValueError("sales_report_chart_binding_invalid")
            series = cls._series(chart)
            seen_positions: set[int] = set()
            for item in series:
                if not isinstance(item, dict):
                    raise ValueError("sales_report_chart_series_invalid")
                label = item.get("label")
                if not isinstance(label, str) or not label:
                    raise ValueError("sales_report_chart_series_invalid")
                value = item.get("value")
                cls._decimal(value)
                position = item.get("position")
                if position is not None:
                    # Only verified TopN rows may carry a result_position.
                    if not isinstance(position, int) or position < 1:
                        raise ValueError("sales_report_chart_series_invalid")
                    if position in seen_positions:
                        raise ValueError("sales_report_chart_series_invalid")
                    seen_positions.add(position)
            if chart.visual_type == VisualType.DONUT.value and len(series) < 2:
                raise ValueError("sales_report_donut_requires_two_slices")

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
            or "src=" in lowered
        ):
            raise ValueError("sales_report_static_html_validation_failed")
