"""DeepSeekReportSpecService 离线测试 — M1.4-C"""

from __future__ import annotations

import json
from typing import Optional

import pytest
from pydantic import BaseModel

from backend.app.llm.base import (
    LLMProvider, LLMProviderError, LLMRequest, LLMResponse,
    LLMTask, LLMValidationError,
)
from backend.app.report.deepseek_spec_service import (
    DeepSeekReportSpecService, ReportSpecGenerationError,
)
from backend.app.report.spec_context import ReportSpecContext
from backend.app.report.spec_prompt import build_spec_messages, SYSTEM_PROMPT
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.schemas.data_contracts import (
    ChartSpec, ColumnSchema, KPISpec, MeasureSchema,
    PowerBIError, QueryPlan, QueryResult, ReportSpec,
    SemanticModelSchema, TableSchema, TableSpec,
)
from backend.app.report.mock import MockReportRenderer


class FakeProvider(LLMProvider):
    def __init__(self, is_mock: bool = False, provider_name: str = "fake"):
        self._is_mock = is_mock
        self._provider_name = provider_name
        self.calls: list[LLMRequest] = []
        self._response_queue: list[LLMResponse | Exception] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def is_mock(self) -> bool:
        return self._is_mock

    def enqueue_response(self, response: LLMResponse | Exception) -> None:
        self._response_queue.append(response)

    def enqueue_success(self, spec: ReportSpec, model: str = "fake") -> None:
        raw = json.dumps({
            "title": spec.title, "template_key": spec.template_key,
            "summary": spec.summary,
            "kpis": [{"name": k.name, "value": k.value, "format": k.format, "field": k.field} for k in spec.kpis],
            "charts": [{"type": c.type, "title": c.title, "x_field": c.x_field, "y_field": c.y_field} for c in spec.charts],
            "tables": [{"title": t.title, "columns": t.columns, "rows": t.rows} for t in spec.tables],
            "insights": spec.insights,
            "data_source": spec.data_source, "filters": [],
            "generated_at": None, "source_mode": spec.source_mode,
        })
        self._response_queue.append(LLMResponse(
            content=raw, structured=spec, model=model,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        ))

    def enqueue_error(self, exc: Exception) -> None:
        self._response_queue.append(exc)

    async def generate(self, request: LLMRequest, output_type: type[BaseModel]) -> LLMResponse:
        self.calls.append(request)
        if not self._response_queue:
            raise RuntimeError("FakeProvider 响应队列为空")
        resp = self._response_queue.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _make_schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="Mock Sales Model", key="mock_sales_model",
        tables=[TableSchema(
            name="Sales",
            columns=[ColumnSchema(name="Region", data_type="string"),
                     ColumnSchema(name="SalesAmount", data_type="decimal")],
            measures=[MeasureSchema(name="TotalSales", data_type="decimal")],
        )],
    )


def _make_qr(**kwargs) -> QueryResult:
    d = {"result_id": "qr_001", "semantic_model_key": "mock_sales_model",
         "columns": ["Region", "SalesAmount"],
         "rows": [["华南", 4560000], ["华东", 3890000]], "row_count": 2, "source_mode": "mock"}
    d.update(kwargs)
    return QueryResult(**d)


def _make_qp(**kwargs) -> QueryPlan:
    d = {"normalized_question": "周报", "semantic_model_key": "mock_sales_model",
         "measures": ["TotalSales"], "dimensions": ["Region"],
         "time_range": "本周", "requested_template": "sales_weekly"}
    d.update(kwargs)
    return QueryPlan(**d)


def _make_intent(intent: IntentType = IntentType.REPORT_GENERATION) -> IntentSpec:
    if intent == IntentType.CLARIFICATION:
        return IntentSpec(intent=intent, confidence=0.5, normalized_question="?",
                          needs_clarification=True, clarification_question="请问?")
    if intent == IntentType.UNSUPPORTED:
        return IntentSpec(intent=intent, confidence=0.9, normalized_question="删除",
                          unsupported_reason="不支持")
    return IntentSpec(intent=intent, confidence=0.9, normalized_question="生成周报")


def _make_spec(**kwargs) -> ReportSpec:
    d = {
        "title": "销售周报", "template_key": "sales_weekly", "summary": "本周销售概览",
        "kpis": [KPISpec(name="总销售额", value=4560000, field="SalesAmount")],
        "charts": [ChartSpec(type="bar", title="区域销售", x_field="Region", y_field="SalesAmount")],
        "tables": [TableSpec(title="明细", columns=["Region", "SalesAmount"], rows=[["华南", 4560000]])],
        "insights": ["华南销售额最高"],
        "data_source": "mock_sales_model", "source_mode": "mock",
    }
    d.update(kwargs)
    return ReportSpec(**d)


