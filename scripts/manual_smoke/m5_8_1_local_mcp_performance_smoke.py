"""Safe cold/warm Local MCP metadata/session performance smoke.

The script prints durations and cache/session counters only.  It never prints
opaque model keys, connection properties, schema contents, member values, DAX,
prompts, or business rows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.core.performance import (
    PerformanceRecorder,
    bind_performance_recorder,
    reset_performance_recorder,
)
from backend.app.powerbi.local_mcp import LocalMCPPowerBIAdapter
from backend.app.schemas.data_contracts import ColumnMembersRequest, DAXRequest


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-display-name")
    parser.add_argument("--member-table")
    parser.add_argument("--member-field")
    parser.add_argument("--full-turn", action="store_true")
    parser.add_argument("--profile", default="deepseek")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--queue-capacity", type=int, default=32)
    parser.add_argument("--dax-concurrency", default="1,4")
    return parser.parse_args()


async def _timed(operation):
    started_at = time.perf_counter_ns()
    value = await operation
    return value, round((time.perf_counter_ns() - started_at) / 1_000_000.0, 3)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _select_model(
    items: list[dict[str, Any]],
    display_name: str | None,
    *,
    require_selectable: bool = True,
) -> str:
    selectable = [
        item
        for item in items
        if (
            item.get("selectable") is True
            if require_selectable
            else (
                item.get("available") is not False
                and item.get("connected") is not False
            )
        )
    ]
    if display_name is None:
        matches = selectable
    else:
        matches = [
            item for item in selectable
            if item.get("display_name") == display_name
        ]
    if len(matches) != 1:
        raise RuntimeError(
            "Desktop model selection did not resolve uniquely "
            f"(catalog_count={len(items)}, selectable_count={len(selectable)}, "
            f"match_count={len(matches)})"
        )
    return str(matches[0]["key"])


def _safe_turn_metrics(body: dict[str, Any]) -> dict[str, Any]:
    performance = (body.get("execution_audit") or {}).get("performance") or {}
    operations: dict[str, float] = {}
    for observation in performance.get("operations") or []:
        operation = observation.get("operation")
        duration = observation.get("duration_ms")
        if isinstance(operation, str) and isinstance(duration, (int, float)):
            operations[operation] = round(operations.get(operation, 0.0) + duration, 3)
    return {
        "total_turn_ms": performance.get("total_turn_ms"),
        "operations_ms": operations,
        "cache_hit_rate": performance.get("cache_hit_rate"),
        "session_reuse_rate": performance.get("session_reuse_rate"),
        "terminal_state": body.get("terminal_state"),
        "error_type": body.get("error_type"),
    }


async def _full_turn_profile(args: argparse.Namespace) -> dict[str, Any]:
    from httpx import ASGITransport, AsyncClient

    from backend.app.config.settings import (
        LLMMode,
        PersistenceBackend,
        PowerBIMode,
        Settings,
    )
    from backend.app.main import create_app

    temporary = tempfile.TemporaryDirectory(prefix="powerbiagent-m581-perf-")
    temp_root = Path(temporary.name)
    summary: dict[str, Any] = {}
    try:
        settings = Settings(
            llm_mode=LLMMode.OPENAI_COMPATIBLE,
            llm_default_profile=args.profile,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            persistence_backend=PersistenceBackend.MEMORY,
            report_artifacts_path=str(temp_root / "reports"),
            presentation_localization_registry_path=str(
                temp_root / "runtime" / "display_localizations.json"
            ),
            powerbi_local_mcp_workers=args.workers,
            powerbi_local_mcp_queue_capacity=args.queue_capacity,
        )
        app = create_app(settings=settings)
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app, raise_app_exceptions=True)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                bootstrap_at = time.monotonic()
                discovery = await client.get("/api/v1/semantic-models")
                bootstrap_ms = round((time.monotonic() - bootstrap_at) * 1000.0, 3)
                if discovery.status_code != 200:
                    raise RuntimeError("Desktop discovery failed")
                model_key = _select_model(
                    discovery.json().get("items", []),
                    args.model_display_name,
                )

                async def post(label: str, message: str) -> dict[str, Any]:
                    response = await client.post(
                        "/api/v1/chat",
                        json={
                            "message": message,
                            "conversation_id": f"m581-perf-{label}-{uuid.uuid4().hex}",
                            "request_id": f"m581-perf-{label}-{uuid.uuid4().hex}",
                            "semantic_model_key": model_key,
                            "llm_profile_key": args.profile,
                        },
                    )
                    metrics = _safe_turn_metrics(response.json())
                    metrics["http_status"] = response.status_code
                    if response.status_code != 200 or metrics["terminal_state"] != "completed":
                        raise RuntimeError(f"full-turn performance case failed: {label}")
                    return metrics

                cold_started_at = time.monotonic()
                first = await post("cold-scalar", "总销售额是多少？")
                cold_journey_ms = round(
                    bootstrap_ms + (time.monotonic() - cold_started_at) * 1000.0,
                    3,
                )
                second = await post("warm-second", "2025年5月销售额")
                member = await post("member", "华南区销售额")
                trend = await post("trend", "每个月销售额趋势")

                sequence = (
                    "总销售额是多少？",
                    "2025年5月销售额",
                    "华南区销售额",
                    "每个月销售额趋势",
                )
                sequential_started_at = time.monotonic()
                sequential = [
                    await post(f"sequential-{index}", sequence[index % len(sequence)])
                    for index in range(10)
                ]
                sequential_ms = round(
                    (time.monotonic() - sequential_started_at) * 1000.0,
                    3,
                )

                concurrent_started_at = time.monotonic()
                concurrent = await asyncio.gather(*(
                    post(f"concurrent-{index}", sequence[index % len(sequence)])
                    for index in range(4)
                ))
                concurrent_ms = round(
                    (time.monotonic() - concurrent_started_at) * 1000.0,
                    3,
                )
                summary = {
                    "bootstrap_discovery_ms": bootstrap_ms,
                    "cold_journey_ms": cold_journey_ms,
                    "first_scalar": first,
                    "immediate_second": second,
                    "member_lookup": member,
                    "trend": trend,
                    "sequential_10": {
                        "wall_ms": sequential_ms,
                        "turns": sequential,
                    },
                    "concurrent_4": {
                        "wall_ms": concurrent_ms,
                        "turns": concurrent,
                    },
                }
    finally:
        temporary.cleanup()
    summary["residual"] = int(temp_root.exists())
    return summary


async def _main() -> None:
    args = _arguments()
    if bool(args.member_table) != bool(args.member_field):
        raise SystemExit("--member-table and --member-field must be supplied together")

    if args.workers <= 0 or args.queue_capacity < args.workers:
        raise SystemExit("workers must be positive and no larger than queue capacity")
    concurrency_levels = [int(item) for item in args.dax_concurrency.split(",")]
    if not concurrency_levels or any(item <= 0 for item in concurrency_levels):
        raise SystemExit("--dax-concurrency must contain positive integers")

    from backend.app.config.settings import Settings

    runtime_settings = Settings()
    adapter = LocalMCPPowerBIAdapter(
        executable=runtime_settings.powerbi_local_mcp_executable,
        package=runtime_settings.powerbi_local_mcp_package,
        semantic_model_key=(
            runtime_settings.powerbi_local_semantic_model_key
        ),
        readonly=runtime_settings.powerbi_local_mcp_readonly,
        timeout=float(runtime_settings.request_timeout_seconds),
        max_retries=0,
        worker_count=args.workers,
        max_pending_operations=args.queue_capacity,
        max_operations_per_request=(
            runtime_settings.powerbi_local_mcp_per_request_limit
        ),
        admission_timeout_seconds=(
            runtime_settings.powerbi_local_mcp_admission_timeout_seconds
        ),
    )
    recorder = PerformanceRecorder()
    token = bind_performance_recorder(recorder)
    output: dict[str, object] = {}
    try:
        catalog, output["discovery_cold_ms"] = await _timed(
            adapter.discover_semantic_models()
        )
        catalog_items = [
            {
                "key": item.key,
                "display_name": item.display_name,
                "available": item.available,
                "connected": item.connected,
                "selectable": item.selectable,
            }
            for item in catalog.items
        ]
        model_key = _select_model(
            catalog_items,
            args.model_display_name,
            require_selectable=False,
        )

        _, output["discovery_warm_ms"] = await _timed(
            adapter.discover_semantic_models()
        )
        probe, output["probe_cold_ms"] = await _timed(
            adapter.probe_compatibility(model_key)
        )
        if not probe.compatible:
            raise RuntimeError(
                "Desktop compatibility probe failed "
                f"(error_type={probe.error_type or 'unknown'})"
            )
        _, output["probe_warm_ms"] = await _timed(
            adapter.probe_compatibility(model_key)
        )
        _, output["schema_cold_ms"] = await _timed(
            adapter.get_semantic_model_schema(model_key)
        )
        _, output["schema_warm_ms"] = await _timed(
            adapter.get_semantic_model_schema(model_key)
        )

        if args.member_table and args.member_field:
            member_request = ColumnMembersRequest(
                semantic_model_key=model_key,
                table_name=args.member_table,
                field_name=args.member_field,
                limit=100,
            )
            _, output["member_cold_ms"] = await _timed(
                adapter.get_column_members(member_request)
            )
            _, output["member_warm_ms"] = await _timed(
                adapter.get_column_members(member_request)
            )

        dax_request = DAXRequest(
            semantic_model_key=model_key,
            dax='EVALUATE ROW("__pbiagent_perf", 1)',
            max_rows=2,
            timeout_seconds=30,
        )
        _, output["dax_first_ms"] = await _timed(adapter.execute_dax(dax_request))
        _, output["dax_second_ms"] = await _timed(adapter.execute_dax(dax_request))

        async def dax_batch(concurrency: int) -> dict[str, Any]:
            async def one() -> tuple[float, dict[str, object]]:
                request_recorder = PerformanceRecorder()
                request_token = bind_performance_recorder(request_recorder)
                try:
                    _, latency_ms = await _timed(adapter.execute_dax(dax_request))
                    return latency_ms, request_recorder.summary()
                finally:
                    reset_performance_recorder(request_token)

            batch_started_at = time.perf_counter_ns()
            results = await asyncio.gather(*(one() for _ in range(concurrency)))
            wall_ms = (
                time.perf_counter_ns() - batch_started_at
            ) / 1_000_000.0
            latencies = [item[0] for item in results]
            summaries = [item[1] for item in results]
            return {
                "concurrency": concurrency,
                "wall_ms": round(wall_ms, 3),
                "throughput_per_second": round(
                    concurrency / (max(wall_ms, 0.001) / 1000.0),
                    3,
                ),
                "p50_ms": _percentile(latencies, 0.50),
                "p95_ms": _percentile(latencies, 0.95),
                "p99_ms": _percentile(latencies, 0.99),
                "queue_wait_p95_ms": _percentile(
                    [float(item["queue_wait_ms"]) for item in summaries],
                    0.95,
                ),
                "worker_ids": sorted({
                    worker_id
                    for item in summaries
                    for worker_id in item["worker_ids"]
                }),
                "errors": 0,
            }

        output["dax_concurrency"] = [
            await dax_batch(level) for level in concurrency_levels
        ]

        started_at = time.perf_counter_ns()
        await asyncio.gather(*(
            adapter.get_semantic_model_schema(model_key)
            for _ in range(8)
        ))
        output["concurrent_schema_8_ms"] = round(
            (time.perf_counter_ns() - started_at) / 1_000_000.0,
            3,
        )
        output["worker_count"] = args.workers
        output["performance"] = recorder.summary()
        if args.full_turn:
            # End the metadata-only session before booting the formal app so
            # the run still proves one application-owned MCP worker at a time.
            await adapter.aclose()
            output["full_turn"] = await _full_turn_profile(args)
    finally:
        reset_performance_recorder(token)
        await adapter.aclose()
    output["lifecycle"] = adapter.runtime_lifecycle_snapshot()
    output["session_close_verified"] = (
        output["lifecycle"] is not None
        and output["lifecycle"]["session_residual"] == 0
        and output["lifecycle"]["active_workers"] == 0
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
