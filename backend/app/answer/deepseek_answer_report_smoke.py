"""M1.4 Answer + ReportSpec Smoke（真实 DeepSeek + Mock QueryResult）

串联全链路：Intent → QueryPlan → DAX → Answer/ReportSpec → Mock Renderer。
使用真实 DeepSeek API + 本地合成 Schema/QueryResult。
不调用真实 Power BI。不输出 DAX/Prompt/Secret/完整响应。

运行：python -m backend.app.answer.deepseek_answer_report_smoke
"""

from __future__ import annotations

import hashlib
import sys
from typing import Any

from backend.app.config.settings import Settings
from backend.app.intent.models import IntentType
from backend.app.intent.deepseek_service import DeepSeekIntentService
from backend.app.llm.factory import build_llm_registry
from backend.app.llm.base import LLMResponse
from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService
from backend.app.dax.deepseek_service import DeepSeekDAXService
from backend.app.dax.safety import DAXSafetyValidator
from backend.app.answer.deepseek_service import DeepSeekAnswerService
from backend.app.report.deepseek_spec_service import DeepSeekReportSpecService
from backend.app.report.mock import MockReportRenderer
from backend.app.schemas.data_contracts import (
    ColumnSchema, MeasureSchema, QueryPlan, QueryResult,
    SemanticModelSchema, TableSchema,
)


def _make_schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="Mock Sales Multi-Table Model",
        key="mock_sales_model",
        tables=[
            TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="Month", data_type="string"),
                    ColumnSchema(name="SalesAmount", data_type="decimal"),
                    ColumnSchema(name="OrderQuantity", data_type="int64"),
                ],
                measures=[
                    MeasureSchema(name="TotalSales", data_type="decimal"),
                    MeasureSchema(name="OrderCount", data_type="int64"),
                ],
            ),
        ],
    )


def _make_query_result(**kwargs) -> QueryResult:
    defaults = {
        "result_id": "qr_smoke_001",
        "semantic_model_key": "mock_sales_model",
        "columns": ["Region", "SalesAmount"],
        "rows": [["华南", 4560000], ["华东", 3890000], ["华北", 3120000]],
        "row_count": 3,
        "source_mode": "mock",
    }
    defaults.update(kwargs)
    return QueryResult(**defaults)


class _CallCounter:
    def __init__(self):
        self.count = 0
        self.token_usage: dict[str, int] = {}

    def record(self, response: LLMResponse) -> None:
        self.count += 1
        if hasattr(response, "usage") and response.usage:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if k in response.usage:
                    self.token_usage[k] = self.token_usage.get(k, 0) + response.usage[k]


def _safe_error_info(exc: Exception) -> dict[str, str]:
    """从异常中提取安全错误信息"""
    info: dict[str, str] = {}
    info["error_type"] = type(exc).__name__
    # 尝试提取 error_code
    for attr in ("error_code", "code", "detail"):
        if hasattr(exc, attr):
            val = getattr(exc, attr)
            if val and isinstance(val, str) and len(val) < 80:
                info["error_code"] = str(val)
                break
    if "error_code" not in info:
        # 从 ValidationResult 类异常中提取内部错误代码
        msg = str(exc)
        import re
        m = re.search(r'(answer_|report_|query_plan_|dax_|spec_)\w+', msg)
        if m:
            info["error_code"] = m.group(0)
        else:
            info["error_code"] = "unknown_safe_error"
    return info


def _extract_validation_codes(exc: Exception) -> list[str]:
    """从异常消息中提取最多 5 个验证错误代码"""
    import re
    codes: list[str] = []
    msg = str(exc)
    # 匹配 answer_*/report_* 等格式的错误代码
    for m in re.finditer(
        r'(?:answer_|report_|query_plan_|dax_|evidence_|metric_|chart_|kpi_|table_|spec_)'
        r'[a-z_]+',
        msg,
    ):
        c = m.group(0)
        if c not in codes:
            codes.append(c)
            if len(codes) >= 5:
                break
    return codes


