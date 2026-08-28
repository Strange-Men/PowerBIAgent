"""TurnServiceProtocol — 轮次服务抽象协议

Application 层通过此协议调用，不依赖具体实现。
MockTurnService 和 DeepSeekTurnService 均遵循此协议。
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class TurnServiceProtocol(Protocol):
    """轮次服务协议

    定义 Turn 执行的标准接口。
    MockTurnService 和 DeepSeekTurnService 均遵循此协议。
    """

    async def execute(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        report_template_key: Optional[str] = None,
        llm_profile_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行完整 Turn 流程

        Args:
            message: 用户自然语言消息
            conversation_id: 会话 ID（None 时服务端生成）
            request_id: 请求 ID（None 时服务端生成）
            semantic_model_key: 语义模型标识
            report_template_key: 报表模板标识
            llm_profile_key: 本轮显式选择的公开 LLM profile key

        Returns:
            统一结果字典，包含 request_id, conversation_id, terminal_state,
            intent, response_type, answer/report/clarification/unsupported 等字段。

        Raises:
            IdempotencyConflictError: request_id 冲突
            IdempotencyCoordinationError: Owner/Waiter 协调失败
        """
        ...
