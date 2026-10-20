"""Finite typed numeric representation; grants no fact or provenance authority."""
from decimal import Decimal
from math import isfinite


def is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, float):
        return isfinite(value)
    return isinstance(value, int)
