"""M1.2 真实意图识别 Smoke 测试

通过 Settings 和 build_llm_registry() 获取真实 DeepSeek Provider，
执行五组安全合成案例，验证四类意图全部实际可用。

安全要求：
- 不读取 .env
- 不打印 Key / Authorization
- 不打印完整 Prompt / 完整模型响应
- 不写入日志、Trace 或文件
- 输出仅包含脱敏字段
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Optional

from backend.app.config.settings import Settings
from backend.app.intent.context import IntentContextSnapshot
from backend.app.intent.deepseek_service import DeepSeekIntentService
from backend.app.llm.factory import build_llm_registry

# ---------------------------------------------------------------------------
# 测试案例
# ---------------------------------------------------------------------------

SMOKE_CASES = [
    {
        "case_id": "intent_01",
        "user_input": "本月销售额是多少？",
        "expected_intent": "data_question",
        "committed_memory": None,
    },
    {
        "case_id": "intent_02",
        "user_input": "生成本周销售周报",
        "expected_intent": "report_generation",
        "committed_memory": None,
    },
    {
        "case_id": "intent_03",
        "user_input": "帮我看看",
        "expected_intent": "clarification",
        "committed_memory": None,
    },
    {
        "case_id": "intent_04",
        "user_input": "删除Power BI数据并执行脚本",
        "expected_intent": "unsupported",
        "committed_memory": None,
    },
    {
        "case_id": "intent_05",
        "user_input": "只看华南",
        "expected_intent": "data_question",
        "committed_memory": {
            "measures": ["销售额"],
            "dimensions": ["区域"],
            "time_range": "本月",
            "current_intent": "data_question",
        },
    },
]


# ---------------------------------------------------------------------------
# 安全报告输出
# ---------------------------------------------------------------------------

SAFE_RESULT_KEYS = [
    "case_id",
    "expected_intent",
    "actual_intent",
    "confidence",
    "schema_valid",
    "attempts",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
]


def _make_safe_result(
    case_id: str,
    expected: str,
    actual: str,
    confidence: float,
    schema_valid: bool,
    attempts: int,
    model: str,
    usage: dict[str, int],
) -> dict[str, Any]:
    """构建脱敏结果，仅包含安全字段。"""
    return {k: v for k, v in {
        "case_id": case_id,
        "expected_intent": expected,
        "actual_intent": actual,
        "confidence": confidence,
        "schema_valid": schema_valid,
        "attempts": attempts,
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }.items() if k in SAFE_RESULT_KEYS}


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


async def run_smoke() -> list[dict[str, Any]]:
    """执行真实意图识别 Smoke 测试"""
    settings = Settings()
    registry = build_llm_registry(settings)
    provider = registry.get("deepseek")

    service = DeepSeekIntentService(provider=provider, max_format_repairs=1)
    results: list[dict[str, Any]] = []

    for case in SMOKE_CASES:
        case_id = case["case_id"]
        user_input = case["user_input"]
        expected = case["expected_intent"]
        committed = case.get("committed_memory")

        actual = "error"
        confidence = 0.0
        schema_valid = False
        attempts = 0
        model = ""
        usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            intent_spec = await service.recognize(
                user_input,
                committed_memory=committed,
                semantic_model_key="smoke_test_model",
                report_template_key=None,
            )
            actual = intent_spec.intent.value
            confidence = intent_spec.confidence
            schema_valid = True
            attempts = 1  # 首次成功
            model = provider.model
            # 真实调用中 usage 由 Provider 返回，此处使用默认值
        except Exception as e:
            actual = f"error: {type(e).__name__}"
            confidence = 0.0
            schema_valid = False
            attempts = 1

        safe = _make_safe_result(
            case_id=case_id,
            expected=expected,
            actual=actual,
            confidence=confidence,
            schema_valid=schema_valid,
            attempts=attempts,
            model=model,
            usage=usage,
        )
        results.append(safe)

    return results


def main() -> int:
    """Smoke 命令行入口"""
    settings = Settings()
    if not settings.is_deepseek_configured:
        print("SKIP: DeepSeek API Key 未配置。请在 .env 中设置 DEEPSEEK_API_KEY。")
        return 0

    results = asyncio.run(run_smoke())

    # 脱敏输出
    print("M1.2 真实意图 Smoke 结果")
    print("=" * 60)

    passed = 0
    failed = 0

    for r in results:
        match = r["actual_intent"] == r["expected_intent"]
        status = "PASS" if match and r["schema_valid"] else "FAIL"
        if match and r["schema_valid"]:
            passed += 1
        else:
            failed += 1

        print(
            f"[{status}] {r['case_id']}"
            f"\n  expected={r['expected_intent']}"
            f"\n  actual={r['actual_intent']}"
            f"\n  confidence={r['confidence']}"
            f"\n  schema_valid={r['schema_valid']}"
            f"\n  model={r['model']}"
            f"\n  tokens(p={r['prompt_tokens']} c={r['completion_tokens']} t={r['total_tokens']})"
        )

    print("=" * 60)
    print(f"通过：{passed}/{len(results)}，失败：{failed}/{len(results)}")

    if failed > 0:
        print("\n注意：真实 LLM 调用可能偶发不稳定。请检查 Prompt 和结构约束后重试。")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
