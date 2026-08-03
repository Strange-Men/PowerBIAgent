"""M1.5 DeepSeek Chat Smoke（真实 DeepSeek + Mock Power BI + ASGITransport）

通过 ASGITransport 调用本地 /health 和 /api/v1/chat。
使用真实 DeepSeek + MockPowerBIAdapter + MockReportRenderer。
不调用真实 Power BI。不输出 DAX/Prompt/Secret/Answer 原文。

运行：python -m backend.app.application.deepseek_chat_smoke
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any


def _safe_hash(text: str) -> str:
    """SHA-256 前 12 字符"""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


_SAFE_FIELDS = frozenset({
    "case", "success", "health_status", "version",
    "llm_mode", "powerbi_mode", "http_status", "intent",
    "response_type", "terminal_state", "source_mode",
    "memory_commit", "idempotent_replay",
    "trace_id_hash", "tool_sequence",
    "call_count", "repair_count",
    "prompt_tokens", "completion_tokens", "total_tokens",
    "duration_ms", "estimated_cost_usd",
    "error_type", "template_key", "request_id_hash",
    "replay_call_count", "original_call_count",
})


def _safe_result(case: dict[str, Any]) -> dict[str, Any]:
    """只输出白名单字段"""
    return {k: v for k, v in case.items() if k in _SAFE_FIELDS}


async def _run_smoke() -> dict[str, Any]:
    """运行 Smoke 测试"""
    from httpx import ASGITransport, AsyncClient

    from backend.app.main import create_app
    from backend.app.config.settings import LLMMode, PowerBIMode, Settings

    # ── 加载 Settings ──
    settings = Settings(llm_mode=LLMMode.DEEPSEEK, powerbi_mode=PowerBIMode.MOCK)

    if not settings.is_deepseek_configured:
        print(json.dumps({
            "overall_success": False,
            "error": "DEEPSEEK_API_KEY 未配置。请在 .env 中设置。",
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # ── 创建 App ──
    app = create_app(settings=settings)
    transport = ASGITransport(app=app)
    results: list[dict[str, Any]] = []

    # ── 显式进入 lifespan，确保 TurnService 初始化 ──
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # ── Health Check ──
            health_resp = await client.get("/health")
            health_data = health_resp.json()

            # ── Case A: data_question ──
            req_a = {"message": "本月销售额是多少？", "semantic_model_key": "mock_sales_model"}
            resp_a = await client.post("/api/v1/chat", json=req_a)
            data_a = resp_a.json()
            results.append({
                "case": "data_question",
                "success": resp_a.status_code == 200 and data_a.get("terminal_state") == "completed",
                "http_status": resp_a.status_code,
                "intent": data_a.get("intent", ""),
                "response_type": data_a.get("response_type", ""),
                "terminal_state": data_a.get("terminal_state", ""),
                "source_mode": data_a.get("source_mode", ""),
                "memory_commit": data_a.get("memory_commit", False),
                "idempotent_replay": data_a.get("idempotent_replay", False),
                "trace_id_hash": _safe_hash(data_a.get("trace_id", "")),
                "tool_sequence": data_a.get("tool_sequence", []),
                "error_type": data_a.get("error_type"),
                "request_id_hash": _safe_hash(data_a.get("request_id", "")),
            })
            if data_a.get("usage"):
                results[-1].update(data_a["usage"])

            # ── Case B: report_generation ──
            req_b = {
                "message": "生成销售周报",
                "report_template_key": "sales_weekly",
                "semantic_model_key": "mock_sales_model",
            }
            resp_b = await client.post("/api/v1/chat", json=req_b)
            data_b = resp_b.json()
            results.append({
                "case": "report_generation",
                "success": resp_b.status_code == 200 and data_b.get("terminal_state") == "completed",
                "http_status": resp_b.status_code,
                "intent": data_b.get("intent", ""),
                "response_type": data_b.get("response_type", ""),
                "terminal_state": data_b.get("terminal_state", ""),
                "source_mode": data_b.get("source_mode", ""),
                "memory_commit": data_b.get("memory_commit", False),
                "idempotent_replay": data_b.get("idempotent_replay", False),
                "trace_id_hash": _safe_hash(data_b.get("trace_id", "")),
                "tool_sequence": data_b.get("tool_sequence", []),
                "error_type": data_b.get("error_type"),
                "template_key": (data_b.get("report") or {}).get("template_key", ""),
                "request_id_hash": _safe_hash(data_b.get("request_id", "")),
            })
            if data_b.get("usage"):
                results[-1].update(data_b["usage"])

            # ── Case C: clarification ──
            req_c = {"message": "帮", "semantic_model_key": "mock_sales_model"}
            resp_c = await client.post("/api/v1/chat", json=req_c)
            data_c = resp_c.json()
            results.append({
                "case": "clarification",
                "success": data_c.get("intent") == "clarification",
                "http_status": resp_c.status_code,
                "intent": data_c.get("intent", ""),
                "response_type": data_c.get("response_type", ""),
                "terminal_state": data_c.get("terminal_state", ""),
                "source_mode": data_c.get("source_mode", ""),
                "memory_commit": data_c.get("memory_commit", False),
                "idempotent_replay": data_c.get("idempotent_replay", False),
                "trace_id_hash": _safe_hash(data_c.get("trace_id", "")),
                "tool_sequence": data_c.get("tool_sequence", []),
                "error_type": data_c.get("error_type"),
                "request_id_hash": _safe_hash(data_c.get("request_id", "")),
            })
            if data_c.get("usage"):
                results[-1].update(data_c["usage"])

            # ── Case D: unsupported ──
            req_d = {
                "message": "帮我写一封邮件通知销售团队本周业绩",
                "semantic_model_key": "mock_sales_model",
            }
            resp_d = await client.post("/api/v1/chat", json=req_d)
            data_d = resp_d.json()
            results.append({
                "case": "unsupported",
                "success": data_d.get("intent") == "unsupported",
                "http_status": resp_d.status_code,
                "intent": data_d.get("intent", ""),
                "response_type": data_d.get("response_type", ""),
                "terminal_state": data_d.get("terminal_state", ""),
                "source_mode": data_d.get("source_mode", ""),
                "memory_commit": data_d.get("memory_commit", False),
                "idempotent_replay": data_d.get("idempotent_replay", False),
                "trace_id_hash": _safe_hash(data_d.get("trace_id", "")),
                "tool_sequence": data_d.get("tool_sequence", []),
                "error_type": data_d.get("error_type"),
                "request_id_hash": _safe_hash(data_d.get("request_id", "")),
            })
            if data_d.get("usage"):
                results[-1].update(data_d["usage"])

            # ── Case E: 幂等重放 ──
            if data_a.get("request_id"):
                replay_req = {
                    "message": "本月销售额是多少？",
                    "request_id": data_a["request_id"],
                    "semantic_model_key": "mock_sales_model",
                }
                resp_e = await client.post("/api/v1/chat", json=replay_req)
                data_e = resp_e.json()
                results.append({
                    "case": "idempotent_replay",
                    "success": data_e.get("idempotent_replay") is True,
                    "http_status": resp_e.status_code,
                    "intent": data_e.get("intent", ""),
                    "terminal_state": data_e.get("terminal_state", ""),
                    "idempotent_replay": data_e.get("idempotent_replay", False),
                    "request_id_hash": _safe_hash(data_e.get("request_id", "")),
                })
                if data_e.get("usage") and data_a.get("usage"):
                    results[-1]["replay_call_count"] = data_e["usage"].get("call_count", -1)
                    results[-1]["original_call_count"] = data_a["usage"].get("call_count", -1)

            # ── Case F: request_id 冲突 (409) ──
            conflict_req = {
                "message": "完全不同的消息内容",
                "request_id": data_a.get("request_id", ""),
                "semantic_model_key": "mock_sales_model",
            }
            resp_f = await client.post("/api/v1/chat", json=conflict_req)
            data_f = resp_f.json()
            results.append({
                "case": "request_id_conflict",
                "success": resp_f.status_code == 409,
                "http_status": resp_f.status_code,
                "error_type": data_f.get("error_type", ""),
            })

    # ── 汇总 ──
    overall_success = all(r.get("success", False) for r in results)
    safe_results = [_safe_result(r) for r in results]

    output = {
        "overall_success": overall_success,
        "health": {
            "status": health_data.get("status"),
            "ready": health_data.get("ready"),
            "version": health_data.get("version"),
            "llm_mode": health_data.get("llm_mode"),
            "powerbi_mode": health_data.get("powerbi_mode"),
        },
        "cases": safe_results,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

    if not overall_success:
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(_run_smoke())
