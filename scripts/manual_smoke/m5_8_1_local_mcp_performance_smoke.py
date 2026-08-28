"""Safe cold/warm Local MCP metadata/session performance smoke.

The script prints durations and cache/session counters only.  It never prints
opaque model keys, connection properties, schema contents, member values, DAX,
prompts, or business rows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
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
    parser.add_argument("--model-display-name", required=True)
    parser.add_argument("--member-table")
    parser.add_argument("--member-field")
    parser.add_argument("--full-turn", action="store_true")
    parser.add_argument("--profile", default="deepseek")
    return parser.parse_args()


async def _timed(operation):
    started_at = time.monotonic()
    value = await operation
    return value, round((time.monotonic() - started_at) * 1000.0, 3)


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
        )
        app = create_app(settings=settings)
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app, raise_app_exceptions=True)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                bootstrap_at = time.monotonic()
                discovery = await client.get("/api/v1/semantic-models")
                bootstrap_ms = round((time.monotonic() - bootstrap_at) * 1000.0, 3)
                matches = [
                    item
                    for item in discovery.json().get("items", [])
                    if item.get("selectable") is True
                    and item.get("display_name") == args.model_display_name
                ]
                if discovery.status_code != 200 or len(matches) != 1:
                    raise RuntimeError("requested Desktop display name did not resolve uniquely")
                model_key = matches[0]["key"]

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

    adapter = LocalMCPPowerBIAdapter(max_retries=0)
    recorder = PerformanceRecorder()
    token = bind_performance_recorder(recorder)
    output: dict[str, object] = {}
    try:
        catalog, output["discovery_cold_ms"] = await _timed(
            adapter.discover_semantic_models()
        )
        matches = [
            item for item in catalog.items
            if item.display_name == args.model_display_name
        ]
        if len(matches) != 1:
            raise SystemExit("requested Desktop display name did not resolve uniquely")
        model_key = matches[0].key

        _, output["discovery_warm_ms"] = await _timed(
            adapter.discover_semantic_models()
        )
        _, output["probe_cold_ms"] = await _timed(
            adapter.probe_compatibility(model_key)
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

        started_at = time.monotonic()
        await asyncio.gather(*(
            adapter.get_semantic_model_schema(model_key)
            for _ in range(8)
        ))
        output["concurrent_schema_8_ms"] = round(
            (time.monotonic() - started_at) * 1000.0,
            3,
        )
        output["performance"] = recorder.summary()
        if args.full_turn:
            # End the metadata-only session before booting the formal app so
            # the run still proves one application-owned MCP worker at a time.
            await adapter.aclose()
            output["full_turn"] = await _full_turn_profile(args)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        reset_performance_recorder(token)
        await adapter.aclose()


if __name__ == "__main__":
    asyncio.run(_main())
