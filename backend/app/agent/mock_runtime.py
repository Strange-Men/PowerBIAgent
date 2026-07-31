"""MockAgentRuntime — 实现 AgentRuntime 接口的 Mock 运行时

使用 MockLLMProvider，根据 task 和 scenario_key 返回预设结果。
不调用网络，不调用 PowerBIAdapter，不绕过 ToolGateway。
"""

from typing import Any, Optional

from pydantic import BaseModel

from backend.app.agent.runtime import AgentRunResult, AgentRuntime
from backend.app.llm.base import LLMRequest, LLMTask
from backend.app.llm.mock import MockLLMProvider


class MockAgentRuntime(AgentRuntime):
    """Mock Agent 运行时

    使用 MockLLMProvider 返回预设结构化结果。
    未知场景明确失败。
    """

    def __init__(self, llm_provider: Optional[MockLLMProvider] = None):
        self._llm = llm_provider or MockLLMProvider()
        self._tools: dict[str, Any] = {}
        self._scenario_key: Optional[str] = None

    def set_scenario(self, scenario_key: str) -> None:
        """设置 Mock 场景"""
        self._scenario_key = scenario_key

    async def run(
        self,
        user_input: str,
        context: dict[str, Any],
        output_type: type[BaseModel],
    ) -> AgentRunResult:
        """执行 Mock Agent"""
        # 根据 output_type 推断 task
        task = LLMTask.INTENT_RECOGNITION
        type_name = output_type.__name__.lower()
        if "queryplan" in type_name:
            task = LLMTask.QUERY_PLAN
        elif "dax" in type_name.lower():
            task = LLMTask.DAX
        elif "answer" in type_name:
            task = LLMTask.ANSWER
        elif "report" in type_name:
            task = LLMTask.REPORT

        request = LLMRequest(
            messages=[{"role": "user", "content": user_input}],
            task=task,
            scenario_key=self._scenario_key or "data_question",
        )

        response = await self._llm.generate(request, output_type)
        return AgentRunResult(
            content=response.content,
            structured=response.structured,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )

    def register_tool(self, tool: Any) -> None:
        """注册工具"""
        name = getattr(tool, "name", str(id(tool)))
        self._tools[name] = tool

    @property
    def registered_tools(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def is_mock(self) -> bool:
        return True
