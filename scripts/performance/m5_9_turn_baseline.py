"""Safe request-local turn timing baseline across supported query shapes.

The default run uses the deterministic Mock provider/adapter to keep CI and
offline stress reproducible.  It reports only status, timing and bounded
runtime counters; response text, prompts, rows and generated HTML are omitted.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.app.config.settings import (  # noqa: E402
    LLMMode,
    PersistenceBackend,
    PowerBIMode,
    Settings,
)
from backend.app.main import create_app  # noqa: E402


_CASES = (
    ("scalar", "本月销售额是多少？", None),
    ("grouped", "按地区统计销售额", None),
    ("ranking", "销售额前三个产品", None),
    ("trend", "每个月销售额趋势", None),
    ("report", "生成销售分析报表", "sales_report"),
)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _safe_metrics(body: dict[str, Any], wall_ms: float) -> dict[str, Any]:
    performance = (body.get("execution_audit") or {}).get("performance") or {}
    safe_fields = (
        "total_ms", "router_ms", "intent_llm_ms", "schema_ms",
        "grounding_ms", "member_lookup_ms", "query_plan_ms", "dax_build_ms",
        "queue_wait_ms", "mcp_rpc_ms", "powerbi_execute_ms",
        "result_inspection_ms", "answer_ms", "report_ms", "db_ms",
        "llm_task_ms", "retry_count", "timeout_count", "cache_hit",
        "cache_miss", "session_new", "session_reused", "queue_depth",
        "worker_ids",
    )
    return {
        "http_status": body.get("_http_status"),
        "terminal_state": body.get("terminal_state"),
        "response_type": body.get("response_type"),
        "wall_ms": round(wall_ms, 3),
        **{field: performance.get(field) for field in safe_fields},
        "usage": {
            field: (body.get("usage") or {}).get(field)
            for field in (
                "call_count", "repair_count", "prompt_tokens",
                "completion_tokens", "total_tokens", "duration_ms",
            )
        },
    }


async def _main() -> None:
    temporary = tempfile.TemporaryDirectory(prefix="powerbiagent-m59-turn-")
    temp_root = Path(temporary.name)
    try:
        settings = Settings(
            llm_mode=LLMMode.MOCK,
            llm_default_profile="mock",
            powerbi_mode=PowerBIMode.MOCK,
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
                async def execute(
                    label: str,
                    message: str,
                    template_key: str | None,
                ) -> dict[str, Any]:
                    started_at = time.perf_counter_ns()
                    response = await client.post("/api/v1/chat", json={
                        "message": message,
                        "conversation_id": f"m59-{label}-{uuid.uuid4()}",
                        "request_id": f"m59-{label}-{uuid.uuid4()}",
                        "semantic_model_key": "mock_sales_model",
                        "report_template_key": template_key,
                        "llm_profile_key": "mock",
                    })
                    wall_ms = (time.perf_counter_ns() - started_at) / 1_000_000.0
                    body = response.json()
                    body["_http_status"] = response.status_code
                    if response.status_code != 200 or body.get("terminal_state") != "completed":
                        raise RuntimeError(f"turn baseline failed: {label}")
                    return _safe_metrics(body, wall_ms)

                cold = await execute("cold-scalar", *_CASES[0][1:])
                cases = {
                    label: await execute(label, message, template)
                    for label, message, template in _CASES
                }

                async def concurrent_batch(concurrency: int) -> dict[str, Any]:
                    started_at = time.perf_counter_ns()
                    results = await asyncio.gather(*(
                        execute(
                            f"concurrency-{concurrency}-{index}",
                            _CASES[index % len(_CASES)][1],
                            _CASES[index % len(_CASES)][2],
                        )
                        for index in range(concurrency)
                    ))
                    wall_ms = (time.perf_counter_ns() - started_at) / 1_000_000.0
                    latencies = [float(item["wall_ms"]) for item in results]
                    safe_wall_ms = max(wall_ms, 0.001)
                    return {
                        "concurrency": concurrency,
                        "wall_ms": round(wall_ms, 3),
                        "throughput_per_second": round(
                            concurrency / (safe_wall_ms / 1000.0), 3
                        ),
                        "p50_ms": _percentile(latencies, 0.50),
                        "p95_ms": _percentile(latencies, 0.95),
                        "p99_ms": _percentile(latencies, 0.99),
                        "errors": 0,
                    }

                concurrency = [
                    await concurrent_batch(level) for level in (1, 4)
                ]
        output = {
            "mode": "offline_deterministic_mock_turns",
            "cold": cold,
            "warm_cases": cases,
            "concurrency": concurrency,
        }
    finally:
        temporary.cleanup()
    output["residual"] = int(temp_root.exists())
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
