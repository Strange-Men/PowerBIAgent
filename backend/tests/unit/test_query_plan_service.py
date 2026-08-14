"""DeepSeekQueryPlanService 离线测试 — M1.3

使用 Fake Provider 完成全部离线测试。绝对禁止访问互联网。

覆盖：
- 四类入口边界（data_question/report_generation/clarification/unsupported）
- clarification/unsupported 不生成 QueryPlan
- Schema 白名单
- 不存在字段被拒绝
- QueryPlan 一次修复
- 不允许第三次调用
- 并发请求无共享状态
- Mock 不回退
- 异常不泄漏 Secret
- Prompt 规则验证
"""

from __future__ import annotations

import json
from typing import Any, Optional
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTask,
    LLMValidationError,
)
from backend.app.query_plan.context import build_schema_view, render_schema_text
from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService, QueryPlanError
from backend.app.query_plan.prompt import (
    SYSTEM_PROMPT,
    build_query_plan_messages,
)
from backend.app.intent.context import IntentContextSnapshot
from backend.app.schemas.data_contracts import (
    ColumnSchema,
    MeasureSchema,
    QueryPlan,
    SemanticModelSchema,
    StructuredFilter,
    TableSchema,
)


# ── Fake Provider ──

class FakeProvider(LLMProvider):
    """可控的 Fake LLM Provider"""

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

    def enqueue_success(self, plan: QueryPlan, model: str = "fake-model",
                        raw_content: str = "") -> None:
        if not raw_content:
            raw_content = json.dumps({
                "normalized_question": plan.normalized_question,
                "semantic_model_key": plan.semantic_model_key,
                "measures": plan.measures,
                "dimensions": plan.dimensions,
                "filters": [{"field": f.field, "operator": f.operator.value, "value": f.value} for f in plan.filters],
                "time_range": plan.time_range,
                "sort": plan.sort,
                "top_n": plan.top_n,
                "comparison_mode": plan.comparison_mode,
                "requested_template": plan.requested_template,
                "inherited_context": plan.inherited_context,
                "is_mock": plan.is_mock,
            })
        self._response_queue.append(LLMResponse(
            content=raw_content,
            structured=plan,
            model=model,
            usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        ))

    def enqueue_error(self, exc: Exception) -> None:
        self._response_queue.append(exc)

    async def generate(
        self,
        request: LLMRequest,
        output_type: type[BaseModel],
    ) -> LLMResponse:
        self.calls.append(request)
        if not self._response_queue:
            raise RuntimeError("FakeProvider 响应队列为空")
        resp = self._response_queue.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


# ── Helpers ──

def _make_schema() -> SemanticModelSchema:
    return SemanticModelSchema(
        name="Mock Sales Model",
        key="mock_sales_model",
        tables=[
            TableSchema(
                name="Sales",
                columns=[
                    ColumnSchema(name="SalesKey", data_type="int64", is_hidden=True),
                    ColumnSchema(name="Date", data_type="dateTime"),
                    ColumnSchema(name="Region", data_type="string"),
                    ColumnSchema(name="ProductCategory", data_type="string"),
                    ColumnSchema(name="SalesAmount", data_type="decimal"),
                    ColumnSchema(name="OrderQuantity", data_type="int64"),
                ],
                measures=[
                    MeasureSchema(name="TotalSales", expression="SUM('Sales'[SalesAmount])"),
                    MeasureSchema(name="TotalCost", expression="SUM('Sales'[CostAmount])"),
                    MeasureSchema(name="Profit", expression="[TotalSales]-[TotalCost]"),
                    MeasureSchema(name="OrderCount", expression="SUM('Sales'[OrderQuantity])"),
                ],
            )
        ],
    )


def _make_svc(provider: Optional[FakeProvider] = None, max_repairs: int = 1) -> DeepSeekQueryPlanService:
    if provider is None:
        provider = FakeProvider(is_mock=False)
    return DeepSeekQueryPlanService(provider=provider, max_format_repairs=max_repairs)


def _make_intent(intent: IntentType = IntentType.DATA_QUESTION) -> IntentSpec:
    return IntentSpec(
        intent=intent,
        confidence=0.9,
        normalized_question="测试问题",
        needs_clarification=(intent == IntentType.CLARIFICATION),
        clarification_question="请说明" if intent == IntentType.CLARIFICATION else None,
        unsupported_reason="不支持" if intent == IntentType.UNSUPPORTED else None,
    )


