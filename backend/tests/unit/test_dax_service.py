"""DeepSeekDAXService 与 DAX 安全验证离线测试 — M1.3

使用 Fake Provider 完成全部离线测试。绝对禁止访问互联网。

覆盖：
- DAX 成功生成
- DAX 只读安全验证 (安全/不安全)
- 非法对象拒绝
- SQL/脚本/写操作拒绝
- 注释绕过拒绝
- 多语句注入拒绝
- 空 DAX 拒绝
- Schema 外对象拒绝
- DAX 一次修复
- 不允许第三次调用
- Mock 不回退
- 异常不泄漏 Secret
- Prompt 规则验证
"""

from __future__ import annotations

import json
from typing import Optional
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTask,
    LLMValidationError,
)
from backend.app.dax.deepseek_service import DAXGenerationError, DeepSeekDAXService
from backend.app.dax.prompt import build_dax_messages, SYSTEM_PROMPT
from backend.app.dax.safety import DAXSafetyValidator, DAXSafetyResult
from backend.app.query_plan.context import build_schema_view, render_schema_text
from backend.app.schemas.data_contracts import (
    ColumnSchema,
    DAXRequest,
    MeasureSchema,
    QueryPlan,
    SemanticModelSchema,
    TableSchema,
)


# ── Fake Provider ──

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

    def enqueue_success(self, dax_req: DAXRequest, model: str = "fake-model") -> None:
        raw = json.dumps({
            "semantic_model_key": dax_req.semantic_model_key,
            "dax": dax_req.dax,
            "max_rows": dax_req.max_rows,
            "timeout_seconds": dax_req.timeout_seconds,
            "request_id": dax_req.request_id,
            "is_mock": False,
        })
        self._response_queue.append(LLMResponse(
            content=raw,
            structured=dax_req,
            model=model,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
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

SAFE_DAX = (
    'EVALUATE '
    'TOPN(5, '
    'SUMMARIZECOLUMNS('
    "'Sales'[Region], "
    '"TotalSales", '
    "SUM('Sales'[SalesAmount])"
    '), '
    '[TotalSales], '
    'DESC'
    ')'
)


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


def _make_plan(**kwargs) -> QueryPlan:
    defaults = {
        "normalized_question": "本月各区域销售额 Top 5",
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


def _make_dax(dax: str = SAFE_DAX, **kwargs) -> DAXRequest:
    defaults = {
        "semantic_model_key": "mock_sales_model",
        "dax": dax,
        "max_rows": 1000,
        "timeout_seconds": 30,
        "request_id": "test-req",
        "is_mock": False,
    }
    defaults.update(kwargs)
    return DAXRequest(**defaults)


def _make_svc(provider: Optional[FakeProvider] = None, max_repairs: int = 1) -> DeepSeekDAXService:
    if provider is None:
        provider = FakeProvider(is_mock=False)
    return DeepSeekDAXService(provider=provider, max_dax_repairs=max_repairs)


# ══════════════════════════════════════════════════════════════════
# DAX 成功生成
# ══════════════════════════════════════════════════════════════════

class TestDAXGeneration:
    """DAX 成功生成"""

    @pytest.mark.asyncio
    async def test_safe_dax_generated(self):
        """安全 DAX 生成成功"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_dax())
        svc = _make_svc(provider)
        result = await svc.generate(_make_plan(), _make_schema())
        assert result is not None
        assert result.semantic_model_key == "mock_sales_model"
        assert "EVALUATE" in result.dax

    @pytest.mark.asyncio
    async def test_semantic_model_key_set(self):
        """semantic_model_key 正确设置"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_dax())
        svc = _make_svc(provider)
        result = await svc.generate(_make_plan(), _make_schema(), semantic_model_key="custom_model")
        assert result.semantic_model_key == "custom_model"

    @pytest.mark.asyncio
    async def test_request_id_set(self):
        """request_id 正确设置"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_dax())
        svc = _make_svc(provider)
        result = await svc.generate(_make_plan(), _make_schema(), request_id="req-123")
        assert result.request_id == "req-123"

    @pytest.mark.asyncio
    async def test_is_mock_false(self):
        """is_mock 为 False"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_dax())
        svc = _make_svc(provider)
        result = await svc.generate(_make_plan(), _make_schema())
        assert result.is_mock is False


# ══════════════════════════════════════════════════════════════════
# DAX 只读安全验证
# ══════════════════════════════════════════════════════════════════

class TestDAXSafetyValidation:
    """DAX 只读安全验证"""

    def test_safe_evaluate_summarizecolumns(self):
        """EVALUATE + SUMMARIZECOLUMNS 通过安全验证"""
        validator = DAXSafetyValidator()
        result = validator.validate(SAFE_DAX)
        assert result.is_valid is True

    def test_safe_define_measure(self):
        """DEFINE MEASURE + EVALUATE 通过安全验证"""
        dax = (
            "DEFINE MEASURE 'Sales'[TotalQty] = SUM('Sales'[OrderQuantity])\n"
            "EVALUATE SUMMARIZECOLUMNS('Sales'[Region], [TotalQty])"
        )
        validator = DAXSafetyValidator()
        result = validator.validate(dax)
        assert result.is_valid is True

    def test_safe_var_return(self):
        """VAR + RETURN 通过安全验证"""
        dax = (
            "EVALUATE "
            "VAR top_regions = TOPN(5, VALUES('Sales'[Region]), [TotalSales]) "
            "RETURN top_regions"
        )
        validator = DAXSafetyValidator()
        result = validator.validate(dax)
        assert result.is_valid is True

    def test_sql_select_rejected(self):
        """SQL SELECT 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("SELECT * FROM Sales")
        assert result.is_valid is False

    def test_write_operation_rejected(self):
        """DELETE 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("EVALUATE; DELETE FROM Sales")
        assert result.is_valid is False

    def test_update_rejected(self):
        """UPDATE 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("UPDATE Sales SET Region = 'North'")
        assert result.is_valid is False

    def test_python_rejected(self):
        """Python import 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate('import os; os.system("rm -rf /")')
        assert result.is_valid is False

    def test_javascript_rejected(self):
        """JavaScript function 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("function hack() { process.exit(0); }")
        assert result.is_valid is False

    def test_shell_rejected(self):
        """Shell 脚本被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("#!/bin/bash\nrm -rf /")
        assert result.is_valid is False

    def test_comment_bypass_rejected(self):
        """注释绕过被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("EVALUATE Sales -- EVALUATE\n-- DROP TABLE")
        assert result.is_valid is False

    def test_block_comment_rejected(self):
        """块注释被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("EVALUATE /* hidden */ Sales")
        assert result.is_valid is False

    def test_semicolon_injection_rejected(self):
        """分号多语句被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("EVALUATE Sales; EVALUATE Another")
        assert result.is_valid is False

    def test_empty_dax_rejected(self):
        """空 DAX 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("")
        assert result.is_valid is False

    def test_blank_dax_rejected(self):
        """空白 DAX 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("   ")
        assert result.is_valid is False

    def test_no_evaluate_rejected(self):
        """无 EVALUATE 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("SUMMARIZECOLUMNS('Sales'[Region], [TotalSales])")
        assert result.is_valid is False

    def test_too_many_evaluates_rejected(self):
        """多个 EVALUATE 被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("EVALUATE T1\nEVALUATE T2")
        assert result.is_valid is False

    def test_schema_object_validation(self):
        """Schema 对象验证 - 非法对象被标记"""
        validator = DAXSafetyValidator()
        schema = _make_schema()
        dax = "EVALUATE SUMMARIZECOLUMNS('Sales'[Region], [FakeMeasure])"
        result = validator.validate(dax, schema)
        # FakeMeasure 不在 schema 中
        assert result.is_valid is False
        assert any("FakeMeasure" in e for e in result.errors)

    def test_schema_object_validation_known_objects_pass(self):
        """Schema 中存在的对象通过验证"""
        validator = DAXSafetyValidator()
        schema = _make_schema()
        result = validator.validate(SAFE_DAX, schema)
        assert result.is_valid is True

    def test_excessive_length_rejected(self):
        """超长 DAX 被拒绝"""
        validator = DAXSafetyValidator(max_dax_length=100)
        long_dax = "EVALUATE " + "'Sales'[Region], " * 50
        result = validator.validate(long_dax)
        assert result.is_valid is False

    def test_referenced_objects_extracted(self):
        """验证结果包含引用对象列表"""
        validator = DAXSafetyValidator()
        result = validator.validate(SAFE_DAX)
        assert "Sales" in result.referenced_objects
        assert "Region" in result.referenced_objects

    def test_dax_refresh_function_rejected(self):
        """REFRESH 函数被拒绝"""
        validator = DAXSafetyValidator()
        result = validator.validate("EVALUATE Sales\nREFRESH Sales")
        assert result.is_valid is False


# ══════════════════════════════════════════════════════════════════
# DAX 一次修复
# ══════════════════════════════════════════════════════════════════

class TestDAXRepair:
    """DAX 一次修复"""

    @pytest.mark.asyncio
    async def test_invalid_json_repair_success(self):
        """首次非法 JSON、第二次成功"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMValidationError(
            "bad json", error_code="invalid_content_json",
            provider="fake", retryable=False,
        ))
        provider.enqueue_success(_make_dax())
        svc = _make_svc(provider, max_repairs=1)
        result = await svc.generate(_make_plan(), _make_schema())
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
        provider.enqueue_success(_make_dax())  # 不被调用
        svc = _make_svc(provider, max_repairs=1)
        with pytest.raises(DAXGenerationError):
            await svc.generate(_make_plan(), _make_schema())
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_never_third_call(self):
        """绝不第三次调用"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMValidationError(
            "bad", error_code="invalid_content_json",
            provider="fake", retryable=False,
        ))
        provider.enqueue_error(LLMValidationError(
            "also bad", error_code="output_schema_invalid",
            provider="fake", retryable=False,
        ))
        provider.enqueue_success(_make_dax())  # 不被调用
        svc = _make_svc(provider, max_repairs=1)
        with pytest.raises(DAXGenerationError):
            await svc.generate(_make_plan(), _make_schema())
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_provider_error_not_repairable(self):
        """Provider 错误不修复"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_error(LLMProviderError(
            "service error", provider="fake", retryable=True,
        ))
        svc = _make_svc(provider, max_repairs=1)
        with pytest.raises(DAXGenerationError):
            await svc.generate(_make_plan(), _make_schema())
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_unsafe_dax_triggers_repair(self):
        """不安全的 DAX 触发修复"""
        provider = FakeProvider(is_mock=False)
        # 首次返回包含不安全内容的 DAX
        unsafe_dax = _make_dax(dax="EVALUATE Sales -- hidden")
        provider.enqueue_success(unsafe_dax)
        # 修复后返回安全 DAX
        provider.enqueue_success(_make_dax())
        svc = _make_svc(provider, max_repairs=1)
        result = await svc.generate(_make_plan(), _make_schema())
        assert result is not None
        assert len(provider.calls) == 2