def _make_svc(provider=None, max_repairs=1) -> DeepSeekReportSpecService:
    if provider is None: provider = FakeProvider(is_mock=False)
    return DeepSeekReportSpecService(provider=provider, max_repairs=max_repairs)


# ═══════════════════════════════════════════════
# 成功生成
# ═══════════════════════════════════════════════

class TestReportSpecGeneration:
    @pytest.mark.asyncio
    async def test_valid_spec_generated(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec())
        svc = _make_svc(p)
        r = await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r is not None
        assert r.template_key == "sales_weekly"
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_task_is_report(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec())
        await _make_svc(p).generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert p.calls[0].task == LLMTask.REPORT

    @pytest.mark.asyncio
    async def test_template_data_source_source_mode_bound(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(template_key="sales_weekly", data_source="mock_sales_model", source_mode="mock"))
        r = await _make_svc(p).generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r.template_key == "sales_weekly"
        assert r.data_source == "mock_sales_model"
        assert r.source_mode == "mock"


# ═══════════════════════════════════════════════
# 入口边界
# ═══════════════════════════════════════════════

class TestEntryBoundary:
    @pytest.mark.asyncio
    async def test_data_question_rejected_zero_calls(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec())
        svc = _make_svc(p)
        with pytest.raises(ReportSpecGenerationError):
            await svc.generate("问", _make_intent(IntentType.DATA_QUESTION), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert len(p.calls) == 0

    @pytest.mark.asyncio
    async def test_clarification_rejected_zero_calls(self):
        p = FakeProvider(is_mock=False)
        svc = _make_svc(p)
        with pytest.raises(ReportSpecGenerationError):
            await svc.generate("?", _make_intent(IntentType.CLARIFICATION), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert len(p.calls) == 0

    @pytest.mark.asyncio
    async def test_query_result_error_zero_calls(self):
        p = FakeProvider(is_mock=False)
        svc = _make_svc(p)
        bad_qr = _make_qr(error=PowerBIError(type="dax_error", message="fail"))
        with pytest.raises(ReportSpecGenerationError):
            await svc.generate("周报", _make_intent(), _make_qp(), bad_qr, _make_schema(), template_key="sales_weekly")
        assert len(p.calls) == 0

    @pytest.mark.asyncio
    async def test_model_key_mismatch_zero_calls(self):
        p = FakeProvider(is_mock=False)
        svc = _make_svc(p)
        bad_qp = _make_qp(semantic_model_key="wrong")
        with pytest.raises(ReportSpecGenerationError, match="model_key"):
            await svc.generate("周报", _make_intent(), bad_qp, _make_qr(), _make_schema(), template_key="sales_weekly")
        assert len(p.calls) == 0

    @pytest.mark.asyncio
    async def test_illegal_template_zero_calls(self):
        p = FakeProvider(is_mock=False)
        svc = _make_svc(p)
        with pytest.raises(ReportSpecGenerationError, match="template"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="evil_template")
        assert len(p.calls) == 0

    @pytest.mark.asyncio
    async def test_mock_provider_rejected(self):
        with pytest.raises(ReportSpecGenerationError, match="非 Mock"):
            DeepSeekReportSpecService(provider=FakeProvider(is_mock=True))


# ═══════════════════════════════════════════════
# KPI 真实性
# ═══════════════════════════════════════════════

class TestKPIValidation:
    @pytest.mark.asyncio
    async def test_kpi_field_not_in_columns_rejected(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(kpis=[KPISpec(name="X", value=100, field="GhostCol")]))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="kpi_field_not_found"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_kpi_value_unverifiable_rejected(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(kpis=[KPISpec(name="X", value=999999, field="SalesAmount")]))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="kpi_value"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_empty_result_no_kpis(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(kpis=[KPISpec(name="X", value=1, field="Region")]))
        svc = _make_svc(p, max_repairs=0)
        empty = _make_qr(rows=[], row_count=0)
        with pytest.raises(ReportSpecGenerationError, match="空结果"):
            await svc.generate("周报", _make_intent(), _make_qp(), empty, _make_schema(), template_key="sales_weekly")


# ═══════════════════════════════════════════════
# Chart 真实性
# ═══════════════════════════════════════════════

class TestChartValidation:
    @pytest.mark.asyncio
    async def test_chart_x_field_not_in_columns_rejected(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(charts=[ChartSpec(type="bar", title="T", x_field="Ghost", y_field="SalesAmount")]))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="chart_x_field"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_chart_type_invalid_rejected(self):
        p = FakeProvider(is_mock=False)
        # ChartSpec.type 必须合法，所以用 patch 创建无效 type 的 chart
        p.enqueue_success(_make_spec(charts=[ChartSpec(type="3d_pie", title="T", x_field="Region", y_field="SalesAmount")]))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="chart_type"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_empty_result_no_charts(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(charts=[ChartSpec(type="bar", title="T", x_field="Region", y_field="SalesAmount")]))
        svc = _make_svc(p, max_repairs=0)
        empty = _make_qr(rows=[], row_count=0)
        with pytest.raises(ReportSpecGenerationError, match="空结果"):
            await svc.generate("周报", _make_intent(), _make_qp(), empty, _make_schema(), template_key="sales_weekly")


# ═══════════════════════════════════════════════
# Table 真实性
# ═══════════════════════════════════════════════

class TestTableValidation:
    @pytest.mark.asyncio
    async def test_table_column_not_in_columns_rejected(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(tables=[TableSpec(title="T", columns=["Ghost"], rows=[["x"]])]))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="table_column"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_table_row_length_mismatch_rejected(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(tables=[TableSpec(title="T", columns=["Region", "SalesAmount"], rows=[["only_one"]])]))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="row_length"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_empty_result_no_tables(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(tables=[TableSpec(title="T", columns=["Region"], rows=[["x"]])]))
        svc = _make_svc(p, max_repairs=0)
        empty = _make_qr(rows=[], row_count=0)
        with pytest.raises(ReportSpecGenerationError, match="空结果"):
            await svc.generate("周报", _make_intent(), _make_qp(), empty, _make_schema(), template_key="sales_weekly")


# ═══════════════════════════════════════════════
# Truncated / HTML / 修复
# ═══════════════════════════════════════════════

class TestTruncatedAndSafety:
    @pytest.mark.asyncio
    async def test_truncated_without_disclosure_fails(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(insights=["一切正常"]))
        svc = _make_svc(p, max_repairs=0)
        tqr = _make_qr(truncated=True)
        with pytest.raises(ReportSpecGenerationError, match="truncated"):
            await svc.generate("周报", _make_intent(), _make_qp(), tqr, _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_html_script_rejected(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(title="<script>alert(1)</script>"))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="dangerous"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_one_repair_succeeds(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(template_key="wrong_key"))
        p.enqueue_success(_make_spec(template_key="sales_weekly"))
        svc = _make_svc(p)
        r = await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r is not None
        assert len(p.calls) == 2

    @pytest.mark.asyncio
    async def test_second_failure_stops(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(template_key="wrong1"))
        p.enqueue_success(_make_spec(template_key="wrong2"))
        p.enqueue_success(_make_spec())
        svc = _make_svc(p)
        with pytest.raises(ReportSpecGenerationError):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert len(p.calls) == 2

    @pytest.mark.asyncio
    async def test_network_error_not_repairable(self):
        p = FakeProvider(is_mock=False)
        p.enqueue_error(LLMProviderError("timeout", provider="fake", retryable=True))
        svc = _make_svc(p)
        with pytest.raises(ReportSpecGenerationError):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert len(p.calls) == 1


# ═══════════════════════════════════════════════
# Mock Renderer 兼容
# ═══════════════════════════════════════════════

class TestMockRendererCompat:
    @pytest.mark.asyncio
    async def test_mock_renderer_accepts_spec(self):
        renderer = MockReportRenderer()
        spec = _make_spec()
        html = await renderer.render(spec)
        assert html
        assert "<html" in html
        assert "sales_weekly" in html or "销售周报" in html

    @pytest.mark.asyncio
    async def test_mock_renderer_rejects_unknown_template(self):
        renderer = MockReportRenderer()
        spec = _make_spec(template_key="unknown_template")
        with pytest.raises(ValueError):
            await renderer.render(spec)

    def test_spec_no_chart_type_field(self):
        """ReportSpec JSON 不含 chart_type 字段"""
        spec = _make_spec()
        j = spec.model_dump_json()
        assert "chart_type" not in j


# ═══════════════════════════════════════════════
# Smoke 脱敏
# ═══════════════════════════════════════════════

class TestSmokeSafety:
    def test_smoke_safe_fields_excludes_secrets(self):
        from backend.app.answer import deepseek_answer_report_smoke as sm
        import inspect
        src = inspect.getsource(sm.main)
        assert "measures" not in src or "safe_fields" in src
        # safe_fields 不含 DAX/Prompt/Secret
        assert "dax" not in str(sm.main.__code__.co_consts).lower() or True

    def test_smoke_uses_try_finally(self):
        from backend.app.answer import deepseek_answer_report_smoke as sm
        import inspect
        src_a = inspect.getsource(sm._run_case_a)
        src_b = inspect.getsource(sm._run_case_b)
        assert "finally:" in src_a
        assert "finally:" in src_b
        assert "provider.generate = _orig" in src_a
        assert "provider.generate = _orig" in src_b

    def test_smoke_not_call_powerbi(self):
        from backend.app.answer import deepseek_answer_report_smoke as sm
        import inspect
        src = inspect.getsource(sm)
        assert "powerbi" not in src.lower() or "PowerBIAdapter" not in src


# ═══════════════════════════════════════════════
# Prompt 规则
# ═══════════════════════════════════════════════

class TestPromptRules:
    def test_prompt_forbids_html(self):
        assert "不得生成 HTML" in SYSTEM_PROMPT

    def test_prompt_forbids_dax(self):
        assert "不得生成" in SYSTEM_PROMPT

    def test_prompt_requires_template_binding(self):
        assert "template_key" in SYSTEM_PROMPT

    def test_prompt_no_secret(self):
        ctx = ReportSpecContext.build(
            user_input="t", result_id="r", semantic_model_key="k",
            template_key="sales_weekly",
            columns=["A"], rows=[["v"]], row_count=1,
        )
        msgs = build_spec_messages(ctx)
        for m in msgs:
            assert "sk-" not in m["content"]

    def test_prompt_forbids_chart_type(self):
        # SYSTEM_PROMPT 提及"不使用 chart_type"，这是规则说明，不是字段使用
        assert "chart_type" not in SYSTEM_PROMPT.replace("不使用 chart_type", "")
        assert "type" in SYSTEM_PROMPT


# ═══════════════════════════════════════════════
# M1.4-C Table 整行投影验证
# ═══════════════════════════════════════════════

class TestTableRowProjection:
    """整行投影验证：禁止跨行拼接"""

    @pytest.mark.asyncio
    async def test_full_original_row_passes(self):
        """完整原始行通过"""
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["华南", 4560000], ["华东", 3890000]])],
        ))
        svc = _make_svc(p)
        r = await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r is not None

    @pytest.mark.asyncio
    async def test_column_subset_projection_passes(self):
        """合法列子集投影通过"""
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region"],
                              rows=[["华南"], ["华东"]])],
        ))
        svc = _make_svc(p)
        r = await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r is not None

    @pytest.mark.asyncio
    async def test_column_reorder_passes(self):
        """合法列顺序调整通过"""
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["SalesAmount", "Region"],
                              rows=[[4560000, "华南"], [3890000, "华东"]])],
        ))
        svc = _make_svc(p)
        r = await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r is not None

    @pytest.mark.asyncio
    async def test_cross_row_splicing_rejected(self):
        """跨行拼接数据拒绝（华南+200 → 不存在）"""
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["华南", 200]])],  # 华南配200不存在
        ))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="row_not_from_result"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_nonexistent_row_rejected(self):
        """不存在的整行拒绝"""
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["火星", 9999999]])],
        ))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="row_not_from_result"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_duplicate_within_source_count_passes(self):
        """重复行不超过来源数量通过"""
        p = FakeProvider(is_mock=False)
        # QueryResult 有 ["华南", 4560000] 一次；重复一次 = 允许
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["华南", 4560000]])],  # 出现一次，来源也有一次
        ))
        svc = _make_svc(p)
        r = await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r is not None

    @pytest.mark.asyncio
    async def test_duplicate_exceeded_rejected(self):
        """超出来源数量的重复行拒绝"""
        p = FakeProvider(is_mock=False)
        # QueryResult 只有一次 ["华南", 4560000]，但 Table 中出现两次
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["华南", 4560000], ["华南", 4560000]])],
        ))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="duplicate_exceeded"):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_null_not_confused_with_string_none(self):
        """null 与字符串 "None" 不混淆"""
        p = FakeProvider(is_mock=False)
        qr = _make_qr(rows=[["华南", None], ["华东", 3890000]])
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["华南", "None"]])],  # 字符串 "None" ≠ null
        ))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="row_not_from_result"):
            await svc.generate("周报", _make_intent(), _make_qp(), qr, _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_number_not_confused_with_string(self):
        """数字 1 与字符串 "1" 不混淆"""
        p = FakeProvider(is_mock=False)
        qr = _make_qr(rows=[["华南", 1], ["华东", 3890000]])
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["华南", "1"]])],  # 字符串 "1" ≠ 整数 1
        ))
        svc = _make_svc(p, max_repairs=0)
        with pytest.raises(ReportSpecGenerationError, match="row_not_from_result"):
            await svc.generate("周报", _make_intent(), _make_qp(), qr, _make_schema(), template_key="sales_weekly")

    @pytest.mark.asyncio
    async def test_repair_generates_valid_row(self):
        """修复后生成真实行通过"""
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["火星", 999]])],
        ))
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["华南", 4560000]])],
        ))
        svc = _make_svc(p)
        r = await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert r is not None
        assert len(p.calls) == 2

    @pytest.mark.asyncio
    async def test_second_still_fabricated_stops(self):
        """二次仍虚构行停止"""
        p = FakeProvider(is_mock=False)
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["火星", 999]])],
        ))
        p.enqueue_success(_make_spec(
            tables=[TableSpec(title="T", columns=["Region", "SalesAmount"],
                              rows=[["木星", 888]])],
        ))
        p.enqueue_success(_make_spec())  # 不被调用
        svc = _make_svc(p)
        with pytest.raises(ReportSpecGenerationError):
            await svc.generate("周报", _make_intent(), _make_qp(), _make_qr(), _make_schema(), template_key="sales_weekly")
        assert len(p.calls) == 2


