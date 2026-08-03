"""M1.4-A 真实 QueryPlan + DAX Smoke（收紧版）

使用真实 DeepSeek API 和多表 Mock SemanticModelSchema。
调用真实 DeepSeekIntentService，只在 intent=data_question 时继续。
输出仅保留状态、修复次数、Token 和 DAX 哈希。
不输出 measures/dimensions/time_range/top_n/Prompt/DAX/Schema/Secret。
Provider 替换使用 try/finally 恢复。
"""

from __future__ import annotations

import hashlib
import sys
from typing import Any

from backend.app.config.settings import Settings
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.intent.deepseek_service import DeepSeekIntentService
from backend.app.llm.factory import build_llm_registry
from backend.app.llm.base import LLMRequest, LLMResponse
from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService
from backend.app.dax.deepseek_service import DeepSeekDAXService
from backend.app.dax.safety import DAXSafetyValidator
from backend.app.schemas.data_contracts import (
    ColumnSchema,
    MeasureSchema,
    SemanticModelSchema,
    TableSchema,
)


def _make_schema() -> SemanticModelSchema:
    """构建多表 Mock 语义模型"""
    return SemanticModelSchema(
        name="Mock Sales Multi-Table Model",
        key="mock_sales_model",
        tables=[
            TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="SalesKey", data_type="int64", is_hidden=True),
                    ColumnSchema(name="Date", data_type="dateTime"),
                    ColumnSchema(name="Month", data_type="string"),
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="ProductCategory", data_type="string"),
                    ColumnSchema(name="SalesAmount", data_type="decimal"),
                    ColumnSchema(name="CostAmount", data_type="decimal"),
                    ColumnSchema(name="OrderQuantity", data_type="int64"),
                ],
                measures=[
                    MeasureSchema(name="TotalSales", data_type="decimal"),
                    MeasureSchema(name="TotalCost", data_type="decimal"),
                    MeasureSchema(name="Profit", data_type="decimal"),
                    MeasureSchema(name="ProfitMargin", data_type="decimal"),
                    MeasureSchema(name="OrderCount", data_type="int64"),
                ],
            ),
            TableSchema(
                name="Customer",
                columns=[
                    ColumnSchema(name="CustomerKey", data_type="int64", is_hidden=True),
                    ColumnSchema(name="CustomerName", data_type="string"),
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="CustomerSegment", data_type="string"),
                ],
                measures=[
                    MeasureSchema(name="CustomerCount", data_type="int64"),
                ],
            ),
        ],
    )


class _CallCounter:
    """Provider 调用计数器（不修改 Provider 行为）"""

    def __init__(self):
        self.count = 0
        self.token_usage: dict[str, int] = {}

    def record(self, response: LLMResponse) -> None:
        self.count += 1
        if hasattr(response, "usage") and response.usage:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if k in response.usage:
                    self.token_usage[k] = self.token_usage.get(k, 0) + response.usage[k]