async def _run_smoke() -> dict[str, Any]:
    settings = Settings(llm_mode="deepseek")
    if not settings.is_deepseek_configured:
        return {"success": False, "error": "deepseek_api_key_missing"}

    registry = build_llm_registry(settings)
    try:
        provider = registry.get("deepseek")
    except KeyError:
        return {"success": False, "error": "deepseek_provider_not_registered"}

    schema = _make_schema()
    all_tokens: dict[str, int] = {}

    # ── 案例 A: 数据问答 ──
    qa = await _run_case_a(provider, schema)
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k in qa:
            all_tokens[k] = all_tokens.get(k, 0) + qa.pop(k, 0)

    # ── 案例 B: 报表生成 ──
    rpt = await _run_case_b(provider, schema)
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k in rpt:
            all_tokens[k] = all_tokens.get(k, 0) + rpt.pop(k, 0)

    overall = qa.get("success", False) and rpt.get("success", False)

    return {
        "success": overall,
        "model": getattr(provider, "model", "unknown"),
        "case_a": qa,
        "case_b": rpt,
        **all_tokens,
    }


async def _run_case_a(provider, schema) -> dict[str, Any]:
    user_input = "统计本月各区域销售额，并按销售额降序取前5名。"
    result: dict[str, Any] = {"case": "data_question", "success": False}
    counter = _CallCounter()
    _orig = provider.generate

    async def _tracked(req, ot):
        resp = await _orig(req, ot)
        counter.record(resp)
        return resp

    # 1. Intent
    result["stage"] = "intent"
    try:
        intent_svc = DeepSeekIntentService(provider=provider)
        intent = await intent_svc.recognize(user_input)
        result["intent"] = intent.intent.value
    except Exception as e:
        result.update(_safe_error_info(e))
        return result

    if intent.intent != IntentType.DATA_QUESTION:
        result["intent_mismatch"] = intent.intent.value
        result["error_code"] = "intent_not_data_question"
        return result

    # 2. QueryPlan
    result["stage"] = "query_plan"
    provider.generate = _tracked
    try:
        qp_svc = DeepSeekQueryPlanService(provider=provider)
        qp = await qp_svc.generate(user_input, intent, schema)
        result["qp_repairs"] = max(0, counter.count - 1)
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig
        result["intent_repairs"] = 0  # intent 不支持修复

    # 3. DAX
    result["stage"] = "dax"
    counter.count = 0
    provider.generate = _tracked
    try:
        dax_svc = DeepSeekDAXService(provider=provider)
        qr = _make_query_result()
        dax_req = await dax_svc.generate(qp, schema, request_id="smoke-qa")
        result["dax_repairs"] = max(0, counter.count - 1)
        result["dax_sha"] = hashlib.sha256(dax_req.dax.encode()).hexdigest()[:12]
        result["dax_safe"] = DAXSafetyValidator().validate(dax_req.dax, schema).is_valid
    except Exception as e:
        result.update(_safe_error_info(e))
        return result
    finally:
        provider.generate = _orig

    # 4. Answer
    result["stage"] = "answer"
    counter.count = 0
    provider.generate = _tracked
    try:
        ans_svc = DeepSeekAnswerService(provider=provider)
        result["called_answer"] = True
        answer = await ans_svc.generate(user_input, intent, qp, qr, schema)
        result["answer_repairs"] = max(0, counter.count - 1)
        result["answer_valid"] = True
        result["source_mode"] = answer.source_mode
        result["has_evidence"] = bool(answer.evidence)
        ans_sha = hashlib.sha256(answer.answer.encode()).hexdigest()[:12]
        result["answer_sha"] = ans_sha
        result["success"] = True
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig
        for k in counter.token_usage:
            result[k] = result.get(k, 0) + counter.token_usage[k]

    return result