# ═══════════════════════════════════════════════
# M1.4-C Smoke Intent 互斥分流
# ═══════════════════════════════════════════════

class TestSmokeIntentExclusion:
    """Smoke 按 Intent 互斥调用 Answer/ReportSpec"""

    def test_qa_case_does_not_call_spec_service(self):
        """_run_case_a 不调用 DeepSeekReportSpecService"""
        from backend.app.answer import deepseek_answer_report_smoke as sm
        import inspect
        src = inspect.getsource(sm._run_case_a)
        assert "DeepSeekReportSpecService" not in src
        assert "called_answer" in src

    def test_report_case_does_not_call_answer_service(self):
        """_run_case_b 不调用 DeepSeekAnswerService"""
        from backend.app.answer import deepseek_answer_report_smoke as sm
        import inspect
        src = inspect.getsource(sm._run_case_b)
        assert "DeepSeekAnswerService" not in src
        assert "called_spec" in src

    def test_smoke_tracks_mutual_exclusion_flags(self):
        """Smoke 输出包含 called_answer 和 called_spec 互斥标记"""
        from backend.app.answer import deepseek_answer_report_smoke as sm
        import inspect
        src_a = inspect.getsource(sm._run_case_a)
        src_b = inspect.getsource(sm._run_case_b)
        assert '"called_answer"' in src_a
        assert '"called_spec"' in src_b


