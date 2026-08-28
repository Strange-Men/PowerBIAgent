"""M5.8.2 real routing/query-shape acceptance against an open Rich PBIX.

The output contains only control-plane outcomes and latency. It never prints
questions, DAX, schema contents, member values, business rows, or secrets.
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


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-display-name", required=True)
    parser.add_argument("--profile", default="deepseek")
    return parser.parse_args()


def _audit(body: dict[str, Any]) -> dict[str, Any]:
    return body.get("execution_audit") or {}


def _plan(body: dict[str, Any]) -> dict[str, Any]:
    return _audit(body).get("canonical_query_plan") or {}


async def _main() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.app.config.settings import (
        LLMMode,
        PersistenceBackend,
        PowerBIMode,
        Settings,
    )
    from backend.app.main import create_app

    args = _arguments()
    temporary = tempfile.TemporaryDirectory(prefix="powerbiagent-m582-real-")
    temp_root = Path(temporary.name)
    results: list[dict[str, Any]] = []
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
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=True),
                base_url="http://test",
                timeout=180,
            ) as client:
                discovery = await client.get("/api/v1/semantic-models")
                matches = [
                    item
                    for item in discovery.json().get("items", [])
                    if item.get("selectable") is True
                    and item.get("display_name") == args.model_display_name
                ]
                if discovery.status_code != 200 or len(matches) != 1:
                    raise RuntimeError(
                        "requested Desktop display name did not resolve uniquely"
                    )
                model_key = matches[0]["key"]

                async def post(label: str, message: str) -> dict[str, Any]:
                    started_at = time.monotonic()
                    response = await client.post("/api/v1/chat", json={
                        "message": message,
                        "conversation_id": f"m582-real-{label}-{uuid.uuid4().hex}",
                        "request_id": f"m582-real-{label}-{uuid.uuid4().hex}",
                        "semantic_model_key": model_key,
                        "llm_profile_key": args.profile,
                    })
                    body = response.json()
                    if response.status_code != 200:
                        raise RuntimeError(f"case {label} returned HTTP failure")
                    results.append({
                        "case": label,
                        "terminal_state": body.get("terminal_state"),
                        "question_route": _audit(body).get("question_route")
                        or _audit(body).get("capability_decision"),
                        "query_shape": _plan(body).get("query_shape")
                        or _audit(body).get("query_shape"),
                        "dax_executed": bool(_audit(body).get("dax_executed")),
                        "memory_commit": bool(body.get("memory_commit")),
                        "latency_ms": round(
                            (time.monotonic() - started_at) * 1000.0, 3
                        ),
                    })
                    return body

                business_cases = (
                    ("average_order_value", "平均订单金额是多少", "scalar"),
                    ("total_orders", "总订单数是多少", "scalar"),
                    ("product_list", "我们销售了哪些产品？", "entity_list"),
                    ("top_one_product", "销量最高的是哪款产品？", "ranking"),
                    (
                        "bounded_trend_a",
                        "2025年8月到2026年1月销售额月趋势",
                        "bounded_trend",
                    ),
                    (
                        "bounded_trend_b",
                        "从2025年8月至2026年1月按月看销售额",
                        "bounded_trend",
                    ),
                )
                for label, message, shape in business_cases:
                    body = await post(label, message)
                    plan = _plan(body)
                    if body.get("terminal_state") != "completed":
                        raise RuntimeError(f"business case failed: {label}")
                    if plan.get("query_shape") != shape:
                        raise RuntimeError(f"query shape mismatch: {label}")
                    if not _audit(body).get("dax_executed") or not body.get(
                        "memory_commit"
                    ):
                        raise RuntimeError(f"business execution missing: {label}")
                    if shape == "entity_list" and plan.get("measures"):
                        raise RuntimeError("entity list unexpectedly required a measure")
                    if shape == "ranking" and plan.get("top_n") != 1:
                        raise RuntimeError("implicit ranking did not become Top1")

                best = await post("ambiguous_best", "哪些产品卖得最好？")
                if (
                    best.get("terminal_state") != "clarification_required"
                    or best.get("clarification_question")
                    != "请明确用于判断排名的业务指标。"
                    or _audit(best).get("dax_executed")
                ):
                    raise RuntimeError("minimal ranking clarification failed")

                for label, message, shape in (
                    (
                        "member_set",
                        "手机和笔记本的销量分别是多少？",
                        "member_set",
                    ),
                    (
                        "filtered_aggregation",
                        "手机和电脑加起来销量是多少",
                        "filtered_aggregation",
                    ),
                ):
                    body = await post(label, message)
                    if body.get("terminal_state") == "completed":
                        plan = _plan(body)
                        filters = plan.get("filters") or []
                        if (
                            plan.get("query_shape") != shape
                            or len(filters) != 1
                            or filters[0].get("operator") != "in"
                        ):
                            raise RuntimeError(f"member-set shape mismatch: {label}")
                    elif body.get("terminal_state") == "clarification_required":
                        if _audit(body).get("dax_executed") or body.get("memory_commit"):
                            raise RuntimeError(
                                f"unknown member did not fail before DAX: {label}"
                            )
                    else:
                        raise RuntimeError(f"unexpected member-set outcome: {label}")

                for label, message, route in (
                    ("product_help_a", "你支持回答哪些问题？", "product_help"),
                    ("product_help_b", "数据分析支持的范围在哪", "product_help"),
                    ("system_info", "你是什么模型", "system_info"),
                    ("identity", "我是谁", "unsupported_general"),
                    ("calculator_add", "1+1等于几", "deterministic_calc"),
                    ("calculator_multiply", "50乘50是几", "deterministic_calc"),
                ):
                    body = await post(label, message)
                    audit = _audit(body)
                    if (
                        (audit.get("question_route") or audit.get("capability_decision"))
                        != route
                        or audit.get("schema_read")
                        or audit.get("dax_executed")
                        or body.get("memory_commit")
                        or body.get("tool_sequence")
                    ):
                        raise RuntimeError(f"non-business isolation failed: {label}")
    finally:
        temporary.cleanup()

    latencies = [item["latency_ms"] for item in results]
    output = {
        "passed": len(results) == 15,
        "case_count": len(results),
        "cases": results,
        "latency_ms": {
            "min": min(latencies),
            "max": max(latencies),
            "mean": round(sum(latencies) / len(latencies), 3),
        },
        "residual": int(temp_root.exists()),
    }
    if not output["passed"] or output["residual"]:
        raise RuntimeError("M5.8.2 real acceptance failed")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