def _make_plan(**kwargs) -> QueryPlan:
    defaults = {
        "normalized_question": "本月各区域销售额",
        "semantic_model_key": "mock_sales_model",
        "measures": ["TotalSales"],
        "dimensions": ["Region"],
        "filters": [],
        "time_range": "本月",
        "sort": "desc",
        "top_n": 5,
    }
    defaults.update(kwargs)
    return QueryPlan(**defaults)


# ══════════════════════════════════════════════════════════════════
# 四类入口边界
# ══════════════════════════════════════════════════════════════════

class TestEntryBoundary:
    """入口边界测试"""

    @pytest.mark.asyncio
    async def test_data_question_proceeds(self):
        """data_question 生成 QueryPlan"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider)
        result = await svc.generate("本月销售额", _make_intent(IntentType.DATA_QUESTION), _make_schema())
        assert result is not None
        assert result.semantic_model_key == "mock_sales_model"

    @pytest.mark.asyncio
    async def test_report_generation_proceeds(self):
        """report_generation 生成 QueryPlan"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan(requested_template="sales_weekly"))
        svc = _make_svc(provider)
        result = await svc.generate("生成本周周报", _make_intent(IntentType.REPORT_GENERATION), _make_schema())
        assert result is not None

    @pytest.mark.asyncio
    async def test_clarification_rejected(self):
        """clarification 被拒绝"""
        svc = _make_svc()
        with pytest.raises(QueryPlanError, match="clarification"):
            await svc.generate("帮我看看", _make_intent(IntentType.CLARIFICATION), _make_schema())

    @pytest.mark.asyncio
    async def test_unsupported_rejected(self):
        """unsupported 被拒绝"""
        svc = _make_svc()
        with pytest.raises(QueryPlanError, match="unsupported"):
            await svc.generate("删除数据", _make_intent(IntentType.UNSUPPORTED), _make_schema())


# ══════════════════════════════════════════════════════════════════
# Schema 白名单与字段验证
# ══════════════════════════════════════════════════════════════════

class TestSchemaValidation:
    """Schema 白名单与字段验证"""

    @pytest.mark.asyncio
    async def test_real_measures_accepted(self):
        """Schema 中真实存在的度量值被接受"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan(measures=["TotalSales"]))
        svc = _make_svc(provider)
        result = await svc.generate("销售额", _make_intent(), _make_schema())
        assert "TotalSales" in result.measures

    @pytest.mark.asyncio
    async def test_fake_measure_not_accepted(self):
        """虚构的度量值不通过 Pydantic 验证（LLM 输出中的虚构字段）"""
        # 这个测试验证 fake 字段可以被 ValidationService 捕获
        from backend.app.harness.validators.validation_service import ValidationService
        validator = ValidationService()
        schema = _make_schema()
        fake_plan = _make_plan(measures=["FakeMeasure"])
        result = validator.validate_query_plan(fake_plan, schema)
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_schema_view_hides_secrets(self):
        """Schema 视图不暴露 DAX 表达式等敏感信息"""
        schema = _make_schema()
        view = build_schema_view(schema)
        text = render_schema_text(view)
        assert "SUM('Sales'[SalesAmount])" not in text
        assert "expression" not in text.lower()

    def test_schema_text_marks_authoritative_key_and_exact_object_names(self):
        """Schema Prompt 应把 key 和对象名标为逐字复制字段。"""
        text = render_schema_text(build_schema_view(_make_schema()))
        assert "semantic_model_key（必须原样复制到 QueryPlan）" in text
        assert "包括空格和大小写" in text


# ══════════════════════════════════════════════════════════════════
# 一次格式修复
# ══════════════════════════════════════════════════════════════════

class TestOneTimeRepair:
    """一次格式修复测试"""

    @pytest.mark.asyncio
    async def test_first_invalid_json_second_success(self):
        """首次非法 JSON、第二次成功"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMValidationError(
            "bad json", error_code="invalid_content_json",
            provider="fake", retryable=False,
        ))
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider, max_repairs=1)
        result = await svc.generate("测试", _make_intent(), _make_schema())
        assert result is not None
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_second_failure_stops(self):
        """第二次失败后停止"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMValidationError(
            "bad", error_code="invalid_content_json",
            provider="fake", retryable=False,
        ))
        provider.enqueue_error(LLMValidationError(
            "still bad", error_code="output_schema_invalid",
            provider="fake", retryable=False,
        ))
        provider.enqueue_success(_make_plan())  # 不会被调用
        svc = _make_svc(provider, max_repairs=1)
        with pytest.raises(QueryPlanError):
            await svc.generate("测试", _make_intent(), _make_schema())
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_never_calls_third_time(self):
        """绝不调用第三次"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMValidationError(
            "bad", error_code="invalid_content_json",
            provider="fake", retryable=False,
        ))
        provider.enqueue_error(LLMValidationError(
            "still bad", error_code="output_schema_invalid",
            provider="fake", retryable=False,
        ))
        provider.enqueue_success(_make_plan())  # 不会被调用
        svc = _make_svc(provider, max_repairs=1)
        with pytest.raises(QueryPlanError):
            await svc.generate("测试", _make_intent(), _make_schema())
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_provider_error_not_repairable(self):
        """Provider 错误不修复"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMProviderError(
            "service error", provider="fake", retryable=True,
        ))
        svc = _make_svc(provider, max_repairs=1)
        with pytest.raises(QueryPlanError):
            await svc.generate("测试", _make_intent(), _make_schema())
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_repair_disabled_stops(self):
        """修复禁用时首次失败即停止"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMValidationError(
            "bad json", error_code="invalid_content_json",
            provider="fake", retryable=False,
        ))
        svc = _make_svc(provider, max_repairs=0)
        with pytest.raises(QueryPlanError):
            await svc.generate("测试", _make_intent(), _make_schema())
        assert len(provider.calls) == 1


