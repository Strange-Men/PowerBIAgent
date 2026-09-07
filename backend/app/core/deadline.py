"""Request-local monotonic deadline helpers.

The deadline contains timing state only.  ContextVar propagation gives child
tasks the same immutable request budget without carrying conversation, model,
prompt or credential data.
"""

from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar, Token


_REQUEST_DEADLINE: ContextVar[float | None] = ContextVar(
    "powerbiagent_request_deadline",
    default=None,
)


def bind_request_deadline(timeout_seconds: float) -> Token:
    if timeout_seconds <= 0:
        raise ValueError("request deadline must be positive")
    return _REQUEST_DEADLINE.set(time.monotonic() + timeout_seconds)


def reset_request_deadline(token: Token) -> None:
    _REQUEST_DEADLINE.reset(token)


def current_request_deadline() -> float | None:
    return _REQUEST_DEADLINE.get()


def bind_request_deadline_value(deadline: float | None) -> Token:
    return _REQUEST_DEADLINE.set(deadline)


def remaining_request_seconds() -> float | None:
    deadline = current_request_deadline()
    if deadline is None:
        return None
    return max(deadline - time.monotonic(), 0.0)


def bounded_timeout_seconds(configured_seconds: float) -> float:
    if configured_seconds <= 0:
        raise ValueError("configured timeout must be positive")
    remaining = remaining_request_seconds()
    if remaining is None:
        return configured_seconds
    return min(configured_seconds, max(remaining, 0.000_001))


async def sleep_with_request_deadline(delay_seconds: float) -> None:
    """Sleep for retry backoff without extending the request budget."""
    if delay_seconds < 0:
        raise ValueError("retry delay cannot be negative")
    remaining = remaining_request_seconds()
    if remaining is None:
        await asyncio.sleep(delay_seconds)
        return
    if remaining <= 0:
        raise TimeoutError("request_deadline_exceeded")
    async with asyncio.timeout(remaining):
        await asyncio.sleep(delay_seconds)
