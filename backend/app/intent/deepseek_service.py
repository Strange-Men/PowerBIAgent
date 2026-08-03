"""DeepSeekIntentService — M1.2 真实意图识别服务

基于 DeepSeekLLMProvider 实现 IntentService 接口。
- 复用现有 Provider，禁止绕过或自行构造 HTTP 客户端
- 真实模式绝不调用 MockScenarioResolver，也不回退 Mock
- 最多一次格式修复（JSON 或 Schema 错误）
- Provider.is_mock=True 时明确失败
- Service 不保存请求级可变状态，支持并发调用
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.app.intent.context import IntentContextSnapshot
from backend.app.intent.models import IntentSpec
from backend.app.intent.prompt import build_intent_messages
from backend.app.intent.service import IntentRecognitionError, IntentService
from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTask,
    LLMValidationError,
)


class DeepSeekIntentService(IntentService):
    """基于 DeepSeek Provider 的真实意图识别服务

    构造函数：
        provider: 非 Mock LLMProvider（is_mock=True 时明确失败）
        max_format_repairs: 最大格式修复次数（默认 1 次）
    """

    def __init__(
        self,
        provider: LLMProvider,
        max_format_repairs: int = 1,
    ):
        if provider.is_mock:
            raise IntentRecognitionError(
                "DeepSeekIntentService 要求非 Mock Provider，"
                f"但收到 is_mock=True 的 Provider: {provider.provider_name}"
            )

        self._provider = provider
        self._max_format_repairs = max(0, min(max_format_repairs, 1))

    # ── 公共 API ──

    async def recognize(
        self,
        user_input: str,
        committed_memory: Optional[Mapping[str, Any]] = None,
        *,
        semantic_model_key: Optional[str] = None,
        report_template_key: Optional[str] = None,
    ) -> IntentSpec:
        """识别用户意图

        Args:
            user_input: 用户原始输入文本
            committed_memory: 已提交的 committed memory（可选）
            semantic_model_key: 语义模型 Key（关键字参数）
            report_template_key: 报表模板 Key（关键字参数）

        Returns:
            IntentSpec: 结构化意图识别结果

        Raises:
            IntentRecognitionError: 意图识别失败
        """
        if not user_input or not user_input.strip():
            raise IntentRecognitionError("user_input 不能为空")

        # 1. 构建安全上下文快照（白名单提取）
        context = IntentContextSnapshot.from_committed_memory(
            committed_memory,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
        )

        # 2. 首次请求
        attempts = 1
        try:
            return await self._try_recognize(user_input, context, repair_error_code=None)
        except LLMValidationError as e:
            error_code = getattr(e, "error_code", None) or ""
            # 只有 JSON 或 Schema 错误才允许修复
            if not self._is_repairable(error_code):
                raise IntentRecognitionError(
                    f"意图识别失败（不可修复错误）: {e}",
                ) from e
            if self._max_format_repairs < 1:
                raise IntentRecognitionError(
                    f"意图识别失败（格式修复已禁用）: {e}",
                ) from e
        except LLMProviderError as e:
            # 网络、鉴权、限流等不可修复错误直接传播
            raise IntentRecognitionError(
                f"意图识别失败（Provider 错误，不可修复, retryable={e.retryable}）",
            ) from e
        except Exception as e:
            raise IntentRecognitionError(
                f"意图识别失败: {type(e).__name__}",
            ) from e

        # 3. 一次格式修复
        attempts = 2
        try:
            return await self._try_recognize(
                user_input, context,
                repair_error_code="invalid_content_json_or_schema",
            )
        except LLMValidationError as e:
            error_code = getattr(e, "error_code", "") or ""
            raise IntentRecognitionError(
                f"意图识别失败（格式修复后仍无效, error_code={error_code}）",
            ) from e
        except LLMProviderError as e:
            raise IntentRecognitionError(
                f"意图识别失败（Provider 错误, retryable={e.retryable}）",
            ) from e
        except Exception as e:
            raise IntentRecognitionError(
                f"意图识别失败（未知错误）: {type(e).__name__}",
            ) from e

    # ── 内部方法 ──

    async def _try_recognize(
        self,
        user_input: str,
        context: IntentContextSnapshot,
        repair_error_code: Optional[str] = None,
    ) -> IntentSpec:
        """单次意图识别调用"""
        messages = build_intent_messages(
            user_input=user_input,
            context=context,
            repair_error_code=repair_error_code,
        )

        request = LLMRequest(
            messages=messages,
            task=LLMTask.INTENT_RECOGNITION,
            scenario_key=None,  # 真实模式绝不使用 Scenario Key
        )

        response = await self._provider.generate(request, IntentSpec)

        if response.structured is None:
            raise IntentRecognitionError("Provider 返回的 structured 为 None")

        return response.structured

    @staticmethod
    def _is_repairable(error_code: str) -> bool:
        """判断错误是否允许格式修复。

        只允许 JSON 解析失败或 Schema 验证失败的输出内容错误。
        网络、鉴权、限流、超时等不可修复。
        """
        repairable_codes = {
            "invalid_content_json",
            "output_schema_invalid",
        }
        return error_code in repairable_codes

    # ── 属性 ──

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def max_format_repairs(self) -> int:
        return self._max_format_repairs