async def _run_case_b(provider, schema) -> dict[str, Any]:
    user_input = "根据本周销售数据生成销售经营周报。"
    result: dict[str, Any] = {"case": "report_generation", "success": False}
    counter = _CallCounter()
    _orig = provider.generate

    async def _tracked(req, ot):
        resp = await _orig(req, ot)
        counter.record(resp)
        return resp

    # 1. Intent
    result["stage"] = "intent"
    try:
        intent_svc = DeepSeekIntentService(provider=provider)
        intent = await intent_svc.recognize(user_input)
        result["intent"] = intent.intent.value
    except Exception as e:
        result.update(_safe_error_info(e))
        return result

    if intent.intent != IntentType.REPORT_GENERATION:
        result["intent_mismatch"] = intent.intent.value
        result["error_code"] = "intent_not_report_generation"
        return result

    # 2. QueryPlan
    result["stage"] = "query_plan"
    provider.generate = _tracked
    try:
        qp_svc = DeepSeekQueryPlanService(provider=provider)
        qp = await qp_svc.generate(user_input, intent, schema)
        result["qp_repairs"] = max(0, counter.count - 1)
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig

    # 3. DAX
    result["stage"] = "dax"
    counter.count = 0
    provider.generate = _tracked
    try:
        dax_svc = DeepSeekDAXService(provider=provider)
        dax_req = await dax_svc.generate(qp, schema, request_id="smoke-rpt")
        result["dax_repairs"] = max(0, counter.count - 1)
        result["dax_safe"] = DAXSafetyValidator().validate(dax_req.dax, schema).is_valid
    except Exception as e:
        result.update(_safe_error_info(e))
        return result
    finally:
        provider.generate = _orig

    # 4. ReportSpec
    result["stage"] = "report_spec"
    counter.count = 0
    provider.generate = _tracked
    try:
        qr = _make_query_result()
        spec_svc = DeepSeekReportSpecService(provider=provider)
        result["called_spec"] = True
        spec = await spec_svc.generate(
            user_input, intent, qp, qr, schema,
            template_key="sales_weekly",
        )
        result["spec_repairs"] = max(0, counter.count - 1)
        result["spec_valid"] = True
        result["template_key"] = spec.template_key
        result["data_source"] = spec.data_source
        result["source_mode"] = spec.source_mode
        result["has_kpis"] = len(spec.kpis) > 0
        result["has_charts"] = len(spec.charts) > 0
        result["has_tables"] = len(spec.tables) > 0
        spec_json = spec.model_dump_json()
        result["no_chart_type"] = "chart_type" not in spec_json
        spec_sha = hashlib.sha256(spec_json.encode()).hexdigest()[:12]
        result["spec_sha"] = spec_sha
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig

    # 5. Mock Renderer
    result["stage"] = "renderer"
    try:
        renderer = MockReportRenderer()
        html = await renderer.render(spec)
        result["renderer_ok"] = bool(html) and "<html" in html
    except Exception as e:
        result.update(_safe_error_info(e))
        return result

    result["success"] = True
    for k in counter.token_usage:
        result[k] = result.get(k, 0) + counter.token_usage[k]
    return result


def main():
    import asyncio

    print("=" * 60)
    print("M1.4 Answer + ReportSpec Smoke（真实 DeepSeek + Mock QueryResult）")
    print("=" * 60)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        smoke_result = loop.run_until_complete(_run_smoke())
        loop.close()
    except Exception as e:
        smoke_result = {"success": False, "error": str(type(e).__name__)}

    safe_fields = [
        "success", "model",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "case_a", "case_b",
    ]
    safe_output = {k: smoke_result.get(k) for k in safe_fields if k in smoke_result}

    import json
    print(json.dumps(safe_output, indent=2, ensure_ascii=False))

    overall = smoke_result.get("success", False)
    if overall:
        print("\n✅ M1.4 Smoke 通过")
        sys.exit(0)
    else:
        print("\n❌ M1.4 Smoke 失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
