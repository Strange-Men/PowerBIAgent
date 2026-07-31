"""Agent 编排层 — 单 Agent 架构的 AgentRuntime Adapter

本轮 (M0.2) 仅定义接口骨架，不实现完整 Agent Runtime。
AgentRuntime 封装 PydanticAI，隔离框架依赖。
"""

from abc import ABC, abstractmethod
from typing import Any

# AgentRuntime 接口将在 M0.3 实质性实现时定义。
# 本轮仅确认：
# - 业务层不直接依赖 PydanticAI
# - Agent 创建、工具注册、运行、结构化输出均通过此 Adapter
"""
class AgentRuntime(ABC):
    '''Agent 运行时适配器，隔离具体 Agent 框架'''

    @abstractmethod
    async def run(self, user_input: str, context: dict[str, Any]) -> Any:
        '''执行 Agent，返回结构化结果'''
        ...

    @abstractmethod
    def register_tool(self, tool: Any) -> None:
        '''注册工具到 Agent 白名单'''
        ...
"""
