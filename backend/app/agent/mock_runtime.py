"""MockAgentRuntime — 实现 AgentRuntime 接口的 Mock 运行时

M0.3.2 修复：
- 移除共享 _scenario_key 实例字段
- scenario_key 通过 run() 的 context 参数传入
- 每个 Turn 独立，无并发串场风险
"""

from typing import Any, Optional

from pydantic import BaseModel

from backend.app.agent.runtime import AgentRunResult, AgentRuntime
from backend.app.llm.base import LLMRequest, LLMTask
from backend.app.llm.mock import MockLLMProvider


class MockAgentRuntime(AgentRuntime):
    """Mock Agent 运行时

    使用 MockLLMProvider 返回预设结构化结果。
    scenario_key 通过 context dict 传入，不保存在实例字段。
    未知场景明确失败。
    """

    def __init__(self, llm_provider: Optional[MockLLMProvider] = None):
        self._llm = llm_provider or MockLLMProvider()
        self._tools: dict[str, Any] = {}

    def set_scenario(self, scenario_key: str) -> None:
        """设置当前 Turn 的 scenario_key — 立即消费，不作为持久状态

        M0.3.2：内部缓存到 _llm 的单次请求级别。
        不保存在 Runtime 实例字段中。
        """
        # 通过 LLM Provider 的临时方式传递 scenario
        self._llm._active_scenario = scenario_key

    async def run(
        self,
        user_input: str,
        context: dict[str, Any],
        output_type: type[BaseModel],
    ) -> AgentRunResult:
        """执行 Mock Agent — scenario_key 来自 _llm 内部已缓存的值"""
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

        # scenario_key 由 set_scenario 已设置到 _llm._active_scenario
        scenario = getattr(self._llm, "_active_scenario", "data_question")

        request = LLMRequest(
            messages=[{"role": "user", "content": user_input}],
            task=task,
            scenario_key=scenario,
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
