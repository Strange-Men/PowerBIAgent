"""Production fixed renderer for the sole M3 sales_report template."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from pathlib import Path
from string import Template
from typing import Any

from backend.app.report.base import ReportRenderer
from backend.app.schemas.data_contracts import ReportSpec


class FixedSalesReportRenderer(ReportRenderer):
    """Render a validated fixed ReportSpec as self-contained static HTML."""

    _TEMPLATE_PATH = Path(__file__).with_name("templates") / "sales_report.html"
    _SUPPORTED_TEMPLATES = ("sales_report",)

    @property
    def supported_templates(self) -> list[str]:
        return list(self._SUPPORTED_TEMPLATES)

    async def render(self, report: ReportSpec) -> str:
        self._validate_spec(report)
        template = Template(self._TEMPLATE_PATH.read_text(encoding="utf-8"))
        category_rows = "\n".join(
            self._table_row(
                self._text(row[0]),
                self._number(row[1], decimals=2),
                numeric_columns={1},
            )
            for row in report.tables[0].rows
        )
        product_rows = "\n".join(
            self._table_row(
                self._text(row[0]),
                self._text(row[1]),
                self._number(row[2], decimals=2),
                numeric_columns={0, 2},
            )
            for row in report.tables[1].rows
        )
        category_bars = self._bar_rows(
            report.tables[0].rows,
            label_index=0,
            value_index=1,
        )
        product_bars = self._bar_rows(
            report.tables[1].rows,
            label_index=1,
            value_index=2,
            position_index=0,
        )
        generated_at = report.generated_at
        if generated_at is None:
            raise ValueError("sales_report_generated_at_required")
        html = template.substitute(
            title=self._text(report.title),
            total_sales=self._number(report.kpis[0].value, decimals=2),
            total_quantity=self._number(report.kpis[1].value, decimals=0),
            category_bars=category_bars,
            category_rows=category_rows,
            product_bars=product_bars,
            product_rows=product_rows,
            data_source=self._text(report.data_source),
            source_mode=self._text(report.source_mode),
            contract_version=self._text(report.contract_version),
            generated_at=self._text(generated_at.isoformat()),
        )
        self._validate_rendered_html(html)
        return html

    @staticmethod
    def _validate_spec(report: ReportSpec) -> None:
        if report.template_key != "sales_report":
            raise ValueError("sales_report_renderer_template_rejected")
        if report.title != "销售分析报表":
            raise ValueError("sales_report_title_invalid")
        if report.charts or report.insights or report.filters:
            raise ValueError("sales_report_structure_invalid")
        if [(item.name, item.field, item.format) for item in report.kpis] != [
            ("总销售额", "Total Sales", "currency"),
            ("总销量", "Total Quantity", "number"),
        ]:
            raise ValueError("sales_report_kpi_contract_invalid")
        if len(report.tables) != 2:
            raise ValueError("sales_report_table_contract_invalid")
        if (
            report.tables[0].title != "按类别销售额"
            or report.tables[0].columns != ["Category", "Total Sales"]
            or report.tables[1].title != "Top 5 产品销售额"
            or report.tables[1].columns != ["序号", "Product", "Total Sales"]
        ):
            raise ValueError("sales_report_table_contract_invalid")
        if any(len(row) != 2 for row in report.tables[0].rows):
            raise ValueError("sales_report_category_row_invalid")
        if any(len(row) != 3 for row in report.tables[1].rows):
            raise ValueError("sales_report_product_row_invalid")
        positions = [row[0] for row in report.tables[1].rows]
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError("sales_report_result_position_invalid")
        if (
            not report.contract_version
            or not report.semantic_model_key
            or len(report.schema_fingerprint) != 64
            or len(report.query_result_ids) != 4
            or len(set(report.query_result_ids)) != 4
            or len(report.verified_fact_set_ids) != 4
            or len(set(report.verified_fact_set_ids)) != 4
            or report.source_mode not in {"mock", "real"}
            or report.data_source != report.semantic_model_key
            or report.generated_at is None
        ):
            raise ValueError("sales_report_provenance_invalid")

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
    def _bar_rows(
        cls,
        rows: list[list[Any]],
        *,
        label_index: int,
        value_index: int,
        position_index: int | None = None,
    ) -> str:
        """Project verified table values into deterministic visual geometry."""

        values = [cls._decimal(row[value_index]) for row in rows]
        maximum = max((abs(value) for value in values), default=Decimal("0"))
        rendered: list[str] = []
        for row, value in zip(rows, values):
            percent = (
                Decimal("0")
                if maximum == 0
                else (abs(value) * Decimal("100") / maximum).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            )
            percent_text = format(percent, ".2f")
            source_value = escape(format(value, "f"), quote=True)
            display_value = cls._number(value, decimals=2)
            label = cls._text(row[label_index])
            state_class = (
                " negative" if value < 0 else " zero" if value == 0 else ""
            )
            position = ""
            if position_index is not None:
                position_value = cls._text(row[position_index])
                position = (
                    '<span class="result-position">'
                    f"结果序号 {position_value}</span>"
                )
            rendered.append(
                f'<div class="bar-row{state_class}" '
                f'data-source-value="{source_value}" '
                f'data-bar-percent="{percent_text}" '
                f'aria-label="{label}，销售额 {display_value}">'
                f'<div class="bar-label">{position}'
                f'<span class="bar-name">{label}</span></div>'
                '<div class="bar-track" aria-hidden="true">'
                f'<span class="bar-fill" style="width: {percent_text}%"></span>'
                '</div>'
                f'<div class="bar-value">{display_value}</div>'
                '</div>'
            )
        return "\n".join(rendered)

    @staticmethod
    def _table_row(*cells: str, numeric_columns: set[int]) -> str:
        rendered = []
        for index, value in enumerate(cells):
            class_name = ' class="number"' if index in numeric_columns else ""
            rendered.append(f"<td{class_name}>{value}</td>")
        return "<tr>" + "".join(rendered) + "</tr>"

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