# ══════════════════════════════════════════════════════════════════
# Mock 隔离与并发
# ══════════════════════════════════════════════════════════════════

class TestMockIsolation:
    """Mock 隔离与并发"""

    def test_mock_provider_rejected(self):
        """Mock Provider 被拒绝"""
        with pytest.raises(QueryPlanError, match="非 Mock"):
            DeepSeekQueryPlanService(provider=FakeProvider(is_mock=True))

    @pytest.mark.asyncio
    async def test_scenario_key_is_none(self):
        """真实模式不使用 Scenario Key"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider)
        await svc.generate("测试", _make_intent(), _make_schema())
        assert provider.calls[0].scenario_key is None

    @pytest.mark.asyncio
    async def test_task_is_query_plan(self):
        """task 为 QUERY_PLAN"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider)
        await svc.generate("测试", _make_intent(), _make_schema())
        assert provider.calls[0].task == LLMTask.QUERY_PLAN

    @pytest.mark.asyncio
    async def test_concurrent_requests_independent(self):
        """并发请求独立"""
        import asyncio

        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan(normalized_question="问题A"))
        provider.enqueue_success(_make_plan(normalized_question="问题B"))
        svc = _make_svc(provider)

        async def _call(msg: str) -> QueryPlan:
            return await svc.generate(msg, _make_intent(), _make_schema())

        results = await asyncio.gather(_call("问题A"), _call("问题B"))
        assert results[0].normalized_question == "问题A"
        assert results[1].normalized_question == "问题B"


# ══════════════════════════════════════════════════════════════════
# Prompt 规则
# ══════════════════════════════════════════════════════════════════