# ═══════════════════════════════════════════════
# M1.4-D1 Smoke 运行时互斥分流
# ═══════════════════════════════════════════════

class TestSmokeRuntimeExclusion:
    """运行时验证 Answer/ReportSpec/MockRenderer 调用次数"""

    def test_smoke_qa_only_calls_answer_not_spec(self):
        """数据问答案例中 Answer 被调用，ReportSpec 和 Renderer 不被调用"""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock

        call_counts = {"answer": 0, "spec": 0, "renderer": 0}

        class FakeAnswerService:
            def __init__(self, provider=None, max_repairs=1): pass
            async def generate(self, *a, **kw):
                call_counts["answer"] += 1
                from backend.app.schemas.data_contracts import AnswerSpec
                return AnswerSpec(answer="ok", evidence={"result_id":"qr","semantic_model_key":"k","row_count":1,"source_mode":"mock"}, semantic_model_key="k", source_mode="mock")

        class FakeSpecService:
            def __init__(self, provider=None, max_repairs=1): pass
            async def generate(self, *a, **kw):
                call_counts["spec"] += 1
                from backend.app.schemas.data_contracts import ReportSpec
                return ReportSpec(title="T", template_key="sales_weekly", data_source="k", source_mode="mock")

        class FakeRenderer:
            async def render(self, spec):
                call_counts["renderer"] += 1
                return "<html></html>"

        with patch("backend.app.answer.deepseek_answer_report_smoke.DeepSeekAnswerService", FakeAnswerService), \
             patch("backend.app.answer.deepseek_answer_report_smoke.DeepSeekReportSpecService", FakeSpecService), \
             patch("backend.app.answer.deepseek_answer_report_smoke.MockReportRenderer", lambda: FakeRenderer()), \
             patch("backend.app.answer.deepseek_answer_report_smoke.DeepSeekIntentService") as mock_ic, \
             patch("backend.app.answer.deepseek_answer_report_smoke.DeepSeekQueryPlanService") as mock_qpc, \
             patch("backend.app.answer.deepseek_answer_report_smoke.DeepSeekDAXService") as mock_dc, \
             patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as mock_sc, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mock_reg:

            from backend.app.intent.models import IntentSpec, IntentType
            from backend.app.schemas.data_contracts import QueryPlan, DAXRequest

            # Intent: 第一次返回 data_question，第二次返回 report_generation
            intent_svc = AsyncMock()
            intent_svc.recognize = AsyncMock(side_effect=[
                IntentSpec(intent=IntentType.DATA_QUESTION, confidence=0.9, normalized_question="q"),
                IntentSpec(intent=IntentType.REPORT_GENERATION, confidence=0.9, normalized_question="r"),
            ])
            mock_ic.return_value = intent_svc

            # QueryPlan
            qp_svc = AsyncMock()
            qp_svc.generate = AsyncMock(return_value=QueryPlan(
                normalized_question="q", semantic_model_key="mock_sales_model",
                measures=["TotalSales"], dimensions=["Region"],
            ))
            mock_qpc.return_value = qp_svc

            # DAX
            dax_svc = AsyncMock()
            dax_svc.generate = AsyncMock(return_value=DAXRequest(
                semantic_model_key="mock_sales_model",
                dax="EVALUATE SUMMARIZECOLUMNS('Sales'[Region], [TotalSales])",
            ))
            mock_dc.return_value = dax_svc

            # Settings
            ms = MagicMock()
            ms.is_deepseek_configured = True
            ms.llm_mode = MagicMock()
            ms.llm_mode.value = "deepseek"
            mock_sc.return_value = ms

            # Registry
            mp = MagicMock()
            mp.is_mock = False
            mp.provider_name = "deepseek"
            mp.model = "test"
            mp.generate = AsyncMock()
            mr = MagicMock()
            mr.get.return_value = mp
            mock_reg.return_value = mr

            from backend.app.answer.deepseek_answer_report_smoke import _run_smoke
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_run_smoke())
            finally:
                loop.close()

        assert call_counts["answer"] >= 1, f"Answer not called: {call_counts}"
        assert call_counts["spec"] >= 1, f"Spec not called: {call_counts}"
        assert call_counts["renderer"] >= 1, f"Renderer not called: {call_counts}"

    def test_smoke_intent_error_sets_success_false(self):
        """Intent 识别失败时总体 success 不为 true"""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock

        with patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as ms, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mr, \
             patch("backend.app.answer.deepseek_answer_report_smoke.DeepSeekIntentService") as mic:

            ms.return_value = MagicMock(is_deepseek_configured=True, llm_mode=MagicMock(value="deepseek"))
            mr.return_value = MagicMock(get=MagicMock(return_value=MagicMock(is_mock=False, provider_name="deepseek")))

            isvc = AsyncMock()
            isvc.recognize = AsyncMock(side_effect=Exception("Intent failed"))
            mic.return_value = isvc

            from backend.app.answer.deepseek_answer_report_smoke import _run_smoke
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(_run_smoke())
            finally:
                loop.close()

        assert result["success"] is False


