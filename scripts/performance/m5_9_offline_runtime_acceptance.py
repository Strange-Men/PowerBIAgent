"""Deterministic Local MCP queue/pool performance and lifecycle acceptance.

This harness replaces only the external stdio transport with an in-process
latency fixture.  It exercises the production ``PowerBILocalMCPClient``
admission, queue, worker and shutdown code.  Output contains timing/counter
metadata only; no prompt, model identity, PBIX path, connection string or row
data is emitted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.core.performance import (  # noqa: E402
    PerformanceRecorder,
    bind_performance_recorder,
    reset_performance_recorder,
)
from backend.app.powerbi import local_mcp as local_mcp_module  # noqa: E402
from backend.app.powerbi.local_mcp import PowerBILocalMCPClient  # noqa: E402
from backend.app.powerbi.local_mcp import LocalMCPConnectionError  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation-ms", type=float, default=20.0)
    parser.add_argument("--concurrency", default="1,4,20,50,100")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--queue-capacity", type=int)
    parser.add_argument("--admission-timeout-ms", type=float, default=1000.0)
    parser.add_argument("--per-request-limit", type=int, default=2)
    parser.add_argument("--soak-seconds", type=float, default=0.0)
    parser.add_argument("--soak-concurrency", type=int, default=20)
    parser.add_argument("--progress-seconds", type=float, default=300.0)
    return parser.parse_args()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


class _FixtureClient:
    protocol_version = "offline-fixture"
    created = 0
    closed = 0

    def __init__(self, *_: object, **__: object) -> None:
        type(self).created += 1

    async def __aenter__(self) -> "_FixtureClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        type(self).closed += 1

    async def list_tools(self, *, cursor: str | None = None) -> Any:
        return SimpleNamespace(tools=[], next_cursor=None)


async def _run_batch(
    client: PowerBILocalMCPClient,
    *,
    concurrency: int,
    operation_seconds: float,
) -> dict[str, object]:
    ready = asyncio.Event()
    submitted: list[int] = []
    dispatched: list[int] = []
    completed: list[int] = []

    async def one(index: int) -> tuple[float, dict[str, object] | None, str | None]:
        recorder = PerformanceRecorder()
        token = bind_performance_recorder(recorder)
        try:
            await ready.wait()
            started_at = time.perf_counter_ns()
            submitted.append(index)

            async def operation(*_: object) -> int:
                dispatched.append(index)
                await asyncio.sleep(operation_seconds)
                completed.append(index)
                return index

            try:
                result = await client._run_session(operation)
            except LocalMCPConnectionError as exc:
                latency_ms = (time.perf_counter_ns() - started_at) / 1_000_000.0
                return latency_ms, recorder.summary(), exc.error_type
            assert result == index
            latency_ms = (time.perf_counter_ns() - started_at) / 1_000_000.0
            return latency_ms, recorder.summary(), None
        finally:
            reset_performance_recorder(token)

    tasks = [asyncio.create_task(one(index)) for index in range(concurrency)]
    started_at = time.perf_counter_ns()
    ready.set()
    results = await asyncio.gather(*tasks)
    wall_ms = (time.perf_counter_ns() - started_at) / 1_000_000.0
    success_latencies = [item[0] for item in results if item[2] is None]
    rejected_latencies = [item[0] for item in results if item[2] is not None]
    summaries = [
        item[1] for item in results
        if item[1] is not None and item[2] is None
    ]
    errors = [item[2] for item in results if item[2] is not None]
    success_count = concurrency - len(errors)
    successfully_dispatched = [
        item for item in submitted if item in set(dispatched)
    ]
    return {
        "concurrency": concurrency,
        "wall_ms": round(wall_ms, 3),
        "throughput_per_second": round(success_count / (wall_ms / 1000.0), 3),
        "offered_per_second": round(concurrency / (wall_ms / 1000.0), 3),
        "p50_ms": _percentile(success_latencies, 0.50),
        "p95_ms": _percentile(success_latencies, 0.95),
        "p99_ms": _percentile(success_latencies, 0.99),
        "rejection_p95_ms": _percentile(rejected_latencies, 0.95),
        "queue_wait_p95_ms": _percentile(
            [float(summary["queue_wait_ms"]) for summary in summaries], 0.95
        ),
        "max_queue_depth": max(int(summary["queue_depth"]) for summary in summaries),
        "worker_ids": sorted({
            worker_id
            for summary in summaries
            for worker_id in summary["worker_ids"]  # type: ignore[union-attr]
        }),
        "fifo_dispatch": dispatched == successfully_dispatched,
        "completion_reordered": completed != submitted,
        "errors": len(errors),
        "successes": success_count,
        "error_rate": round(len(errors) / concurrency, 4),
        "error_types": sorted(set(errors)),
    }


async def _run_soak(
    client: PowerBILocalMCPClient,
    *,
    duration_seconds: float,
    concurrency: int,
    operation_seconds: float,
    progress_seconds: float,
) -> dict[str, object]:
    started_at = time.perf_counter()
    next_progress = started_at + progress_seconds
    batches = 0
    successes = 0
    errors = 0
    max_queue_depth = 0
    p95_samples: list[float] = []
    while time.perf_counter() - started_at < duration_seconds:
        result = await _run_batch(
            client,
            concurrency=concurrency,
            operation_seconds=operation_seconds,
        )
        batches += 1
        successes += int(result["successes"])
        errors += int(result["errors"])
        max_queue_depth = max(max_queue_depth, int(result["max_queue_depth"]))
        p95_samples.append(float(result["p95_ms"]))
        now = time.perf_counter()
        if now >= next_progress:
            print(json.dumps({
                "soak_progress_seconds": round(now - started_at, 3),
                "soak_batches": batches,
                "soak_successes": successes,
                "soak_errors": errors,
            }), flush=True)
            next_progress = now + progress_seconds
    wall_seconds = time.perf_counter() - started_at
    return {
        "requested_seconds": duration_seconds,
        "wall_seconds": round(wall_seconds, 3),
        "concurrency": concurrency,
        "batches": batches,
        "successes": successes,
        "errors": errors,
        "error_rate": round(errors / max(successes + errors, 1), 6),
        "throughput_per_second": round(successes / max(wall_seconds, 0.001), 3),
        "batch_p95_max_ms": round(max(p95_samples, default=0.0), 3),
        "max_queue_depth": max_queue_depth,
    }


async def _main() -> None:
    args = _arguments()
    if args.operation_ms <= 0:
        raise SystemExit("--operation-ms must be positive")
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")
    if args.admission_timeout_ms <= 0 or args.per_request_limit <= 0:
        raise SystemExit("admission timeout and per-request limit must be positive")
    if (
        args.soak_seconds < 0
        or args.soak_concurrency <= 0
        or args.progress_seconds <= 0
    ):
        raise SystemExit("soak duration/bounds are invalid")
    concurrency_levels = [int(item) for item in args.concurrency.split(",")]
    if not concurrency_levels or any(item <= 0 for item in concurrency_levels):
        raise SystemExit("--concurrency must contain positive integers")

    original_which = local_mcp_module.shutil.which
    original_stdio = local_mcp_module.stdio_client
    original_client = local_mcp_module.Client
    local_mcp_module.shutil.which = lambda _: "offline-fixture"  # type: ignore[assignment]
    local_mcp_module.stdio_client = lambda *_args, **_kwargs: object()  # type: ignore[assignment]
    local_mcp_module.Client = _FixtureClient  # type: ignore[assignment]
    queue_capacity = args.queue_capacity or max(concurrency_levels)
    if queue_capacity < args.workers:
        raise SystemExit("queue capacity cannot be smaller than worker count")
    client = PowerBILocalMCPClient(
        timeout_seconds=10,
        max_pending_operations=queue_capacity,
        worker_count=args.workers,
        admission_timeout_seconds=args.admission_timeout_ms / 1000.0,
        max_operations_per_request=args.per_request_limit,
    )
    try:
        batches = [
            await _run_batch(
                client,
                concurrency=level,
                operation_seconds=args.operation_ms / 1000.0,
            )
            for level in concurrency_levels
        ]
        soak = (
            await _run_soak(
                client,
                duration_seconds=args.soak_seconds,
                concurrency=args.soak_concurrency,
                operation_seconds=args.operation_ms / 1000.0,
                progress_seconds=args.progress_seconds,
            )
            if args.soak_seconds > 0
            else None
        )
    finally:
        await client.aclose()
        local_mcp_module.shutil.which = original_which
        local_mcp_module.stdio_client = original_stdio
        local_mcp_module.Client = original_client

    print(json.dumps({
        "mode": "offline_deterministic_external_transport_fixture",
        "operation_ms": args.operation_ms,
        "worker_count": args.workers,
        "queue_capacity": queue_capacity,
        "admission_timeout_ms": args.admission_timeout_ms,
        "batches": batches,
        "soak": soak,
        "sessions_created": _FixtureClient.created,
        "sessions_closed": _FixtureClient.closed,
        "session_residual": _FixtureClient.created - _FixtureClient.closed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
