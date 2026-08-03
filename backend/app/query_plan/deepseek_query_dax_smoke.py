"""M1.3 真实 QueryPlan + DAX Smoke

使用真实 DeepSeek API 和本地 Mock SemanticModelSchema。
测试合成问题："统计本月各区域销售额，并按销售额降序取前5名。"

安全输出只允许脱敏字段。
"""

from __future__ import annotations

import hashlib
import sys
from typing import Any

from backend.app.config.settings import Settings
from backend.app.intent.context import IntentContextSnapshot
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.factory import build_llm_registry
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
    """构建本地 Mock 语义模型"""
    return SemanticModelSchema(
        name="Mock Sales Model",
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
            )
        ],
    )


async def _run_smoke() -> dict[str, Any]:
    """执行真实 Smoke 测试"""
    settings = Settings()
    if not settings.is_deepseek_configured:
        return {
            "success": False,
            "error": "deepseek_api_key_missing",
            "reason": "未配置 DEEPSEEK_API_KEY",
        }

    # 1. 构建 Provider Registry
    registry = build_llm_registry(settings)
    provider = registry.get("deepseek")

    schema = _make_schema()
    user_input = "统计本月各区域销售额，并按销售额降序取前5名。"

    # 2. 构造已模拟的 IntentSpec（模拟 M1.2 已完成步骤）
    intent = IntentSpec(
        intent=IntentType.DATA_QUESTION,
        confidence=0.95,
        normalized_question=user_input,
    )

    result: dict[str, Any] = {
        "success": True,
        "intent": "data_question",
    }

    # 3. QueryPlan 生成
    qp_service = DeepSeekQueryPlanService(provider=provider, max_format_repairs=1)
    try:
        query_plan = await qp_service.generate(user_input, intent, schema)
        result["query_plan_valid"] = True
        result["measures"] = query_plan.measures
        result["dimensions"] = query_plan.dimensions
        result["time_range"] = query_plan.time_range
        result["top_n"] = query_plan.top_n
    except Exception as e:
        result["success"] = False
        result["query_plan_valid"] = False
        result["error"] = f"query_plan_failed: {type(e).__name__}"
        return result

    # 4. DAX 生成
    dax_service = DeepSeekDAXService(provider=provider, max_dax_repairs=1)
    try:
        dax_request = await dax_service.generate(query_plan, schema, request_id="smoke-test")
        result["dax_valid"] = True
        dax_sha = hashlib.sha256(dax_request.dax.encode("utf-8")).hexdigest()[:12]
        result["dax_sha256_first12"] = dax_sha
    except Exception as e:
        result["success"] = False
        result["dax_valid"] = False
        result["error"] = f"dax_generation_failed: {type(e).__name__}"
        return result

    # 5. DAX 只读安全验证
    safety_validator = DAXSafetyValidator()
    safety_result = safety_validator.validate(dax_request.dax, schema)
    result["dax_read_only"] = safety_result.is_valid
    if not safety_result.is_valid:
        result["success"] = False
        result["error"] = f"dax_safety_failed: {'; '.join(safety_result.errors[:3])}"
        return result

    # 6. Token 统计
    result["model"] = provider.model

    return result


def main():
    """Smoke 入口"""
    import asyncio

    print("=" * 60)
    print("M1.3 真实 QueryPlan + DAX Smoke")
    print("=" * 60)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run_smoke())
        loop.close()
    except Exception as e:
        result = {"success": False, "error": str(type(e).__name__)}

    # ── 安全输出（只输出脱敏字段） ──
    safe_fields = [
        "success", "intent", "query_plan_valid", "dax_valid",
        "dax_read_only", "dax_sha256_first12", "model",
        "measures", "dimensions", "time_range", "top_n", "error",
    ]

    safe_output = {k: result.get(k) for k in safe_fields if k in result}

    import json
    print(json.dumps(safe_output, indent=2, ensure_ascii=False))

    if result.get("success"):
        print("\n✅ M1.3 Smoke 通过")
        sys.exit(0)
    else:
        print("\n❌ M1.3 Smoke 失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
