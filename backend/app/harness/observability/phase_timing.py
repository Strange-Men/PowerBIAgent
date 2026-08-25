"""Request-local monotonic phase timings with no prompt or payload capture."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from functools import wraps
from time import perf_counter
from typing import Any, Callable, Iterator


PHASE_NAMES = (
    "intent_llm",
    "capability_classification",
    "schema",
    "member_lookup",
    "grounding",
    "mcp_enumerate/connect",
    "dax",
    "verified_fact",
    "answer_llm",
    "report_plan",
    "report_query",
    "report_render",
    "persistence",
    "total",
)


class PhaseTimingCollector:
    def __init__(self) -> None:
        self._started_at = perf_counter()
        self._durations = {name: 0.0 for name in PHASE_NAMES}

    def begin(self) -> float:
        return perf_counter()

    def end(self, phase: str, started_at: float) -> None:
        if phase not in self._durations:
            raise ValueError(f"phase_timing_unknown:{phase}")
        self._durations[phase] += (perf_counter() - started_at) * 1000

    @contextmanager
    def measure(self, phase: str) -> Iterator[None]:
        started_at = self.begin()
        try:
            yield
        finally:
            self.end(phase, started_at)

    def finish(self) -> dict[str, float]:
        self._durations["total"] = (perf_counter() - self._started_at) * 1000
        return {
            name: round(self._durations[name], 3)
            for name in PHASE_NAMES
        }


_CURRENT: ContextVar[PhaseTimingCollector | None] = ContextVar(
    "powerbiagent_phase_timing", default=None
)


def bind_phase_timings(collector: PhaseTimingCollector) -> Token:
    return _CURRENT.set(collector)


def reset_phase_timings(token: Token) -> None:
    _CURRENT.reset(token)


def timed_phase(phase: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Measure an async provider boundary when a TurnPipeline context exists."""

    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(function)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            collector = _CURRENT.get()
            if collector is None:
                return await function(*args, **kwargs)
            with collector.measure(phase):
                return await function(*args, **kwargs)

        return wrapper

    return decorator
