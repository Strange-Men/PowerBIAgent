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

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from pathlib import Path
import re
from string import Template
from typing import Any

from backend.app.report.base import ReportRenderer
from backend.app.report.capability import SectionKey
from backend.app.report.policy import (
    LayoutPolicy,
    ThemePolicy,
    VisualType,
)
from backend.app.schemas.data_contracts import ChartSpec, KPISpec, ReportSpec, TableSpec


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
    _LINE_WIDTH = 1000
    _LINE_HEIGHT = 380
    _PERIOD_PATTERN = re.compile(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?(?:[T ].*)?$")

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
            (SectionKey.REGION_COMPARISON, SectionKey.CATEGORY_CONTRIBUTION),
        )
        pair_two_block = (
            self._wide_section(
                SectionKey.TOP_PRODUCTS,
                charts_by_role[SectionKey.TOP_PRODUCTS.value],
                self._chart_body,
            )
            if SectionKey.TOP_PRODUCTS.value in charts_by_role
            else ""
        )
        detail_block = self._detail_table(report.tables[0]) if report.tables else ""

        generated_at = report.generated_at
        if generated_at is None:
            raise ValueError("sales_report_generated_at_required")
        footer_items = [
            f"数据来源：{self._text(report.data_source)}",
            f"最后刷新：{self._text(generated_at.isoformat())}",
        ]
        html = template.substitute(
            title=self._text(report.title),
            kpi_block=kpi_block,
            trend_block=trend_block,
            pair_one_block=pair_one_block,
            pair_two_block=pair_two_block,
            detail_block=detail_block,
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
        title_id = f"section-{key.value}-title"
        return (
            f'<section class="section-card wide" data-section="{key.value}" '
            f'aria-labelledby="{title_id}">'
            f'<h2 class="section-title" id="{title_id}">{cls._text(chart.title)}</h2>'
            f"{body}"
            "</section>"
        )

    @classmethod
    def _half_section(cls, key: SectionKey, chart: ChartSpec) -> str:
        title_id = f"section-{key.value}-title"
        return (
            f'<section class="section-card half" data-section="{key.value}" '
            f'aria-labelledby="{title_id}">'
            f'<h2 class="section-title" id="{title_id}">{cls._text(chart.title)}</h2>'
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

    @classmethod
    def _detail_table(cls, table: TableSpec) -> str:
        headers = "".join(
            f'<th scope="col">{cls._text(item)}</th>' for item in table.columns
        )
        rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{cls._number(value, decimals=2) if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) else cls._text(value)}</td>"
                for value in row
            )
            + "</tr>"
            for row in table.rows
        )
        return (
            '<section class="section-card wide" data-section="key_details" '
            'aria-labelledby="section-key-details-title">'
            f'<h2 class="section-title" id="section-key-details-title">{cls._text(table.title)}</h2>'
            '<div class="table-wrap"><table><thead><tr>'
            f"{headers}</tr></thead><tbody>{rows}</tbody></table></div></section>"
        )

    # ── Line chart (time series) ──

    @classmethod
    def _line_chart(cls, chart: ChartSpec) -> str:
        points = cls._series(chart)
        width = cls._LINE_WIDTH
        height = cls._LINE_HEIGHT
        pad_left, pad_right = 92, 92
        pad_top, pad_bottom = 44, 96
        plot_w = width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom

        values = [Decimal(str(item["value"])) for item in points]
        lower, upper, y_ticks = cls._nice_axis(values)

        def scale_x(index: int) -> str:
            x = (
                pad_left + plot_w / 2
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
        gridlines = []
        for tick in y_ticks:
            y = scale_y(tick)
            tick_label = cls._axis_number(tick)
            gridlines.append(
                f'<line class="chart-gridline" x1="{pad_left}" y1="{y}" '
                f'x2="{width - pad_right}" y2="{y}" '
                f'aria-label="水平网格线 {tick_label}"/>'
                f'<text class="chart-y-tick" x="{pad_left - 12}" y="{y}" '
                f'dy="4" text-anchor="end">{tick_label}</text>'
            )
        line_points = " ".join(f"{x},{y}" for x, y in coords)
        if len(coords) >= 2:
            area_points = (
                f"{pad_left},{scale_y(lower)} "
                + line_points
                + f" {scale_x(len(points) - 1)},{scale_y(lower)}"
            )
            area = (
                f'<polygon points="{area_points}" fill="{ThemePolicy.SEQUENTIAL_100}" '
                f'stroke="none" aria-hidden="true"/>'
            )
        else:
            area = ""

        circles = []
        for index, (value, (x, y)) in enumerate(zip(values, coords)):
            period_label = cls._period_label(str(points[index]["label"]))
            value_label = cls._number(value, decimals=2)
            circles.append(
                f'<circle cx="{x}" cy="{y}" r="4" tabindex="0" '
                f'fill="{ThemePolicy.SEQUENTIAL_400}" stroke="{ThemePolicy.SURFACE}" '
                f'stroke-width="1.5" '
                f'data-point="{index + 1}" '
                f'data-source-value="{escape(format(value, "f"), quote=True)}" '
                f'aria-label="{cls._text(period_label)}，{cls._text(chart.y_field)}={value_label}">'
                f'<title>{cls._text(period_label)}：{value_label}</title></circle>'
            )

        labels: list[str] = []
        year_boundaries = cls._year_boundary_indexes(points)
        base_indexes = cls._with_required_ticks(
            cls._tick_indexes(len(points), 3), year_boundaries, len(points)
        )
        medium_indexes = cls._with_required_ticks(
            cls._tick_indexes(len(points), 7), year_boundaries, len(points)
        )
        desktop_indexes = (
            tuple(range(len(points)))
            if len(points) <= 15
            else cls._with_required_ticks(
                cls._tick_indexes(len(points), 12), year_boundaries, len(points)
            )
        )
        for tier, indexes in (
            ("base", base_indexes),
            ("medium", medium_indexes),
            ("desktop", desktop_indexes),
        ):
            for index in indexes:
                raw_period = str(points[index]["label"])
                labels.append(cls._axis_period_label(
                    cls._period_label(
                        raw_period,
                        include_year=index in year_boundaries,
                    ),
                    scale_x(index),
                    index=index,
                    last_index=len(points) - 1,
                    tier=tier,
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
                    "start" if index == 0 else "end" if index == len(points) - 1 else "middle"
                )
                dy = "-6" if index == max_index else "14"
                direct_labels += (
                    f'<text x="{x}" y="{y}" dy="{dy}" '
                    f'data-direct-index="{index}" text-anchor="{anchor}" '
                    f'class="chart-direct-label">'
                    f"{cls._number(value, decimals=2)}</text>"
                )

        return (
            f'<div class="chart chart-line" data-chart="time_trend">'
            f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet" aria-label="{cls._text(chart.title)}">'
            f'<text class="chart-y-axis-title" x="24" y="{height / 2:.2f}" '
            f'text-anchor="middle" transform="rotate(-90 24 {height / 2:.2f})">'
            f'销售额（元）</text>'
            f'{"".join(gridlines)}{area}{"".join(circles)}'
            f'<polyline points="{line_points}" fill="none" '
            f'stroke="{ThemePolicy.SEQUENTIAL_550}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            f"{''.join(labels)}{direct_labels}"
            "</svg>"
            "</div>"
        )

    @classmethod
    def _axis_period_label(
        cls,
        period: str,
        x: str,
        *,
        index: int,
        last_index: int,
        tier: str,
    ) -> str:
        # The plot has symmetric endpoint padding, so centered labels remain
        # inside the SVG while preserving even spacing on the desktop tier.
        anchor = "middle"
        upper_lane = (
            tier == "base"
            and index not in {0, last_index}
            and "年" in period
        )
        y = cls._LINE_HEIGHT - (64 if upper_lane else 14)
        lane = "upper" if upper_lane else "baseline"
        return (
            f'<text x="{x}" y="{y}" '
            f'data-tick-index="{index}" data-tick-tier="{tier}" '
            f'data-tick-lane="{lane}" '
            f'text-anchor="{anchor}" class="chart-axis-label" '
            f'aria-label="{cls._text(period)}">{cls._text(period)}</text>'
        )

    @staticmethod
    def _tick_indexes(point_count: int, maximum: int) -> tuple[int, ...]:
        if point_count <= maximum:
            return tuple(range(point_count))
        return tuple(sorted({
            round(slot * (point_count - 1) / (maximum - 1))
            for slot in range(maximum)
        }))

    @classmethod
    def _year_boundary_indexes(cls, points: list[dict[str, Any]]) -> tuple[int, ...]:
        indexes = {0, len(points) - 1}
        previous_year: str | None = None
        for index, item in enumerate(points):
            match = cls._PERIOD_PATTERN.fullmatch(str(item["label"]).strip())
            year = match.group(1) if match else None
            if index == 0 or year != previous_year:
                indexes.add(index)
            previous_year = year
        return tuple(sorted(indexes))

    @staticmethod
    def _with_required_ticks(
        sampled: tuple[int, ...],
        required: tuple[int, ...],
        point_count: int,
    ) -> tuple[int, ...]:
        return tuple(sorted({*sampled, *required, 0, point_count - 1}))

    @staticmethod
    def _axis_number(value: Decimal) -> str:
        decimals = 0 if value == value.to_integral_value() else 2
        return format(value, f",.{decimals}f")

    @staticmethod
    def _nice_axis(values: list[Decimal]) -> tuple[Decimal, Decimal, tuple[Decimal, ...]]:
        minimum = min(values)
        maximum = max(values)
        lower_target = Decimal("0") if minimum >= 0 else minimum
        upper_target = maximum if maximum > 0 else Decimal("0")
        raw_step = (upper_target - lower_target) / Decimal("5")
        if raw_step <= 0:
            raw_step = Decimal("1")
        magnitude = Decimal("10") ** raw_step.adjusted()
        normalized = raw_step / magnitude
        factor = next(
            item
            for item in (Decimal("1"), Decimal("2"), Decimal("5"), Decimal("10"))
            if normalized <= item
        )
        step = factor * magnitude
        lower = (lower_target / step).to_integral_value(rounding=ROUND_FLOOR) * step
        upper = (upper_target / step).to_integral_value(rounding=ROUND_CEILING) * step
        if upper == lower:
            upper = lower + step
        ticks: list[Decimal] = []
        current = lower
        while current <= upper:
            ticks.append(current)
            current += step
        return lower, upper, tuple(ticks)

    @classmethod
    def _period_label(cls, raw: str, *, include_year: bool = True) -> str:
        match = cls._PERIOD_PATTERN.fullmatch(raw.strip())
        if match is None:
            return raw
        month = f"{int(match.group(2))}月"
        return f"{int(match.group(1))}年{month}" if include_year else month

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
                f'stroke-linecap="butt" tabindex="0" '
                f'aria-label="{cls._text(item["label"])}，{format(percent, ".2f")}%">'
                f'<title>{cls._text(item["label"])}：'
                f'{cls._number(item["value"], decimals=2)}，'
                f'{format(percent, ".2f")}%</title></circle>'
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
                f'<div class="column-item{state_class}" data-column="{index + 1}" '
                f'tabindex="0" aria-label="{cls._text(item["label"])}，'
                f'{cls._text(chart.y_field)} {cls._number(value, decimals=2)}">'
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
                f'<div class="bar-row{state_class}" tabindex="0" '
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
        if report.insights or report.filters:
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
        if not report.kpis and not report.charts and not report.tables:
            raise ValueError("sales_report_no_sections")
        cls._validate_kpis(report.kpis)
        cls._validate_charts(report.charts)
        cls._validate_tables(report.tables)

    @classmethod
    def _validate_tables(cls, tables: list[TableSpec]) -> None:
        if len(tables) > 1:
            raise ValueError("sales_report_table_count_invalid")
        for table in tables:
            if table.title != "关键明细" or table.columns != ["客户", "销售额（元）"]:
                raise ValueError("sales_report_table_binding_invalid")
            if not table.rows or len(table.rows) > 50:
                raise ValueError("sales_report_table_rows_invalid")
            for row in table.rows:
                if (
                    len(row) != len(table.columns)
                    or not isinstance(row[0], str)
                    or not row[0]
                ):
                    raise ValueError("sales_report_table_rows_invalid")
                cls._decimal(row[1])

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