class TestPromptRules:
    """Prompt 规则验证"""

    def test_prompt_forbids_dax(self):
        """Prompt 禁止生成 DAX"""
        messages = build_query_plan_messages(
            "测试", "data_question", "schema text",
            IntentContextSnapshot(),
        )
        system = messages[0]["content"]
        assert "不得生成 DAX" in system

    def test_prompt_forbids_answer(self):
        """Prompt 禁止生成答案"""
        messages = build_query_plan_messages(
            "测试", "data_question", "schema text",
            IntentContextSnapshot(),
        )
        system = messages[0]["content"]
        assert "不得生成最终回答" in system

    def test_prompt_forbids_tools(self):
        """Prompt 禁止调用工具"""
        messages = build_query_plan_messages(
            "测试", "data_question", "schema text",
            IntentContextSnapshot(),
        )
        system = messages[0]["content"]
        assert "不得调用工具" in system

    def test_prompt_forbids_fabrication(self):
        """Prompt 禁止虚构字段"""
        messages = build_query_plan_messages(
            "测试", "data_question", "schema text",
            IntentContextSnapshot(),
        )
        system = messages[0]["content"]
        assert "不得虚构" in system

    def test_prompt_requires_json(self):
        """Prompt 要求 JSON"""
        messages = build_query_plan_messages(
            "测试", "data_question", "schema text",
            IntentContextSnapshot(),
        )
        system = messages[0]["content"]
        assert "JSON" in system

    def test_prompt_no_key_leak(self):
        """Prompt 不包含 Secret 模板"""
        messages = build_query_plan_messages(
            "测试", "data_question", "schema text",
            IntentContextSnapshot(),
        )
        for msg in messages:
            assert "sk-" not in msg["content"]

    def test_prompt_has_no_mock_specific_grounding_example(self):
        """Real Schema 的 QueryPlan Prompt 不应被 Mock Key/对象名诱导。"""
        messages = build_query_plan_messages(
            "总销售额是多少？", "data_question", "schema text",
            IntentContextSnapshot(),
        )
        system = messages[0]["content"]
        assert "mock_sales_model" not in system
        assert "TotalSales" not in system
        assert "semantic_model_key 必须逐字等于" in system

    def test_prompt_limits_real_filter_and_sort_contract(self):
        messages = build_query_plan_messages(
            "前3名", "data_question", "schema text", IntentContextSnapshot(),
        )
        system = messages[0]["content"]

        assert 'Filter 只允许 operator="eq"' in system
        assert 'sort 只能是 "asc"、"desc" 或 null' in system
        assert "top_n 非 null 时必须同时提供 sort" in system

    def test_prompt_repair_preserves_measure_and_column_identity(self):
        """Semantic repair 不得放宽 Measure/Column 身份边界。"""
        messages = build_query_plan_messages(
            "Electronics 类别的销售额是多少？",
            "data_question",
            "schema text",
            IntentContextSnapshot(),
            repair_error_code="query_plan_invalid_measure",
            validation_errors=["invalid object"],
        )
        repair = messages[0]["content"]
        assert "不得使用数值列" in repair
        assert "不得使用度量值" in repair


# ══════════════════════════════════════════════════════════════════
# 异常脱敏
# ══════════════════════════════════════════════════════════════════

