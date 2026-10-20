"""Bundled presentation resources; exact keys, no cross-language fallback."""
import json
from functools import lru_cache
from pathlib import Path

from backend.app.presentation.locale import current_locale, normalize_locale


@lru_cache(maxsize=2)
def catalog(locale):
    return json.loads((Path(__file__).with_name('locales') / f'{locale}.json').read_text(encoding='utf-8'))


def message(key: str, *, locale=None, **parameters) -> str:
    selected = normalize_locale(locale if locale is not None else current_locale()).value
    return catalog(selected)[key].format(**parameters)


def display_resource(value: str) -> str:
    """Resolve exact registered display text, never rewrite canonical objects.

    Used at the renderer edge for existing immutable ReportSpec display fields.
    Business names absent from the display catalog retain their source identity.
    """
    # Historical fixed ReportSpec label: its currency was never authoritative.
    if value == "销售额（元）":
        return message("report.sales_amount")
    for key, text in catalog('zh-CN').items():
        if '{' not in text and text == value:
            return message(key)
    for key, text in catalog('en-US').items():
        if '{' not in text and text == value:
            return message(key)
    return value
