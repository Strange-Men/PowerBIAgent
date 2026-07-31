"""MockAgentRuntime — 实现 AgentRuntime 接口的 Mock 运行时

M0.3.3 修复：
- 彻底删除 set_scenario() 和所有共享 Scenario 状态
- scenario_key 仅通过 run() 的 context["mock_scenario_key"] 传入
- 同一 Runtime 实例并发执行不同 Scenario 不会串场
"""

from typing import Any, Optional

from pydantic import BaseModel

from backend.app.agent.runtime import AgentRunResult, AgentRuntime
from backend.app.llm.base import LLMRequest, LLMTask
from backend.app.llm.mock import MockLLMProvider


class MockAgentRuntime(AgentRuntime):
    """Mock Agent 运行时

    使用 MockLLMProvider 返回预设结构化结果。
    scenario_key 通过 context dict 传入，不保存在任何实例字段。
    未知场景明确失败。
    """

    def __init__(self, llm_provider: Optional[MockLLMProvider] = None):
        self._llm = llm_provider or MockLLMProvider()
        self._tools: dict[str, Any] = {}

    async def run(
        self,
        user_input: str,
        context: dict[str, Any],
        output_type: type[BaseModel],
    ) -> AgentRunResult:
        """执行 Mock Agent — scenario_key 只从本次调用的 context 读取"""
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

        # M0.3.3: scenario_key 仅从当前调用的局部 context 读取，不使用任何共享状态
        scenario_key = context.get("mock_scenario_key", "data_question")

        request = LLMRequest(
            messages=[{"role": "user", "content": user_input}],
            task=task,
            scenario_key=scenario_key,
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