class TestErrorSanitization:
    """异常脱敏"""

    def test_query_plan_error_no_raw_response(self):
        """QueryPlanError 不包含原始响应"""
        e = QueryPlanError("test")
        assert "choices" not in str(e).lower()

    def test_query_plan_error_no_key(self):
        """QueryPlanError 不包含 Key"""
        e = QueryPlanError("test")
        assert "sk-" not in str(e)

    @pytest.mark.asyncio
    async def test_repair_message_sanitized(self):
        """修复消息不含原始响应"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMValidationError(
            "响应不符合 QueryPlan: detected_measures=['secret_value_test']",
            provider="deepseek",
            retryable=False,
            error_code="output_schema_invalid",
        ))
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider)
        await svc.generate("测试", _make_intent(), _make_schema())
        # 修复请求包含 error_code 但不含原始敏感值
        repair_msg = provider.calls[1].messages[0]["content"]
        assert "secret_value_test" not in repair_msg


# ══════════════════════════════════════════════════════════════════
# M1.3.1 真实 ValidationService 集成测试
# ══════════════════════════════════════════════════════════════════

class TestValidationServiceIntegration:
    """QueryPlan 生成后真实验证"""

    @pytest.mark.asyncio
    async def test_valid_plan_passes_validation(self):
        """合法 QueryPlan 通过 ValidationService 验证"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        plan = _make_plan(
            measures=["TotalSales"],
            dimensions=["Region"],
            semantic_model_key="mock_sales_model",
        )
        provider.enqueue_success(plan)
        svc = _make_svc(provider)
        result = await svc.generate("本月销售额", _make_intent(), schema)
        assert result is not None
        assert result.measures == ["TotalSales"]
        assert result.dimensions == ["Region"]

    @pytest.mark.asyncio
    async def test_fake_measure_triggers_validation_error(self):
        """虚构 measure 触发验证错误并修复"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        # 首次返回虚构指标
        bad_plan = _make_plan(measures=["FakeMetric"])
        provider.enqueue_success(bad_plan)
        # 二次修复返回正确指标
        good_plan = _make_plan(measures=["TotalSales"])
        provider.enqueue_success(good_plan)
        svc = _make_svc(provider)
        result = await svc.generate("销售额", _make_intent(), schema)
        assert result is not None
        assert "TotalSales" in result.measures
        assert "FakeMetric" not in result.measures
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_fake_dimension_triggers_validation_error(self):
        """虚构 dimension 触发验证错误并修复"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        bad_plan = _make_plan(measures=["TotalSales"], dimensions=["FakeDim"])
        provider.enqueue_success(bad_plan)
        good_plan = _make_plan(measures=["TotalSales"], dimensions=["Region"])
        provider.enqueue_success(good_plan)
        svc = _make_svc(provider)
        result = await svc.generate("按区域销售额", _make_intent(), schema)
        assert result is not None
        assert "Region" in result.dimensions
        assert "FakeDim" not in result.dimensions

    @pytest.mark.asyncio
    async def test_fake_filter_field_rejected(self):
        """虚构 filter field 被拒绝并修复"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        from backend.app.schemas.data_contracts import StructuredFilter, FilterOperator
        bad_plan = _make_plan(
            measures=["TotalSales"],
            filters=[StructuredFilter(field="GhostField", operator=FilterOperator.EQ, value="x")],
        )
        provider.enqueue_success(bad_plan)
        good_plan = _make_plan(measures=["TotalSales"])
        provider.enqueue_success(good_plan)
        svc = _make_svc(provider)
        result = await svc.generate("某字段筛选", _make_intent(), schema)
        assert result is not None
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_semantic_model_key_mismatch_rejected(self):
        """semantic_model_key 不匹配被拒绝并修复"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        bad_plan = _make_plan(
            measures=["TotalSales"],
            semantic_model_key="wrong_model_key",
        )
        provider.enqueue_success(bad_plan)
        good_plan = _make_plan(
            measures=["TotalSales"],
            semantic_model_key="mock_sales_model",
        )
        provider.enqueue_success(good_plan)
        svc = _make_svc(provider)
        result = await svc.generate("销售额", _make_intent(), schema)
        assert result is not None
        assert result.semantic_model_key == "mock_sales_model"
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_repair_still_invalid_stops(self):
        """修复后仍错误停止"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        bad_plan1 = _make_plan(measures=["FakeMeasure"])
        provider.enqueue_success(bad_plan1)
        bad_plan2 = _make_plan(measures=["AnotherFake"])
        provider.enqueue_success(bad_plan2)
        provider.enqueue_success(_make_plan())  # 不会被调用
        svc = _make_svc(provider)
        with pytest.raises(QueryPlanError, match="验证修复后仍无效"):
            await svc.generate("销售", _make_intent(), schema)
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_only_two_calls_for_validation_repair(self):
        """验证修复最多两次调用"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        provider.enqueue_success(_make_plan(measures=["GhostMeasure"]))
        provider.enqueue_success(_make_plan(measures=["TotalSales"]))
        provider.enqueue_success(_make_plan())  # 不应被调用
        svc = _make_svc(provider)
        await svc.generate("销售", _make_intent(), schema)
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_format_repair_then_validation_fails_stops(self):
        """格式修复成功但验证失败 → 停止（一次修复已用）"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        provider.enqueue_error(LLMValidationError(
            "bad json", error_code="invalid_content_json",
            provider="fake", retryable=False,
        ))
        # 格式修复成功但返回虚构指标
        provider.enqueue_success(_make_plan(measures=["GhostMeasure"]))
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider)
        with pytest.raises(QueryPlanError):
            await svc.generate("销售", _make_intent(), schema)
        # 格式修复已消耗一次，不能再修复验证错误
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_provider_error_not_repaired_for_validation(self):
        """Provider 网络错误不触发验证修复"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        provider.enqueue_error(LLMProviderError(
            "timeout", provider="fake", retryable=True,
        ))
        svc = _make_svc(provider)
        with pytest.raises(QueryPlanError):
            await svc.generate("销售", _make_intent(), schema)
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_service_uses_validation_service(self):
        """验证 Service 生成后确实调用 validate_query_plan
        （通过验证错误修复场景间接验证：合法 plan 直接通过，非法 plan 触发修复）
        """
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        # 合法 plan 直接通过验证
        provider.enqueue_success(_make_plan(measures=["TotalSales"], dimensions=["Region"]))
        svc = _make_svc(provider)
        result = await svc.generate("销售额", _make_intent(), schema)
        assert result is not None
        assert len(provider.calls) == 1  # 一次通过，无需修复

    @pytest.mark.asyncio
    async def test_repair_instruction_contains_validation_details(self):
        """验证修复请求包含验证错误详情"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        provider.enqueue_success(_make_plan(measures=["FakeMeasure"]))
        provider.enqueue_success(_make_plan(measures=["TotalSales"]))
        svc = _make_svc(provider)
        await svc.generate("销售", _make_intent(), schema)
        # 修复请求包含验证信息
        repair_msg = provider.calls[1].messages[0]["content"]
        assert "验证错误" in repair_msg or "FakeMeasure" in repair_msg

    @pytest.mark.asyncio
    async def test_error_message_no_full_response(self):
        """验证错误不包含完整模型响应"""
        provider = FakeProvider(is_mock=False)
        schema = _make_schema()
        provider.enqueue_success(_make_plan(measures=["FakeMeasure"]))
        provider.enqueue_success(_make_plan(measures=["AlsoFake"]))
        svc = _make_svc(provider)
        with pytest.raises(QueryPlanError) as exc_info:
            await svc.generate("销售", _make_intent(), schema)
        msg = str(exc_info.value)
        assert "choices" not in msg.lower()
        assert len(msg) < 500

    @pytest.mark.asyncio
    async def test_real_grounding_draft_does_not_own_canonical_objects(self):
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan(
            semantic_model_key="llm-invented-model",
            measures=["LLM Invented Measure"],
            dimensions=["LLM Invented Dimension"],
        ))
        svc = _make_svc(provider)
        draft = await svc.generate(
            "销售额",
            _make_intent(),
            _make_schema(),
            semantic_model_key="mock_sales_model",
            enforce_semantic_grounding=True,
        )
        assert draft.semantic_model_key == "mock_sales_model"
        assert draft.measures == ["LLM Invented Measure"]
        assert len(provider.calls) == 1


# ══════════════════════════════════════════════════════════════════
# M1.4-A QueryPlan 模型 Key 权威性测试
# ══════════════════════════════════════════════════════════════════

class TestSemanticModelKeyAuthority:
    """semantic_model_key 权威性校验"""

    @pytest.mark.asyncio
    async def test_matching_key_proceeds(self):
        """semantic_model_key 与 schema.key 一致 → 正常执行"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider)
        result = await svc.generate(
            "测试", _make_intent(), _make_schema(),
            semantic_model_key="mock_sales_model",
        )
        assert result is not None
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_key_not_passed_uses_schema_key(self):
        """未传 semantic_model_key → 使用 schema.key"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan())
        svc = _make_svc(provider)
        result = await svc.generate("测试", _make_intent(), _make_schema())
        assert result is not None
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_mismatched_key_rejected_zero_calls(self):
        """semantic_model_key 与 schema.key 不一致 → 拒绝，0 次 Provider 调用"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_plan())  # 不应被调用
        svc = _make_svc(provider)
        with pytest.raises(QueryPlanError, match="不一致"):
            await svc.generate(
                "测试", _make_intent(), _make_schema(),
                semantic_model_key="wrong_key_xyz",
            )
        assert len(provider.calls) == 0

    @pytest.mark.asyncio
    async def test_mismatched_key_error_sanitized(self):
        """错误消息不包含调用方传入的原始 Key"""
        provider = FakeProvider(is_mock=False)
        svc = _make_svc(provider)
        with pytest.raises(QueryPlanError) as exc_info:
            await svc.generate(
                "测试", _make_intent(), _make_schema(),
                semantic_model_key="alien_model_xyz",
            )
        msg = str(exc_info.value)
        # 不直接回显调用方传入的原始 Key
        assert "alien_model_xyz" not in msg
        # 包含稳定的错误代码
        assert "query_plan_model_key_mismatch" in msg

    @pytest.mark.asyncio
    async def test_mismatched_key_error_has_stable_code(self):
        """错误消息使用稳定错误代码，不含 Schema 内部信息"""
        provider = FakeProvider(is_mock=False)
        svc = _make_svc(provider)
        with pytest.raises(QueryPlanError) as exc_info:
            await svc.generate(
                "测试", _make_intent(), _make_schema(),
                semantic_model_key="another_bad_key",
            )
        msg = str(exc_info.value)
        # 不使用 schema.key 等内部字段
        assert "mock_sales_model" not in msg
        # 有固定错误代码
        assert "query_plan_model_key_mismatch" in msg
        # 有中文说明
        assert "不一致" in msg