async def _run_smoke() -> dict[str, Any]:
    """执行真实 Smoke 测试"""
    settings = Settings(llm_mode="deepseek")
    if not settings.is_deepseek_configured:
        return {
            "success": False,
            "error": "deepseek_api_key_missing",
            "reason": "未配置 DEEPSEEK_API_KEY",
        }

    # 1. 构建 Provider Registry
    registry = build_llm_registry(settings)
    try:
        provider = registry.get("deepseek")
    except KeyError:
        return {
            "success": False,
            "error": "deepseek_provider_not_registered",
            "reason": (
                "DeepSeek Provider 未注册。"
                "请确认 llm_mode='deepseek' 且 DEEPSEEK_API_KEY 已配置。"
            ),
        }

    schema = _make_schema()
    user_input = "统计本月各区域销售额，并按销售额降序取前5名。"

    # 2. 真实意图识别
    intent_service = DeepSeekIntentService(provider=provider, max_format_repairs=1)
    try:
        intent = await intent_service.recognize(user_input)
    except Exception as e:
        return {
            "success": False,
            "error": f"intent_recognition_failed: {type(e).__name__}",
        }

    if intent.intent != IntentType.DATA_QUESTION:
        return {
            "success": False,
            "error": f"intent_not_data_question: {intent.intent.value}",
            "reason": "当前 Smoke 仅覆盖 data_question 路径",
        }

    result: dict[str, Any] = {
        "success": True,
        "intent": "data_question",
    }

    # ── 3. QueryPlan 生成（含修复次数跟踪） ──
    qp_counter = _CallCounter()
    qp_service = DeepSeekQueryPlanService(provider=provider, max_format_repairs=1)

    _original_generate = provider.generate

    async def _qp_tracked_generate(request, output_type):
        response = await _original_generate(request, output_type)
        qp_counter.record(response)
        return response

    provider.generate = _qp_tracked_generate
    try:
        query_plan = await qp_service.generate(user_input, intent, schema)
        result["query_plan_valid"] = True
        result["query_plan_repair_count"] = max(0, qp_counter.count - 1)
    except Exception as e:
        result["success"] = False
        result["query_plan_valid"] = False
        result["query_plan_repair_count"] = qp_counter.count
        result["error"] = f"query_plan_failed: {type(e).__name__}"
        return result
    finally:
        provider.generate = _original_generate

    # ── 4. DAX 生成（含修复次数跟踪） ──
    dax_counter = _CallCounter()
    dax_service = DeepSeekDAXService(provider=provider, max_dax_repairs=1)

    async def _dax_tracked_generate(request, output_type):
        response = await _original_generate(request, output_type)
        dax_counter.record(response)
        return response

    provider.generate = _dax_tracked_generate
    try:
        dax_request = await dax_service.generate(query_plan, schema, request_id="smoke-test")
        result["dax_valid"] = True
        result["dax_repair_count"] = max(0, dax_counter.count - 1)
        dax_sha = hashlib.sha256(dax_request.dax.encode("utf-8")).hexdigest()[:12]
        result["dax_sha256_first12"] = dax_sha
    except Exception as e:
        result["success"] = False
        result["dax_valid"] = False
        result["dax_repair_count"] = dax_counter.count
        result["error"] = f"dax_generation_failed: {type(e).__name__}"
        return result
    finally:
        provider.generate = _original_generate

    # ── 5. DAX 只读安全验证 ──
    safety_validator = DAXSafetyValidator()
    safety_result = safety_validator.validate(dax_request.dax, schema)
    result["dax_read_only"] = safety_result.is_valid
    if not safety_result.is_valid:
        result["success"] = False
        result["error"] = f"dax_safety_failed: {'; '.join(safety_result.errors[:3])}"
        return result

    # ── 6. Token 统计 ──
    result["model"] = getattr(provider, "model", "unknown")
    # 汇总 token 用量
    all_tokens: dict[str, int] = {}
    for counter in (qp_counter, dax_counter):
        for k, v in counter.token_usage.items():
            all_tokens[k] = all_tokens.get(k, 0) + v
    result.update(all_tokens)

    return result


def main():
    """Smoke 入口"""
    import asyncio

    print("=" * 60)
    print("M1.4-A 真实 QueryPlan + DAX Smoke（收紧版）")
    print("=" * 60)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run_smoke())
        loop.close()
    except Exception as e:
        result = {"success": False, "error": str(type(e).__name__)}

    # ── 安全输出（只输出脱敏字段，不输出 Prompt/DAX/Schema/Secret） ──
    safe_fields = [
        "success", "intent",
        "query_plan_valid", "query_plan_repair_count",
        "dax_valid", "dax_read_only", "dax_repair_count",
        "dax_sha256_first12", "model",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "error",
    ]

    safe_output = {k: result.get(k) for k in safe_fields if k in result}

    import json
    print(json.dumps(safe_output, indent=2, ensure_ascii=False))

    if result.get("success"):
        print("\n✅ M1.4-A Smoke 通过")
        sys.exit(0)
    else:
        print("\n❌ M1.4-A Smoke 失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
