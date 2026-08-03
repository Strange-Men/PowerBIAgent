"""意图识别服务接口

本轮 (M0.2) 仅定义服务边界。真实意图识别由 LLM Provider + Prompt 完成。
"""

from abc import ABC, abstractmethod
from typing import Optional

from backend.app.intent.models import IntentSpec


class IntentService(ABC):
    """意图识别服务抽象接口

    M0.2 定义契约，M1 结合真实 LLM 实现。
    当前 Mock LLM 可返回预设 IntentSpec。
    """

    @abstractmethod
    async def recognize(
        self,
        user_input: str,
        committed_memory: Optional[dict] = None,
        *,
        semantic_model_key: Optional[str] = None,
        report_template_key: Optional[str] = None,
    ) -> IntentSpec:
        """识别用户意图

        Args:
            user_input: 用户原始输入文本
            committed_memory: 已提交的 committed structured memory（可选）
            semantic_model_key: 语义模型 Key（关键字参数，M1.2）
            report_template_key: 报表模板 Key（关键字参数，M1.2）

        Returns:
            IntentSpec: 结构化意图识别结果

        Raises:
            IntentRecognitionError: 意图识别失败
        """
        ...


class IntentRecognitionError(Exception):
    """意图识别异常"""
    pass
