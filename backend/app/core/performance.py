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
    queue_depth: int | None = None
    worker_id: int | None = None

    def safe_dict(self) -> dict[str, str | float | int]:
        result: dict[str, str | float | int] = {
            "operation": self.operation,
            "duration_ms": round(self.duration_ms, 3),
            "cache": self.cache,
            "session": self.session,
        }
        if self.queue_depth is not None:
            result["queue_depth"] = self.queue_depth
        if self.worker_id is not None:
            result["worker_id"] = self.worker_id
        return result


class PerformanceRecorder:
    """Collect only duration/category/cache/session metadata for one request."""

    def __init__(self) -> None:
        self._started_at_ns = time.perf_counter_ns()
        self._observations: list[PerformanceObservation] = []
        self._retry_count = 0
        self._timeout_count = 0

    @contextmanager
    def measure(
        self,
        operation: str,
        *,
        cache: CacheStatus = "none",
        session: SessionStatus = "none",
    ) -> Iterator[None]:
        started_at_ns = time.perf_counter_ns()
        try:
            yield
        finally:
            self.record(
                operation,
                (time.perf_counter_ns() - started_at_ns) / 1_000_000.0,
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
        queue_depth: int | None = None,
        worker_id: int | None = None,
    ) -> None:
        self._observations.append(PerformanceObservation(
            operation=operation,
            duration_ms=max(duration_ms, 0.0),
            cache=cache,
            session=session,
            queue_depth=(max(queue_depth, 0) if queue_depth is not None else None),
            worker_id=(max(worker_id, 0) if worker_id is not None else None),
        ))

    def record_retry(self) -> None:
        self._retry_count += 1

    def record_timeout(self) -> None:
        self._timeout_count += 1

    def summary(self) -> dict[str, object]:
        observations = [item.safe_dict() for item in self._observations]
        cache_observations = [item for item in self._observations if item.cache != "none"]
        session_observations = [
            item for item in self._observations if item.session != "none"
        ]
        operation_aliases = {
            "router_ms": {"router"},
            "intent_llm_ms": {"intent_llm"},
            "schema_ms": {"schema_read"},
            "grounding_ms": {"grounding", "semantic_catalog_build"},
            "member_lookup_ms": {"member_lookup"},
            "query_plan_ms": {"query_plan"},
            "dax_build_ms": {"dax_build"},
            "queue_wait_ms": {"queue_wait"},
            "mcp_rpc_ms": {"mcp_rpc"},
            "powerbi_execute_ms": {"dax_execution"},
            "result_inspection_ms": {"result_inspection"},
            "answer_ms": {"answer_presentation"},
            "report_ms": {"report"},
            "db_ms": {"persistence"},
            "llm_task_ms": {"llm_task"},
        }
        totals = {
            field: round(sum(
                item.duration_ms
                for item in self._observations
                if item.operation in operations
            ), 3)
            for field, operations in operation_aliases.items()
        }
        total_ms = round(
            (time.perf_counter_ns() - self._started_at_ns) / 1_000_000.0,
            3,
        )
        queue_depth = max(
            (item.queue_depth or 0 for item in self._observations),
            default=0,
        )
        worker_ids = sorted({
            item.worker_id
            for item in self._observations
            if item.worker_id is not None
        })
        return {
            "total_ms": total_ms,
            "total_turn_ms": total_ms,
            **totals,
            "retry_count": self._retry_count,
            "timeout_count": self._timeout_count,
            "cache_hit": sum(item.cache == "hit" for item in cache_observations),
            "cache_miss": sum(item.cache == "miss" for item in cache_observations),
            "session_new": sum(item.session == "new" for item in session_observations),
            "session_reused": sum(
                item.session == "reused" for item in session_observations
            ),
            "queue_depth": queue_depth,
            "worker_ids": worker_ids,
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


def record_performance_retry() -> None:
    recorder = current_performance_recorder()
    if recorder is not None:
        recorder.record_retry()


def record_performance_timeout() -> None:
    recorder = current_performance_recorder()
    if recorder is not None:
        recorder.record_timeout()


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
