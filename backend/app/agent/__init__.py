"""Agent 编排层 — 单 Agent 架构的 AgentRuntime Adapter

AgentRuntime 封装 PydanticAI，隔离框架依赖。
业务层只依赖 AgentRuntime 抽象接口，不直接 import pydantic_ai。
"""

from backend.app.agent.runtime import AgentRunResult, AgentRuntime

__all__ = ["AgentRuntime", "AgentRunResult"]
