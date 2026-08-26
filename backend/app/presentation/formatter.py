"""Deterministic display formatting that never mutates factual values."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum


class PresentationFormatKind(str, Enum):
    AUTO = "auto"
    INTEGER = "integer"
    DECIMAL = "decimal"
    PERCENTAGE = "percentage"
    AMOUNT = "amount"
    DATE = "date"
    MONTH = "month"
    TEXT = "text"


class PresentationFormatter:
    """Render locale-aware display strings while preserving source values."""

    _TWO_PLACES = Decimal("0.01")

    def __init__(self, *, locale: str = "zh-CN") -> None:
        self.locale = locale.strip() or "zh-CN"

    def format(
        self,
        value: object,
        kind: PresentationFormatKind = PresentationFormatKind.AUTO,
    ) -> str:
        if value is None:
            return "—"
        effective = self._infer_kind(value) if kind == PresentationFormatKind.AUTO else kind
        if effective == PresentationFormatKind.INTEGER:
            number = self._decimal(value)
            return f"{int(number.to_integral_value(rounding=ROUND_HALF_UP)):,}"
        if effective in {PresentationFormatKind.DECIMAL, PresentationFormatKind.AMOUNT}:
            number = self._decimal(value).quantize(
                self._TWO_PLACES, rounding=ROUND_HALF_UP
            )
            return f"{number:,.2f}"
        if effective == PresentationFormatKind.PERCENTAGE:
            percent = (self._decimal(value) * 100).quantize(
                self._TWO_PLACES, rounding=ROUND_HALF_UP
            )
            rendered = f"{percent:,.2f}".rstrip("0").rstrip(".")
            return f"{rendered}%"
        if effective in {PresentationFormatKind.DATE, PresentationFormatKind.MONTH}:
            parsed = self._date(value)
            if effective == PresentationFormatKind.MONTH:
                if self.locale.casefold().startswith("zh"):
                    return f"{parsed.year}年{parsed.month}月"
                return f"{parsed.year:04d}-{parsed.month:02d}"
            if self.locale.casefold().startswith("zh"):
                return f"{parsed.year}年{parsed.month}月{parsed.day}日"
            return parsed.isoformat()
        if isinstance(value, bool):
            return "是" if self.locale.casefold().startswith("zh") and value else (
                "否" if self.locale.casefold().startswith("zh") else str(value)
            )
        return str(value)

    @staticmethod
    def kind_for_data_type(data_type: str) -> PresentationFormatKind:
        return PresentationFormatter.kind_for_metadata(data_type, None)

    @staticmethod
    def kind_for_metadata(
        data_type: str,
        format_string: str | None,
    ) -> PresentationFormatKind:
        normalized = data_type.strip().casefold()
        normalized_format = (format_string or "").strip().casefold()
        if "%" in normalized_format:
            return PresentationFormatKind.PERCENTAGE
        if any(
            token in normalized_format
            for token in ("$", "¥", "￥", "€", "£", "currency")
        ):
            return PresentationFormatKind.AMOUNT
        if any(token in normalized for token in ("date", "time")):
            return PresentationFormatKind.DATE
        if any(token in normalized for token in ("int", "whole")):
            return PresentationFormatKind.INTEGER
        if any(
            token in normalized
            for token in ("decimal", "double", "float", "number", "currency")
        ):
            return PresentationFormatKind.AMOUNT
        return PresentationFormatKind.TEXT

    @staticmethod
    def _infer_kind(value: object) -> PresentationFormatKind:
        if isinstance(value, bool):
            return PresentationFormatKind.TEXT
        if isinstance(value, int):
            return PresentationFormatKind.INTEGER
        if isinstance(value, (float, Decimal)):
            return PresentationFormatKind.DECIMAL
        if isinstance(value, (date, datetime)):
            return PresentationFormatKind.DATE
        return PresentationFormatKind.TEXT

    @staticmethod
    def _decimal(value: object) -> Decimal:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("presentation_number_invalid") from exc
        if not number.is_finite():
            raise ValueError("presentation_number_invalid")
        return number

    @staticmethod
    def _date(value: object) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise ValueError("presentation_date_invalid")
        normalized = value.strip()
        try:
            return date.fromisoformat(normalized[:10])
        except ValueError as exc:
            raise ValueError("presentation_date_invalid") from exc
