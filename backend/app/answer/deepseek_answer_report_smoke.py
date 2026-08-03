"""M1.4.1 Answer + ReportSpec Smoke（真实 DeepSeek + Mock QueryResult）

串联全链路：Intent → QueryPlan → DAX → Answer/ReportSpec → Mock Renderer。
使用真实 DeepSeek API + 本地合成 Schema/QueryResult。不调用真实 Power BI。
不输出 DAX/Prompt/Secret/完整响应。

运行：python -m backend.app.answer.deepseek_answer_report_smoke
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
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


# ── 阶段追踪器 ──

@dataclass
class StageTracker:
    """追踪单个阶段的调用次数和 Token 使用"""
    call_count: int = 0
    token_usage: dict[str, int] = field(default_factory=dict)

    def record(self, response: LLMResponse) -> None:
        self.call_count += 1
        if hasattr(response, "usage") and response.usage:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if k in response.usage:
                    self.token_usage[k] = self.token_usage.get(k, 0) + response.usage[k]

    @property
    def repairs(self) -> int:
        return max(0, self.call_count - 1)


def _wrap_provider(provider, tracker: StageTracker):
    """用阶段追踪器包装 provider.generate"""
    _orig = provider.generate

    async def _tracked(req, ot):
        resp = await _orig(req, ot)
        tracker.record(resp)
        return resp

    return _tracked, _orig


def _safe_error_info(exc: Exception) -> dict[str, str]:
    """从异常中提取安全错误信息"""
    info: dict[str, str] = {}
    info["error_type"] = type(exc).__name__
    for attr in ("error_code", "code", "detail"):
        if hasattr(exc, attr):
            val = getattr(exc, attr)
            if val and isinstance(val, str) and len(val) < 80:
                info["error_code"] = str(val)
                break
    if "error_code" not in info:
        msg = str(exc)
        import re
        m = re.search(r'(answer_|report_|query_plan_|dax_|spec_|intent_)\w+', msg)
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
    for m in re.finditer(
        r'(?:answer_|report_|query_plan_|dax_|evidence_|metric_|chart_|kpi_|table_|spec_|intent_)'
        r'[a-z_]+',
        msg,
    ):
        c = m.group(0)
        if c not in codes:
            codes.append(c)
            if len(codes) >= 5:
                break
    return codes


def _merge_tokens(target: dict[str, int], tracker: StageTracker) -> None:
    """将 tracker 的 Token 合并到 target"""
    for k, v in tracker.token_usage.items():
        target[k] = target.get(k, 0) + v


# ── 主入口 ──

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
    _merge_tokens(all_tokens, qa.pop("_tracker_merged", StageTracker()))

    # ── 案例 B: 报表生成 ──
    rpt = await _run_case_b(provider, schema)
    _merge_tokens(all_tokens, rpt.pop("_tracker_merged", StageTracker()))

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
    global_tokens: dict[str, int] = {}

    # ── 阶段 1: Intent ──
    result["stage"] = "intent"
    intent_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, intent_stage)
    provider.generate = tracked
    try:
        intent_svc = DeepSeekIntentService(provider=provider)
        intent = await intent_svc.recognize(user_input)
        result["intent"] = intent.intent.value
        result["intent_repairs"] = intent_stage.repairs
    except Exception as e:
        result.update(_safe_error_info(e))
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, intent_stage)

    if intent.intent != IntentType.DATA_QUESTION:
        result["intent_mismatch"] = intent.intent.value
        result["error_code"] = "intent_not_data_question"
        return result

    # ── 阶段 2: QueryPlan ──
    result["stage"] = "query_plan"
    qp_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, qp_stage)
    provider.generate = tracked
    try:
        qp_svc = DeepSeekQueryPlanService(provider=provider)
        qp = await qp_svc.generate(user_input, intent, schema)
        result["qp_repairs"] = qp_stage.repairs
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, qp_stage)

    # ── 阶段 3: DAX ──
    result["stage"] = "dax"
    dax_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, dax_stage)
    provider.generate = tracked
    try:
        dax_svc = DeepSeekDAXService(provider=provider)
        qr = _make_query_result()
        dax_req = await dax_svc.generate(qp, schema, request_id="smoke-qa")
        result["dax_repairs"] = dax_stage.repairs
        result["dax_sha"] = hashlib.sha256(dax_req.dax.encode()).hexdigest()[:12]
        result["dax_safe"] = DAXSafetyValidator().validate(dax_req.dax, schema).is_valid
    except Exception as e:
        result.update(_safe_error_info(e))
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, dax_stage)

    # DAX 不安全时提前退出
    if not result.get("dax_safe", False):
        result["error_code"] = "dax_not_safe"
        return result

    # ── 阶段 4: Answer ──
    result["stage"] = "answer"
    ans_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, ans_stage)
    provider.generate = tracked
    try:
        ans_svc = DeepSeekAnswerService(provider=provider)
        answer = await ans_svc.generate(user_input, intent, qp, qr, schema)
        result["answer_repairs"] = ans_stage.repairs
        result["answer_valid"] = True
        result["source_mode"] = answer.source_mode
        result["evidence_bound"] = bool(answer.evidence) and all(
            k in (answer.evidence or {}) for k in
            ("result_id", "semantic_model_key", "row_count", "source_mode")
        )
        # metrics_provenance 验证
        ev = answer.evidence or {}
        provenance = ev.get("metric_provenance")
        result["metrics_provenance_valid"] = (
            not answer.metrics or (isinstance(provenance, dict) and len(provenance) > 0)
        )
        result["answer_sha"] = hashlib.sha256(answer.answer.encode()).hexdigest()[:12]
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, ans_stage)

    # ── 判定 Case A 成功 ──
    checks = [
        result.get("intent") == "data_question",
        result.get("qp_repairs", -1) >= 0,        # QueryPlan 执行过（无异常）
        result.get("dax_repairs", -1) >= 0,        # DAX 执行过
        result.get("dax_safe") is True,
        result.get("answer_valid") is True,
        result.get("evidence_bound") is True,
        result.get("metrics_provenance_valid") is True,
        result.get("source_mode") == "mock",
        result.get("answer_repairs", -1) in (0, 1),
        result.get("error_code") is None,
    ]
    result["success"] = all(checks)

    # 合并 Token
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k in global_tokens:
            result[k] = global_tokens[k]

    # 传递 token tracker 用于全局合并
    tracker = StageTracker()
    tracker.token_usage = global_tokens
    result["_tracker_merged"] = tracker

    return result


async def _run_case_b(provider, schema) -> dict[str, Any]:
    user_input = "根据本周销售数据生成销售经营周报。"
    result: dict[str, Any] = {"case": "report_generation", "success": False}
    global_tokens: dict[str, int] = {}

    # ── 阶段 1: Intent ──
    result["stage"] = "intent"
    intent_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, intent_stage)
    provider.generate = tracked
    try:
        intent_svc = DeepSeekIntentService(provider=provider)
        intent = await intent_svc.recognize(user_input)
        result["intent"] = intent.intent.value
        result["intent_repairs"] = intent_stage.repairs
    except Exception as e:
        result.update(_safe_error_info(e))
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, intent_stage)

    if intent.intent != IntentType.REPORT_GENERATION:
        result["intent_mismatch"] = intent.intent.value
        result["error_code"] = "intent_not_report_generation"
        return result

    # ── 阶段 2: QueryPlan ──
    result["stage"] = "query_plan"
    qp_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, qp_stage)
    provider.generate = tracked
    try:
        qp_svc = DeepSeekQueryPlanService(provider=provider)
        qp = await qp_svc.generate(user_input, intent, schema)
        result["qp_repairs"] = qp_stage.repairs
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, qp_stage)

    # ── 阶段 3: DAX ──
    result["stage"] = "dax"
    dax_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, dax_stage)
    provider.generate = tracked
    try:
        dax_svc = DeepSeekDAXService(provider=provider)
        dax_req = await dax_svc.generate(qp, schema, request_id="smoke-rpt")
        result["dax_repairs"] = dax_stage.repairs
        result["dax_safe"] = DAXSafetyValidator().validate(dax_req.dax, schema).is_valid
    except Exception as e:
        result.update(_safe_error_info(e))
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, dax_stage)

    if not result.get("dax_safe", False):
        result["error_code"] = "dax_not_safe"
        return result

    # ── 阶段 4: ReportSpec ──
    result["stage"] = "report_spec"
    spec_stage = StageTracker()
    tracked, _orig = _wrap_provider(provider, spec_stage)
    provider.generate = tracked
    try:
        qr = _make_query_result()

        # 模板来源：以 QueryPlan 为权威，不构造双来源冲突
        allowed_templates = {"sales_weekly", "satisfaction", "operating_overview"}
        qp_requested = (qp.requested_template or "").strip()
        result["qp_requested_template"] = qp_requested or None

        if qp_requested and qp_requested not in allowed_templates:
            result["error_code"] = "qp_template_not_allowed"
            result["effective_template"] = qp_requested
            result["template_consistent"] = False
            return result

        effective_template = qp_requested or "sales_weekly"
        result["effective_template"] = effective_template
        result["template_consistent"] = True

        spec_svc = DeepSeekReportSpecService(provider=provider)
        spec = await spec_svc.generate(
            user_input, intent, qp, qr, schema,
            template_key=effective_template,
            allowed_templates=allowed_templates,
        )
        result["spec_repairs"] = spec_stage.repairs
        result["spec_valid"] = True
        result["template_key"] = spec.template_key
        result["data_source"] = spec.data_source
        result["source_mode"] = spec.source_mode
        result["has_kpis"] = len(spec.kpis) > 0
        result["has_charts"] = len(spec.charts) > 0
        result["has_tables"] = len(spec.tables) > 0
        spec_json = spec.model_dump_json()
        result["no_chart_type"] = "chart_type" not in spec_json
        result["spec_sha"] = hashlib.sha256(spec_json.encode()).hexdigest()[:12]
    except Exception as e:
        result.update(_safe_error_info(e))
        result["validation_codes"] = _extract_validation_codes(e)
        return result
    finally:
        provider.generate = _orig
        _merge_tokens(global_tokens, spec_stage)

    # ── 阶段 5: Mock Renderer ──
    result["stage"] = "renderer"
    try:
        renderer = MockReportRenderer()
        html = await renderer.render(spec)
        result["renderer_ok"] = bool(html) and "<html" in html
    except Exception as e:
        result.update(_safe_error_info(e))
        # renderer failure isn't a security error but blocks success
        result["renderer_ok"] = False

    # ── 判定 Case B 成功 ──
    eff_tpl = result.get("effective_template", "")
    checks = [
        result.get("intent") == "report_generation",
        result.get("qp_repairs", -1) >= 0,
        result.get("dax_repairs", -1) >= 0,
        result.get("dax_safe") is True,
        result.get("spec_valid") is True,
        result.get("template_consistent") is True,
        eff_tpl in {"sales_weekly", "satisfaction", "operating_overview"},
        result.get("template_key") == eff_tpl,
        result.get("data_source") == "mock_sales_model",
        result.get("source_mode") == "mock",
        result.get("has_kpis") is True,       # KPI 验证通过
        result.get("has_charts") is True,      # Chart 验证通过
        result.get("has_tables") is True,      # Table 验证通过
        result.get("no_chart_type") is True,   # 使用 type 而非 chart_type
        result.get("renderer_ok") is True,
        result.get("spec_repairs", -1) in (0, 1),
        result.get("error_code") is None,
    ]
    result["success"] = all(checks)

    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k in global_tokens:
            result[k] = global_tokens[k]

    tracker = StageTracker()
    tracker.token_usage = global_tokens
    result["_tracker_merged"] = tracker

    return result


def main():
    import asyncio

    print("=" * 60)
    print("M1.4.1 Answer + ReportSpec Smoke（真实 DeepSeek + Mock QueryResult）")
    print("=" * 60)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        smoke_result = loop.run_until_complete(_run_smoke())
        loop.close()
    except Exception as e:
        smoke_result = {"success": False, "error": str(type(e).__name__)}

    # 安全输出白名单
    case_a = smoke_result.get("case_a", {})
    case_b = smoke_result.get("case_b", {})

    safe_output = {
        "success": smoke_result.get("success"),
        "model": smoke_result.get("model"),
        "prompt_tokens": smoke_result.get("prompt_tokens"),
        "completion_tokens": smoke_result.get("completion_tokens"),
        "total_tokens": smoke_result.get("total_tokens"),
        "case_a": {
            "case": case_a.get("case"),
            "success": case_a.get("success"),
            "intent": case_a.get("intent"),
            "stage": case_a.get("stage"),
            "error_type": case_a.get("error_type"),
            "error_code": case_a.get("error_code"),
            "validation_codes": case_a.get("validation_codes"),
            "intent_repairs": case_a.get("intent_repairs"),
            "qp_repairs": case_a.get("qp_repairs"),
            "dax_repairs": case_a.get("dax_repairs"),
            "dax_safe": case_a.get("dax_safe"),
            "dax_sha": case_a.get("dax_sha"),
            "answer_repairs": case_a.get("answer_repairs"),
            "answer_valid": case_a.get("answer_valid"),
            "answer_sha": case_a.get("answer_sha"),
            "source_mode": case_a.get("source_mode"),
            "evidence_bound": case_a.get("evidence_bound"),
            "metrics_provenance_valid": case_a.get("metrics_provenance_valid"),
        },
        "case_b": {
            "case": case_b.get("case"),
            "success": case_b.get("success"),
            "intent": case_b.get("intent"),
            "stage": case_b.get("stage"),
            "error_type": case_b.get("error_type"),
            "error_code": case_b.get("error_code"),
            "validation_codes": case_b.get("validation_codes"),
            "intent_repairs": case_b.get("intent_repairs"),
            "qp_repairs": case_b.get("qp_repairs"),
            "dax_repairs": case_b.get("dax_repairs"),
            "dax_safe": case_b.get("dax_safe"),
            "spec_repairs": case_b.get("spec_repairs"),
            "spec_valid": case_b.get("spec_valid"),
            "spec_sha": case_b.get("spec_sha"),
            "template_key": case_b.get("template_key"),
            "qp_requested_template": case_b.get("qp_requested_template"),
            "effective_template": case_b.get("effective_template"),
            "template_consistent": case_b.get("template_consistent"),
            "data_source": case_b.get("data_source"),
            "source_mode": case_b.get("source_mode"),
            "has_kpis": case_b.get("has_kpis"),
            "has_charts": case_b.get("has_charts"),
            "has_tables": case_b.get("has_tables"),
            "no_chart_type": case_b.get("no_chart_type"),
            "renderer_ok": case_b.get("renderer_ok"),
        },
    }

    import json
    print(json.dumps(safe_output, indent=2, ensure_ascii=False))

    overall = smoke_result.get("success", False)
    if overall:
        print("\n✅ M1.4.1 Smoke 通过")
        sys.exit(0)
    else:
        print("\n❌ M1.4.1 Smoke 失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
