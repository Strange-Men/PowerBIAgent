"""DeepSeekAnswerService — M1.4-B 真实 Answer 生成

基于 DeepSeekLLMProvider 从 QueryPlan、QueryResult 和 Schema 生成结构化 AnswerSpec。
- 复用现有 AnswerSpec、QueryResult、QueryPlan 模型
- 生成后通过 ValidationService.validate_answer() 真实验证
- 最多一次修复（格式错误和验证错误共用配额）
- 网络/鉴权/限流/超时和 HTTP 5xx 不修复
- Service 不保存请求级可变状态，支持并发
"""

from __future__ import annotations

from typing import Optional

from backend.app.answer.context import AnswerContext
from backend.app.answer.prompt import build_answer_messages
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTask,
    LLMValidationError,
)
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    QueryPlan,
    QueryResult,
    SemanticModelSchema,
)


class AnswerGenerationError(Exception):
    """Answer 生成异常"""
    pass


# 非法字段提取上限
_MAX_ILLEGAL_FIELDS = 5


class DeepSeekAnswerService:
    """基于 DeepSeek Provider 的真实 Answer 生成服务

    构造函数：
        provider: 非 Mock LLMProvider
        max_repairs: 最大修复次数（固定 1 次）
    """

    def __init__(
        self,
        provider: LLMProvider,
        max_repairs: int = 1,
    ):
        if provider.is_mock:
            raise AnswerGenerationError(
                "DeepSeekAnswerService 要求非 Mock Provider"
            )

        self._provider = provider
        self._max_repairs = max(0, min(max_repairs, 1))

    # ── 公共 API ──

    async def generate(
        self,
        user_input: str,
        intent: IntentSpec,
        query_plan: QueryPlan,
        query_result: QueryResult,
        schema: SemanticModelSchema,
        *,
        request_id: str = "",
    ) -> AnswerSpec:
        """从 QueryPlan 和 QueryResult 生成 AnswerSpec

        Args:
            user_input: 用户原始输入
            intent: 已验证的 IntentSpec
            query_plan: 已验证的 QueryPlan
            query_result: DAX 查询结果
            schema: 语义模型 Schema
            request_id: 请求 ID

        Returns:
            AnswerSpec: 结构化回答

        Raises:
            AnswerGenerationError: 生成失败
        """
        # ── 入口边界校验（LLM 调用前拒绝） ──

        # 1. 只允许 data_question
        if intent.intent != IntentType.DATA_QUESTION:
            raise AnswerGenerationError(
                f"Answer 生成不支持 intent={intent.intent.value}，"
                f"只有 data_question 可以进入"
            )

        # 2. QueryResult.error 存在时拒绝
        if query_result.error is not None:
            raise AnswerGenerationError(
                f"QueryResult 包含错误: {query_result.error.type} - "
                f"{query_result.error.message}，拒绝生成 Answer"
            )

        # 3. 模型 Key 一致性（三向校验）
        if query_plan.semantic_model_key != schema.key:
            raise AnswerGenerationError(
                "QueryPlan.semantic_model_key 与 Schema key 不一致"
                "（query_plan_model_key_mismatch）"
            )
        if query_result.semantic_model_key != schema.key:
            raise AnswerGenerationError(
                "QueryResult.semantic_model_key 与 Schema key 不一致"
                "（query_result_model_key_mismatch）"
            )

        # 4. source_mode 合法性
        if query_result.source_mode not in ("mock", "real"):
            raise AnswerGenerationError(
                f"非法的 source_mode: '{query_result.source_mode}'"
                "（仅允许 mock/real）"
            )

        if not user_input or not user_input.strip():
            raise AnswerGenerationError("user_input 不能为空")

        # ── 构建安全上下文 ──
        context = AnswerContext.build(
            user_input=user_input,
            result_id=query_result.result_id,
            semantic_model_key=schema.key,
            columns=query_result.columns,
            rows=query_result.rows,
            row_count=query_result.row_count,
            truncated=query_result.truncated,
            source_mode=query_result.source_mode,
            measures=query_plan.measures,
            dimensions=query_plan.dimensions,
            filters_summary=self._build_filters_summary(query_plan),
            time_range=query_plan.time_range or "",
        )

        # ── 构建验证服务 ──
        validation = ValidationService()

        repair_used = False

        # ── 首次请求 ──
        try:
            answer = await self._try_generate(context)
        except LLMValidationError as e:
            error_code = getattr(e, "error_code", None) or ""
            if not self._is_format_repairable(error_code):
                raise AnswerGenerationError(
                    "Answer 生成失败（不可修复错误）"
                ) from e
            if self._max_repairs < 1:
                raise AnswerGenerationError(
                    "Answer 生成失败（格式修复已禁用）"
                ) from e
            # 格式修复
            repair_used = True
            try:
                answer = await self._try_generate(
                    context,
                    repair_error_code="invalid_content_json_or_schema",
                )
            except LLMValidationError as e:
                raise AnswerGenerationError(
                    "Answer 生成失败（格式修复后仍无效）"
                ) from e
            except LLMProviderError as e:
                raise AnswerGenerationError(
                    "Answer 生成失败（Provider 错误）"
                ) from e
            except Exception as e:
                raise AnswerGenerationError(
                    "Answer 生成失败（未知错误）"
                ) from e
        except LLMProviderError as e:
            raise AnswerGenerationError(
                "Answer 生成失败（Provider 错误）"
            ) from e
        except Exception as e:
            raise AnswerGenerationError(
                "Answer 生成失败"
            ) from e

        # ── Answer 严格验证 ──
        val_result = validation.validate_answer_strict(
            answer, query_result, input_truncated=context.input_truncated,
        )
        if not val_result.is_valid:
            if repair_used:
                raise AnswerGenerationError(
                    f"Answer 验证失败（修复后仍无效）: "
                    f"{'; '.join(val_result.errors[:3])}"
                )
            if self._max_repairs < 1:
                raise AnswerGenerationError(
                    f"Answer 验证失败（修复已禁用）: "
                    f"{'; '.join(val_result.errors[:3])}"
                )

            # ── 一次验证修复 ──
            repair_used = True
            illegal_fields = self._extract_illegal_fields(val_result)
            try:
                answer = await self._try_generate(
                    context,
                    repair_error_code="answer_validation_failed",
                    illegal_fields=illegal_fields,
                )
            except LLMValidationError as e:
                raise AnswerGenerationError(
                    "Answer 生成失败（验证修复后 JSON 仍无效）"
                ) from e
            except LLMProviderError as e:
                raise AnswerGenerationError(
                    "Answer 生成失败（Provider 错误）"
                ) from e
            except Exception as e:
                raise AnswerGenerationError(
                    "Answer 生成失败（验证修复时未知错误）"
                ) from e

            # 二次严格验证
            val_result = validation.validate_answer_strict(
                answer, query_result, input_truncated=context.input_truncated,
            )
            if not val_result.is_valid:
                raise AnswerGenerationError(
                    f"Answer 验证失败（验证修复后仍无效）: "
                    f"{'; '.join(val_result.errors[:3])}"
                )

        return answer

    # ── 内部方法 ──

    async def _try_generate(
        self,
        context: AnswerContext,
        repair_error_code: str | None = None,
        illegal_fields: str = "",
    ) -> AnswerSpec:
        """单次 Answer 生成调用"""
        messages = build_answer_messages(
            context,
            repair_error_code=repair_error_code,
            illegal_fields=illegal_fields,
        )

        request = LLMRequest(
            messages=messages,
            task=LLMTask.ANSWER,
        )

        response = await self._provider.generate(request, AnswerSpec)

        if response.structured is None:
            raise AnswerGenerationError("Provider 返回的 structured 为 None")

        return response.structured

    @staticmethod
    def _is_format_repairable(error_code: str) -> bool:
        """判断错误是否为可修复的格式错误"""
        return error_code in {"invalid_content_json", "output_schema_invalid"}

    @staticmethod
    def _build_filters_summary(query_plan: QueryPlan) -> str:
        """从 QueryPlan 构建筛选条件摘要"""
        if not query_plan.filters:
            return ""
        parts = []
        for f in query_plan.filters:
            parts.append(f"{f.field} {f.operator.value} {f.value}")
        return "; ".join(parts)

    @staticmethod
    def _extract_illegal_fields(val_result) -> str:
        """从 ValidationResult.errors 提取最多 _MAX_ILLEGAL_FIELDS 个字段名"""
        import re
        field_set: set[str] = set()
        for err in val_result.errors:
            # 提取引号中的字段名
            m = re.search(r"'([^']+)'", err)
            if m:
                field_set.add(m.group(1))
        fields = sorted(field_set)[:_MAX_ILLEGAL_FIELDS]
        return ", ".join(fields) if fields else "（未知字段）"

    # ── 属性 ──

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def max_repairs(self) -> int:
        return self._max_repairs
