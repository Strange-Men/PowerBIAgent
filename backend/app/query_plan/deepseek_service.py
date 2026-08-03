"""DeepSeekQueryPlanService — M1.3 真实 QueryPlan 生成

基于 DeepSeekLLMProvider 从已验证的 IntentSpec 和 Schema 生成结构化 QueryPlan。
- 复用现有 QueryPlan、IntentSpec、SemanticModelSchema 模型
- 复用现有 ValidationService.validate_query_plan()
- 最多一次格式修复（仅 JSON/Schema 错误可修复）
- Service 不保存请求级可变状态，支持并发
"""

from __future__ import annotations

from typing import Optional

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


class DeepSeekQueryPlanService:
    """基于 DeepSeek Provider 的真实 QueryPlan 生成服务

    构造函数：
        provider: 非 Mock LLMProvider
        max_format_repairs: 最大格式修复次数（默认 1 次）
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

        effective_model_key = semantic_model_key or schema.key

        # 1. 构建 Schema 安全视图
        schema_view = build_schema_view(schema)
        schema_text = render_schema_text(schema_view)

        # 2. 构建安全上下文快照
        context = IntentContextSnapshot.from_committed_memory(
            committed_memory,
            semantic_model_key=effective_model_key,
            report_template_key=report_template_key,
        )

        # 3. 首次请求
        try:
            return await self._try_generate(
                user_input, intent, schema_text, context, repair_error_code=None,
            )
        except LLMValidationError as e:
            error_code = getattr(e, "error_code", None) or ""
            if not self._is_repairable(error_code):
                raise QueryPlanError(
                    "QueryPlan 生成失败（不可修复错误）"
                ) from e
            if self._max_format_repairs < 1:
                raise QueryPlanError(
                    "QueryPlan 生成失败（格式修复已禁用）"
                ) from e
        except LLMProviderError as e:
            raise QueryPlanError(
                "QueryPlan 生成失败（Provider 错误）"
            ) from e
        except Exception as e:
            raise QueryPlanError(
                "QueryPlan 生成失败"
            ) from e

        # 4. 一次格式修复
        try:
            return await self._try_generate(
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

    # ── 内部方法 ──

    async def _try_generate(
        self,
        user_input: str,
        intent: IntentSpec,
        schema_text: str,
        context: IntentContextSnapshot,
        repair_error_code: Optional[str] = None,
    ) -> QueryPlan:
        """单次 QueryPlan 生成调用"""
        messages = build_query_plan_messages(
            user_input=user_input,
            intent_type=intent.intent.value,
            schema_text=schema_text,
            context=context,
            repair_error_code=repair_error_code,
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
    def _is_repairable(error_code: str) -> bool:
        """判断错误是否允许格式修复"""
        return error_code in {"invalid_content_json", "output_schema_invalid"}

    # ── 属性 ──

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def max_format_repairs(self) -> int:
        return self._max_format_repairs