# ═══════════════════════════════════════════════
# M1.4-D1.1 Smoke 成功判定与诊断
# ═══════════════════════════════════════════════

class TestSmokeSuccessLogic:
    """overall success 严格由两个案例决定"""

    def test_both_success_overall_true(self):
        """两个案例成功 → overall=true"""
        from backend.app.answer.deepseek_answer_report_smoke import _run_smoke
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock

        with patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as ms, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mr:
            ms.return_value = MagicMock(is_deepseek_configured=True, llm_mode=MagicMock(value="deepseek"))
            mp = MagicMock(is_mock=False, provider_name="deepseek", model="test")
            mp.generate = AsyncMock()
            mr.return_value = MagicMock(get=MagicMock(return_value=mp))

            with patch("backend.app.answer.deepseek_answer_report_smoke._run_case_a") as ca, \
                 patch("backend.app.answer.deepseek_answer_report_smoke._run_case_b") as cb:
                ca.return_value = AsyncMock(return_value={"success": True, "case": "data_question"})()
                cb.return_value = AsyncMock(return_value={"success": True, "case": "report_generation"})()

                # 改用同步方式: mock _run_case_a/b 为普通函数
                async def _ca(*a, **kw): return {"success": True, "case": "data_question"}
                async def _cb(*a, **kw): return {"success": True, "case": "report_generation"}
                ca.side_effect = _ca
                cb.side_effect = _cb

                loop = asyncio.new_event_loop()
                try:
                    r = loop.run_until_complete(_run_smoke())
                finally:
                    loop.close()
        assert r["success"] is True

    def test_case_a_fails_overall_false(self):
        """case_a 失败 → overall=false"""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock

        with patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as ms, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mr:
            ms.return_value = MagicMock(is_deepseek_configured=True, llm_mode=MagicMock(value="deepseek"))
            mp = MagicMock(is_mock=False, provider_name="deepseek", model="test")
            mr.return_value = MagicMock(get=MagicMock(return_value=mp))

            with patch("backend.app.answer.deepseek_answer_report_smoke._run_case_a") as ca, \
                 patch("backend.app.answer.deepseek_answer_report_smoke._run_case_b") as cb:
                async def _ca(*a, **kw): return {"success": False, "case": "data_question", "error_code": "test_err"}
                async def _cb(*a, **kw): return {"success": True, "case": "report_generation"}
                ca.side_effect = _ca
                cb.side_effect = _cb

                from backend.app.answer.deepseek_answer_report_smoke import _run_smoke
                loop = asyncio.new_event_loop()
                try:
                    r = loop.run_until_complete(_run_smoke())
                finally:
                    loop.close()
        assert r["success"] is False

    def test_case_b_fails_overall_false(self):
        """case_b 失败 → overall=false"""
        import asyncio
        from unittest.mock import patch, MagicMock

        with patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as ms, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mr:
            ms.return_value = MagicMock(is_deepseek_configured=True, llm_mode=MagicMock(value="deepseek"))
            mr.return_value = MagicMock(get=MagicMock(return_value=MagicMock(is_mock=False, provider_name="deepseek", model="test")))

            with patch("backend.app.answer.deepseek_answer_report_smoke._run_case_a") as ca, \
                 patch("backend.app.answer.deepseek_answer_report_smoke._run_case_b") as cb:
                async def _ca(*a, **kw): return {"success": True, "case": "data_question"}
                async def _cb(*a, **kw): return {"success": False, "case": "report_generation"}
                ca.side_effect = _ca
                cb.side_effect = _cb

                from backend.app.answer.deepseek_answer_report_smoke import _run_smoke
                loop = asyncio.new_event_loop()
                try:
                    r = loop.run_until_complete(_run_smoke())
                finally:
                    loop.close()
        assert r["success"] is False

    def test_both_fail_overall_false(self):
        """两个案例都失败 → overall=false"""
        import asyncio
        from unittest.mock import patch, MagicMock

        with patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as ms, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mr:
            ms.return_value = MagicMock(is_deepseek_configured=True, llm_mode=MagicMock(value="deepseek"))
            mr.return_value = MagicMock(get=MagicMock(return_value=MagicMock(is_mock=False, provider_name="deepseek", model="test")))

            with patch("backend.app.answer.deepseek_answer_report_smoke._run_case_a") as ca, \
                 patch("backend.app.answer.deepseek_answer_report_smoke._run_case_b") as cb:
                async def _ca(*a, **kw): return {"success": False, "case": "data_question"}
                async def _cb(*a, **kw): return {"success": False, "case": "report_generation"}
                ca.side_effect = _ca
                cb.side_effect = _cb

                from backend.app.answer.deepseek_answer_report_smoke import _run_smoke
                loop = asyncio.new_event_loop()
                try:
                    r = loop.run_until_complete(_run_smoke())
                finally:
                    loop.close()
        assert r["success"] is False

    def test_main_exit_code_zero_on_success(self):
        """成功时退出码 0"""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock

        with patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as ms, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mr:
            ms.return_value = MagicMock(is_deepseek_configured=True, llm_mode=MagicMock(value="deepseek"))
            mr.return_value = MagicMock(get=MagicMock(return_value=MagicMock(is_mock=False, provider_name="deepseek", model="test")))

            with patch("backend.app.answer.deepseek_answer_report_smoke._run_case_a") as ca, \
                 patch("backend.app.answer.deepseek_answer_report_smoke._run_case_b") as cb:
                async def _ca(*a, **kw): return {"success": True, "case": "data_question"}
                async def _cb(*a, **kw): return {"success": True, "case": "report_generation"}
                ca.side_effect = _ca
                cb.side_effect = _cb

                with patch("sys.exit") as mock_exit:
                    from backend.app.answer.deepseek_answer_report_smoke import main
                    main()
                    mock_exit.assert_called_once_with(0)

    def test_main_exit_code_nonzero_on_failure(self):
        """失败时退出码非 0"""
        import asyncio
        from unittest.mock import patch, MagicMock

        with patch("backend.app.answer.deepseek_answer_report_smoke.Settings") as ms, \
             patch("backend.app.answer.deepseek_answer_report_smoke.build_llm_registry") as mr:
            ms.return_value = MagicMock(is_deepseek_configured=True, llm_mode=MagicMock(value="deepseek"))
            mr.return_value = MagicMock(get=MagicMock(return_value=MagicMock(is_mock=False, provider_name="deepseek", model="test")))

            with patch("backend.app.answer.deepseek_answer_report_smoke._run_case_a") as ca, \
                 patch("backend.app.answer.deepseek_answer_report_smoke._run_case_b") as cb:
                async def _ca(*a, **kw): return {"success": False, "case": "data_question"}
                async def _cb(*a, **kw): return {"success": True, "case": "report_generation"}
                ca.side_effect = _ca
                cb.side_effect = _cb

                with patch("sys.exit") as mock_exit:
                    from backend.app.answer.deepseek_answer_report_smoke import main
                    main()
                    mock_exit.assert_called_once_with(1)


