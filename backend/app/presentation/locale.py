"""Presentation context only. Never a semantic, execution or ownership input."""
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum


class SupportedLocale(str, Enum):
    ZH_CN = 'zh-CN'
    EN_US = 'en-US'


def normalize_locale(value: object) -> SupportedLocale:
    return SupportedLocale.EN_US if value == 'en-US' else SupportedLocale.ZH_CN


_locale = ContextVar('presentation_locale', default=SupportedLocale.ZH_CN)


def current_locale() -> SupportedLocale:
    return _locale.get()


@contextmanager
def presentation_locale(value: object):
    token = _locale.set(normalize_locale(value))
    try:
        yield _locale.get()
    finally:
        _locale.reset(token)
