"""Deterministic display formatting; raw fact values remain unchanged."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from backend.app.localization.models import ResolvedLocalization


class PresentationValueFormatter:
    NULL_TEXT = "—"

    def format(
        self,
        value: Any,
        field: ResolvedLocalization | None = None,
    ) -> str:
        if value is None:
            return self.NULL_TEXT
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            month = re.fullmatch(r"(\d{4})[-/](\d{1,2})", value.strip())
            if month:
                return f"{month.group(1)}年{int(month.group(2))}月"
            return value
        if isinstance(value, (int, float, Decimal)):
            if isinstance(value, float) and not math.isfinite(value):
                return self.NULL_TEXT
            number = self._decimal(value)
            if number is None:
                return str(value)
            if self._is_percentage(field):
                return f"{self._number(number * Decimal('100'), 2)}%"
            if self._is_integer(field, number):
                return f"{int(number):,}"
            return self._number(number, 2)
        return str(value)

    @staticmethod
    def _decimal(value: int | float | Decimal) -> Decimal | None:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _number(value: Decimal, places: int) -> str:
        quantum = Decimal(1).scaleb(-places)
        rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
        text = f"{rounded:,.{places}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    @staticmethod
    def _is_integer(
        field: ResolvedLocalization | None,
        value: Decimal,
    ) -> bool:
        data_type = (field.data_type if field else "").casefold()
        return "int" in data_type or (
            data_type in {"whole", "whole number"} and value == value.to_integral()
        )

    @staticmethod
    def _is_percentage(field: ResolvedLocalization | None) -> bool:
        if field is None:
            return False
        format_string = (field.format_string or "").casefold()
        name = f"{field.canonical_name} {field.display_name}".casefold()
        return "%" in format_string or any(
            token in name for token in ("percent", "percentage", "rate", "比例", "率")
        )
