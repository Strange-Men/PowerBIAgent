"""DeepSeekQueryPlanService — M1.3.1 真实 QueryPlan 生成

基于 DeepSeekLLMProvider 从已验证的 IntentSpec 和 Schema 生成结构化 QueryPlan。
- 复用现有 QueryPlan、IntentSpec、SemanticModelSchema 模型
- 生成后通过 ValidationService.validate_query_plan() 真实验证
- 最多一次修复（覆盖格式错误和 Schema 验证错误）
- 网络/鉴权/限流/超时和 HTTP 5xx 不修复
- Service 不保存请求级可变状态，支持并发
"""

from __future__ import annotations

from typing import Optional

from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.context import IntentContextSnapshot
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTask,
    LLMValidationError,
)
from backend.app.query_plan.context import build_schema_view, render_schema_text
from backend.app.query_plan.prompt import build_query_plan_messages
from backend.app.schemas.data_contracts import QueryPlan, SemanticModelSchema


class QueryPlanError(Exception):
    """QueryPlan 生成异常"""
    pass


# ── 验证错误代码映射 ──

_VALIDATION_ERROR_MAP: dict[str, str] = {
    "allowed list": "query_plan_model_mismatch",
    "not found in schema": "query_plan_measure_not_found",
    "not found in schema columns": "query_plan_dimension_not_found",
    "Filter field": "query_plan_filter_not_found",
}

# 验证错误中非法对象名提取上限
_MAX_ILLEGAL_OBJECTS = 5


