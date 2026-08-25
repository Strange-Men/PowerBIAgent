"""M5.5 deterministic display formatter coverage."""

from datetime import date

from backend.app.localization.models import LocalizationSource, ResolvedLocalization
from backend.app.presentation.formatter import PresentationValueFormatter


def _field(
    canonical_name: str,
    *,
    data_type: str = "decimal",
    format_string: str | None = None,
) -> ResolvedLocalization:
    return ResolvedLocalization(
        semantic_model_key="model",
        object_identity=f"measure:T:{canonical_name}",
        object_type="measure",
        canonical_name=canonical_name,
        display_name=canonical_name,
        source=LocalizationSource.CANONICAL_FALLBACK,
        schema_identity="a" * 64,
        table_name="T",
        data_type=data_type,
        format_string=format_string,
    )


def test_integer_decimal_percentage_date_month_and_null() -> None:
    formatter = PresentationValueFormatter()
    assert formatter.format(3065, _field("Quantity", data_type="int64")) == "3,065"
    assert formatter.format(6943997.509999986, _field("Revenue")) == "6,943,997.51"
    assert formatter.format(0.8562, _field("AttendanceRate")) == "85.62%"
    assert formatter.format(0.1, _field("Margin", format_string="0.0%")) == "10%"
    assert formatter.format(date(2026, 3, 1)) == "2026-03-01"
    assert formatter.format("2026-03") == "2026年3月"
    assert formatter.format(None) == "—"


def test_float_artifact_rounding_does_not_mutate_input() -> None:
    value = 0.1 + 0.2
    formatter = PresentationValueFormatter()
    assert value != 0.3
    assert formatter.format(value, _field("Value")) == "0.3"
    assert value == 0.30000000000000004
