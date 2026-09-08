"""Code-owned parsing for explicit, object-free temporal expressions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


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


def parse_explicit_month_range(text: str) -> ExplicitMonthRange | None:
    """Parse a fully explicit month range without choosing a model date field."""
    normalized = unicodedata.normalize("NFKC", text)
    match = _CHINESE_MONTH_RANGE.search(normalized)
    if match is None:
        match = _NUMERIC_MONTH_RANGE.search(normalized)
    if match is None:
        return None
    start_year = int(match.group("start_year"))
    end_year_text = match.group("end_year")
    return ExplicitMonthRange(
        start_year=start_year,
        start_month=int(match.group("start_month")),
        end_year=int(end_year_text) if end_year_text else start_year,
        end_month=int(match.group("end_month")),
    )
