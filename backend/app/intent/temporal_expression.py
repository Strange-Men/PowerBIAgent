"""Code-owned parsing for explicit, object-free temporal expressions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ExplicitMonthRange:
    start_year: int
    start_month: int
    end_year: int
    end_month: int


_CHINESE_MONTH_RANGE = re.compile(
    r"(?<!\d)(?P<start_year>\d{4})\s*年\s*"
    r"(?P<start_month>0?[1-9]|1[0-2])\s*月(?:份)?\s*"
    r"(?:至|到|[-—–~～])\s*"
    r"(?:(?P<end_year>\d{4})\s*年\s*)?"
    r"(?P<end_month>0?[1-9]|1[0-2])\s*月(?:份)?"
)
_NUMERIC_MONTH_RANGE = re.compile(
    r"(?<!\d)(?P<start_year>\d{4})\s*[-/]\s*"
    r"(?P<start_month>0?[1-9]|1[0-2])\s*"
    r"(?:至|到|~|～|\bto\b)\s*"
    r"(?P<end_year>\d{4})\s*[-/]\s*"
    r"(?P<end_month>0?[1-9]|1[0-2])(?!\d)"
)
_RELATIVE_YEAR_MONTH_RANGE = re.compile(
    r"(?P<relative>今年|去年)\s*"
    r"(?P<start_month>0?[1-9]|1[0-2])\s*月(?:份)?\s*"
    r"(?:至|到|[-—–~～])\s*"
    r"(?P<end_month>0?[1-9]|1[0-2])\s*月(?:份)?"
)
_YEARLESS_MONTH_RANGE = re.compile(
    r"(?<![\d年])(?P<start_month>0?[1-9]|1[0-2])\s*月(?:份)?\s*"
    r"(?:至|到|[-—–~～])\s*"
    r"(?P<end_month>0?[1-9]|1[0-2])\s*月(?:份)?"
)


def parse_explicit_month_range(
    text: str, *, reference_year: int | None = None
) -> ExplicitMonthRange | None:
    """Parse a fully explicit month range without choosing a model date field."""
    normalized = unicodedata.normalize("NFKC", text)
    match = _CHINESE_MONTH_RANGE.search(normalized)
    if match is None:
        match = _NUMERIC_MONTH_RANGE.search(normalized)
    if match is not None:
        start_year = int(match.group("start_year"))
        end_year_text = match.group("end_year")
        return ExplicitMonthRange(
            start_year=start_year,
            start_month=int(match.group("start_month")),
            end_year=int(end_year_text) if end_year_text else start_year,
            end_month=int(match.group("end_month")),
        )
    relative = _RELATIVE_YEAR_MONTH_RANGE.search(normalized)
    if relative is None:
        return None
    base_year = reference_year if reference_year is not None else date.today().year
    resolved_year = base_year - (1 if relative.group("relative") == "去年" else 0)
    return ExplicitMonthRange(
        start_year=resolved_year,
        start_month=int(relative.group("start_month")),
        end_year=resolved_year,
        end_month=int(relative.group("end_month")),
    )


def has_explicit_month_range(text: str) -> bool:
    """Detect both resolvable and yearless month-range obligations."""
    normalized = unicodedata.normalize("NFKC", text)
    return bool(
        _CHINESE_MONTH_RANGE.search(normalized)
        or _NUMERIC_MONTH_RANGE.search(normalized)
        or _RELATIVE_YEAR_MONTH_RANGE.search(normalized)
        or _YEARLESS_MONTH_RANGE.search(normalized)
    )