# ══════════════════════════════════════════════════════════════════
# Mock 隔离
# ══════════════════════════════════════════════════════════════════

class TestDAXMockIsolation:
    """Mock 隔离"""

    def test_mock_provider_rejected(self):
        """Mock Provider 被拒绝"""
        with pytest.raises(DAXGenerationError, match="非 Mock"):
            DeepSeekDAXService(provider=FakeProvider(is_mock=True))

    @pytest.mark.asyncio
    async def test_task_is_dax(self):
        """task 为 DAX"""
        provider = FakeProvider(is_mock=False)
        provider.enqueue_success(_make_dax())
        svc = _make_svc(provider)
        await svc.generate(_make_plan(), _make_schema())
        assert provider.calls[0].task == LLMTask.DAX

    def test_validate_safety_public_api(self):
        """validate_safety 可公开调用"""
        svc = _make_svc()
        result = svc.validate_safety(SAFE_DAX, _make_schema())
        assert result.is_valid is True


# ══════════════════════════════════════════════════════════════════
# Prompt 规则
# ══════════════════════════════════════════════════════════════════

class TestDAXPromptRules:
    """DAX Prompt 规则"""

    def test_prompt_forbids_sql(self):
        """Prompt 禁止生成 SQL"""
        messages = build_dax_messages(
            "QP summary", "schema text", "mock_sales_model", "req-1",
        )
        system = messages[0]["content"]
        assert "不得生成 SQL" in system

    def test_prompt_forbids_write(self):
        """Prompt 禁止写操作"""
        messages = build_dax_messages(
            "QP summary", "schema text", "mock_sales_model", "req-1",
        )
        system = messages[0]["content"]
        assert "不得生成写操作" in system or "INSERT" in system

    def test_prompt_requires_evaluate(self):
        """Prompt 要求 EVALUATE"""
        messages = build_dax_messages(
            "QP summary", "schema text", "mock_sales_model", "req-1",
        )
        system = messages[0]["content"]
        assert "EVALUATE" in system

    def test_prompt_forbids_answer(self):
        """Prompt 禁止生成答案"""
        messages = build_dax_messages(
            "QP summary", "schema text", "mock_sales_model", "req-1",
        )
        system = messages[0]["content"]
        assert "不得生成最终回答" in system

    def test_prompt_no_key_leak(self):
        """Prompt 不包含 Secret"""
        messages = build_dax_messages(
            "QP summary", "schema text", "mock_sales_model", "req-1",
        )
        for msg in messages:
            assert "sk-" not in msg["content"]

    def test_repair_prompt_contains_illegal_objects(self):
        """修复 Prompt 包含非法对象提示"""
        messages = build_dax_messages(
            "QP summary", "schema text", "mock_sales_model", "req-1",
            repair_error_code="dax_safety_failed",
            illegal_objects="'FakeMeasure'",
        )
        system = messages[0]["content"]
        assert "FakeMeasure" in system


# ══════════════════════════════════════════════════════════════════
# 异常脱敏
# ══════════════════════════════════════════════════════════════════

class TestDAXErrorSanitization:
    """DAX 异常脱敏"""

    def test_dax_error_no_key(self):
        """DAXGenerationError 不包含 Key"""
        e = DAXGenerationError("test")
        assert "sk-" not in str(e)

    def test_safety_result_structured(self):
        """安全验证结果结构化"""
        validator = DAXSafetyValidator()
        result = validator.validate("EVALUATE; DROP TABLE Sales")
        assert isinstance(result, DAXSafetyResult)
        assert result.is_valid is False
        assert len(result.errors) > 0
