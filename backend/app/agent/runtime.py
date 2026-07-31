"""AgentRuntime — 单 Agent 架构的 Agent 运行时适配器

隔离 PydanticAI 框架依赖。业务层只依赖此抽象接口。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel


class AgentRunResult(BaseModel):
    """Agent 运行结果"""
    content: str = ""
    structured: Optional[BaseModel] = None
    finish_reason: str = "stop"
    usage: dict[str, int] = {}


class AgentRuntime(ABC):
    """Agent 运行时适配器

    封装 Agent 创建、工具注册、运行、结构化输出。
    业务层只依赖此接口，不直接 import pydantic_ai。

    M0.2 定义接口契约，M0.3 提供 MockAgentRuntime，
    M1 提供 PydanticAI 真实实现。
    """

    @abstractmethod
    async def run(
        self,
        user_input: str,
        context: dict[str, Any],
        output_type: type[BaseModel],
    ) -> AgentRunResult:
        """执行 Agent，返回结构化结果

        Args:
            user_input: 用户输入文本
            context: 组装好的上下文（来自 ContextBuilder）
            output_type: 期望的 Pydantic 输出类型

        Returns:
            AgentRunResult: 包含原始内容和结构化对象的运行结果
        """
        ...

    @abstractmethod
    def register_tool(self, tool: Any) -> None:
        """注册工具到 Agent 白名单

        Args:
            tool: 工具定义
        """
        ...

    @property
    @abstractmethod
    def registered_tools(self) -> list[str]:
        """已注册的工具名称列表"""
        ...

    @property
    @abstractmethod
    def is_mock(self) -> bool:
        """是否为 Mock 运行时"""
        ...
