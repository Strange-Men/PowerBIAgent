"""Request-local, monotonic and data-safe performance observations."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator, Literal


CacheStatus = Literal["hit", "miss", "none"]
SessionStatus = Literal["reused", "new", "none"]


@dataclass(frozen=True)
class PerformanceObservation:
    operation: str
    duration_ms: float
    cache: CacheStatus = "none"
    session: SessionStatus = "none"

    def safe_dict(self) -> dict[str, str | float]:
        return {
            "operation": self.operation,
            "duration_ms": round(self.duration_ms, 3),
            "cache": self.cache,
            "session": self.session,
        }


class PerformanceRecorder:
    """Collect only duration/category/cache/session metadata for one request."""

    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._observations: list[PerformanceObservation] = []

    @contextmanager
    def measure(
        self,
        operation: str,
        *,
        cache: CacheStatus = "none",
        session: SessionStatus = "none",
    ) -> Iterator[None]:
        started_at = time.monotonic()
        try:
            yield
        finally:
            self.record(
                operation,
                (time.monotonic() - started_at) * 1000.0,
                cache=cache,
                session=session,
            )

    def record(
        self,
        operation: str,
        duration_ms: float,
        *,
        cache: CacheStatus = "none",
        session: SessionStatus = "none",
    ) -> None:
        self._observations.append(PerformanceObservation(
            operation=operation,
            duration_ms=max(duration_ms, 0.0),
            cache=cache,
            session=session,
        ))

    def summary(self) -> dict[str, object]:
        observations = [item.safe_dict() for item in self._observations]
        cache_observations = [item for item in self._observations if item.cache != "none"]
        session_observations = [
            item for item in self._observations if item.session != "none"
        ]
        return {
            "total_turn_ms": round(
                (time.monotonic() - self._started_at) * 1000.0,
                3,
            ),
            "operations": observations,
            "cache_hit_rate": round(
                sum(item.cache == "hit" for item in cache_observations)
                / len(cache_observations),
                4,
            ) if cache_observations else 0.0,
            "session_reuse_rate": round(
                sum(item.session == "reused" for item in session_observations)
                / len(session_observations),
                4,
            ) if session_observations else 0.0,
        }


_CURRENT_RECORDER: ContextVar[PerformanceRecorder | None] = ContextVar(
    "powerbiagent_performance_recorder",
    default=None,
)


def current_performance_recorder() -> PerformanceRecorder | None:
    return _CURRENT_RECORDER.get()


def bind_performance_recorder(recorder: PerformanceRecorder) -> Token:
    return _CURRENT_RECORDER.set(recorder)


def reset_performance_recorder(token: Token) -> None:
    _CURRENT_RECORDER.reset(token)


@contextmanager
def measure_performance(
    operation: str,
    *,
    cache: CacheStatus = "none",
    session: SessionStatus = "none",
) -> Iterator[None]:
    recorder = current_performance_recorder()
    if recorder is None:
        yield
        return
    with recorder.measure(operation, cache=cache, session=session):
        yield