class DeepSeekQueryPlanService:
    """基于 DeepSeek Provider 的真实 QueryPlan 生成服务

    构造函数：
        provider: 非 Mock LLMProvider
        max_format_repairs: 最大修复次数（固定 1 次）
    """

    def __init__(
        self,
        provider: LLMProvider,
        max_format_repairs: int = 1,
    ):
        if provider.is_mock:
            raise QueryPlanError(
                "DeepSeekQueryPlanService 要求非 Mock Provider"
            )

        self._provider = provider
        self._max_format_repairs = max(0, min(max_format_repairs, 1))

    # ── 公共 API ──

    async def generate(
        self,
        user_input: str,
        intent: IntentSpec,
        schema: SemanticModelSchema,
        *,
        committed_memory: Optional[dict] = None,
        semantic_model_key: Optional[str] = None,
        report_template_key: Optional[str] = None,
        enforce_semantic_grounding: bool = False,
    ) -> QueryPlan:
        """从 IntentSpec 和 Schema 生成 QueryPlan

        Args:
            user_input: 用户原始输入
            intent: 已验证的 IntentSpec
            schema: SemanticModelSchema
            committed_memory: 已提交的 committed memory（可选）
            semantic_model_key: 语义模型 Key
            report_template_key: 报表模板 Key

        Returns:
            QueryPlan: 结构化查询计划

        Raises:
            QueryPlanError: 生成失败
        """
        # ── 入口边界：只允许 data_question 和 report_generation ──
        if intent.intent not in (IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION):
            raise QueryPlanError(
                f"QueryPlan 不支持 intent={intent.intent.value}，"
                f"clarification 和 unsupported 必须在进入 QueryPlan 前明确拒绝"
            )

        if not user_input or not user_input.strip():
            raise QueryPlanError("user_input 不能为空")

        # ── 模型 Key 权威性校验：传入值与 schema.key 不一致时拒绝 ──
        if semantic_model_key is not None and semantic_model_key != schema.key:
            raise QueryPlanError(
                "semantic_model_key 与 Schema key 不一致，拒绝执行"
                "（query_plan_model_key_mismatch）"
            )

        effective_model_key = semantic_model_key or schema.key

        # 0. 构建当前 Schema 专用 ValidationService
        validation = ValidationService(allowed_semantic_models=[effective_model_key])

        # 1. 构建 Schema 安全视图
        schema_view = build_schema_view(schema)
        schema_text = render_schema_text(schema_view)

        # 2. 构建安全上下文快照
        context = IntentContextSnapshot.from_committed_memory(
            committed_memory,
            semantic_model_key=effective_model_key,
            report_template_key=report_template_key,
        )

        repair_used = False

        # 3. 首次请求
        try:
            plan = await self._try_generate(
                user_input, intent, schema_text, context,
            )
        except LLMValidationError as e:
            error_code = getattr(e, "error_code", None) or ""
            if not self._is_format_repairable(error_code):
                raise QueryPlanError(
                    "QueryPlan 生成失败（不可修复错误）"
                ) from e
            if self._max_format_repairs < 1:
                raise QueryPlanError(
                    "QueryPlan 生成失败（格式修复已禁用）"
                ) from e
            # 格式修复
            repair_used = True
            try:
                plan = await self._try_generate(
                    user_input, intent, schema_text, context,
                    repair_error_code="invalid_content_json_or_schema",
                )
            except LLMValidationError as e:
                raise QueryPlanError(
                    "QueryPlan 生成失败（格式修复后仍无效）"
                ) from e
            except LLMProviderError as e:
                raise QueryPlanError(
                    "QueryPlan 生成失败（Provider 错误）"
                ) from e
            except Exception as e:
                raise QueryPlanError(
                    "QueryPlan 生成失败（未知错误）"
                ) from e
        except LLMProviderError as e:
            raise QueryPlanError(
                "QueryPlan 生成失败（Provider 错误）"
            ) from e
        except Exception as e:
            raise QueryPlanError(
                "QueryPlan 生成失败"
            ) from e

        # 4. Schema 验证（首次生成或格式修复后）
        val_result = validation.validate_query_plan(
            plan,
            schema,
            enforce_semantic_grounding=enforce_semantic_grounding,
        )
        if not val_result.is_valid:
            if repair_used:
                raise QueryPlanError(
                    f"QueryPlan 验证失败（修复后仍无效）: {'; '.join(val_result.errors[:3])}"
                )
            if self._max_format_repairs < 1:
                raise QueryPlanError(
                    f"QueryPlan 验证失败（修复已禁用）: {'; '.join(val_result.errors[:3])}"
                )

            # ── 一次验证修复 ──
            repair_used = True
            error_code, illegal_objects = self._build_validation_error_summary(val_result)
            try:
                plan = await self._try_generate(
                    user_input, intent, schema_text, context,
                    repair_error_code=error_code,
                    validation_errors=illegal_objects,
                )
            except LLMValidationError as e:
                raise QueryPlanError(
                    "QueryPlan 生成失败（验证修复后 JSON 仍无效）"
                ) from e
            except LLMProviderError as e:
                raise QueryPlanError(
                    "QueryPlan 生成失败（Provider 错误）"
                ) from e
            except Exception as e:
                raise QueryPlanError(
                    "QueryPlan 生成失败（验证修复时未知错误）"
                ) from e

            # 二次验证
            val_result = validation.validate_query_plan(
                plan,
                schema,
                enforce_semantic_grounding=enforce_semantic_grounding,
            )
            if not val_result.is_valid:
                raise QueryPlanError(
                    f"QueryPlan 验证失败（验证修复后仍无效）: {'; '.join(val_result.errors[:3])}"
                )

        return plan

    # ── 内部方法 ──

    async def _try_generate(
        self,
        user_input: str,
        intent: IntentSpec,
        schema_text: str,
        context: IntentContextSnapshot,
        repair_error_code: Optional[str] = None,
        validation_errors: str = "",
    ) -> QueryPlan:
        """单次 QueryPlan 生成调用"""
        messages = build_query_plan_messages(
            user_input=user_input,
            intent_type=intent.intent.value,
            schema_text=schema_text,
            context=context,
            repair_error_code=repair_error_code,
            validation_errors=validation_errors,
        )

        request = LLMRequest(
            messages=messages,
            task=LLMTask.QUERY_PLAN,
        )

        response = await self._provider.generate(request, QueryPlan)

        if response.structured is None:
            raise QueryPlanError("Provider 返回的 structured 为 None")

        return response.structured

    @staticmethod
    def _is_format_repairable(error_code: str) -> bool:
        """判断错误是否为可修复的格式错误"""
        return error_code in {"invalid_content_json", "output_schema_invalid"}

    @staticmethod
    def _build_validation_error_summary(val_result) -> tuple[str, str]:
        """从 ValidationResult.errors 提取安全错误摘要

        Returns:
            (error_code, illegal_objects_str): 错误代码和最多5个非法对象名
        """
        errors = val_result.errors
        error_code = "query_plan_validation_failed"

        # 收集非法对象名
        import re

        illegal_set: set[str] = set()
        for err in errors:
            if err.startswith("query_plan_"):
                error_code = err.split(":", 1)[0]
                quoted = re.search(r"'([^']+)'", err)
                if quoted:
                    illegal_set.add(quoted.group(1))
                continue
            # "Model 'X' not in allowed list"
            m = re.search(r"Model '([^']+)'", err)
            if m:
                error_code = "query_plan_model_mismatch"
                illegal_set.add(m.group(1))
                continue
            # "Measure/column 'X' not found"
            m = re.search(r"(?:Measure|column) '([^']+)' not found", err)
            if m:
                if error_code == "query_plan_validation_failed":
                    error_code = "query_plan_measure_not_found"
                illegal_set.add(m.group(1))
                continue
            # "Dimension 'X' not found"
            m = re.search(r"Dimension '([^']+)' not found", err)
            if m:
                if error_code == "query_plan_validation_failed":
                    error_code = "query_plan_dimension_not_found"
                illegal_set.add(m.group(1))
                continue
            # "Filter field 'X' not found"
            m = re.search(r"Filter field '([^']+)' not found", err)
            if m:
                if error_code == "query_plan_validation_failed":
                    error_code = "query_plan_filter_not_found"
                illegal_set.add(m.group(1))
                continue
            # "query_plan_template_not_allowed"
            if "query_plan_template_not_allowed" in err:
                error_code = "query_plan_template_not_allowed"
                continue

        illegal_list = sorted(illegal_set)[:_MAX_ILLEGAL_OBJECTS]
        illegal_objects = ", ".join(illegal_list) if illegal_list else "（未知对象）"

        return error_code, illegal_objects

    # ── 属性 ──

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def max_format_repairs(self) -> int:
        return self._max_format_repairs