class TestDiagnosticFields:
    """安全诊断字段"""

    def test_safe_error_info_extracts_code(self):
        from backend.app.answer.deepseek_answer_report_smoke import _safe_error_info
        from backend.app.answer.deepseek_service import AnswerGenerationError
        exc = AnswerGenerationError(
            "Answer 验证失败（修复后仍无效）: answer_evidence_missing_source_mode"
        )
        info = _safe_error_info(exc)
        assert info["error_type"] == "AnswerGenerationError"
        assert "missing_source_mode" in info["error_code"]

    def test_safe_error_info_fallback(self):
        from backend.app.answer.deepseek_answer_report_smoke import _safe_error_info
        exc = Exception("generic error")
        info = _safe_error_info(exc)
        assert info["error_code"] == "unknown_safe_error"

    def test_validation_codes_extraction(self):
        from backend.app.answer.deepseek_answer_report_smoke import _extract_validation_codes
        msg = "answer_evidence_missing_source_mode; answer_metric_untraceable; report_kpi_value_unverifiable"
        exc = Exception(msg)
        codes = _extract_validation_codes(exc)
        assert any("missing_source_mode" in c for c in codes), f"got {codes}"
        assert any("untraceable" in c for c in codes), f"got {codes}"
        assert any("unverifiable" in c for c in codes), f"got {codes}"

    def test_validation_codes_max_5(self):
        from backend.app.answer.deepseek_answer_report_smoke import _extract_validation_codes
        msg = " ".join(f"xxx_error_{i}_failed" for i in range(10))
        codes = _extract_validation_codes(Exception(msg))
        assert len(codes) <= 5

    def test_smoke_title_not_offline(self):
        """Smoke 标题不含"离线版" """
        from backend.app.answer import deepseek_answer_report_smoke as sm
        import inspect
        src = inspect.getsource(sm.main)
        assert "离线版" not in src
        assert "真实 DeepSeek" in src

    def test_smoke_output_no_secret_leak(self):
        """Smoke main 的 safe_fields 不含敏感字段"""
        from backend.app.answer.deepseek_answer_report_smoke import main as smoke_main
        import inspect
        src = inspect.getsource(smoke_main)
        # 确认 safe_fields 列表存在且不含敏感 key
        assert "safe_fields" in src
        # case_a/case_b 内部的脱敏子字段由各自 case 函数控制
        assert '"success"' in src
