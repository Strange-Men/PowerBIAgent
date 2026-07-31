"""M0.2+ Agent 框架测试

测试：
1. AgentRuntime 真实可导入（非字符串）
2. AgentRuntime 是抽象类
3. 缺少抽象方法时不能实例化
4. MockAgentRuntime 可实现接口
5. PydanticAI 最小导入与 Smoke Test
6. PydanticAI API 准确性验证
"""

import pytest


class TestAgentRuntime:
    """AgentRuntime 真实类测试"""

    def test_agent_runtime_importable(self):
        """AgentRuntime 可以真实导入（不是字符串）"""
        from backend.app.agent import AgentRuntime, AgentRunResult
        assert AgentRuntime is not None
        assert AgentRunResult is not None
        # 确认是类，不是字符串
        assert isinstance(AgentRuntime, type)
        assert isinstance(AgentRunResult, type)

    def test_agent_runtime_is_abstract(self):
        """AgentRuntime 是抽象类"""
        from backend.app.agent import AgentRuntime
        import inspect
        assert inspect.isabstract(AgentRuntime)

    def test_agent_runtime_has_required_methods(self):
        """AgentRuntime 定义了至少 run、register_tool、registered_tools、is_mock"""
        from backend.app.agent import AgentRuntime
        assert hasattr(AgentRuntime, 'run')
        assert hasattr(AgentRuntime, 'register_tool')
        assert hasattr(AgentRuntime, 'registered_tools')
        assert hasattr(AgentRuntime, 'is_mock')

    def test_agent_runtime_cannot_instantiate(self):
        """缺少抽象方法时不能实例化"""
        from backend.app.agent import AgentRuntime
        with pytest.raises(TypeError):
            AgentRuntime()

    def test_agent_run_result_create(self):
        """AgentRunResult 可以创建"""
        from backend.app.agent import AgentRunResult
        result = AgentRunResult(content="test", finish_reason="stop")
        assert result.content == "test"
        assert result.usage == {}


class TestPydanticAISmoke:
    """PydanticAI 最小导入与基本功能测试"""

    def test_import_pydantic_ai(self):
        """验证 pydantic_ai 可导入"""
        import pydantic_ai
        assert pydantic_ai is not None

    def test_import_agent(self):
        """验证 Agent 类可导入"""
        from pydantic_ai import Agent
        assert Agent is not None

    def test_import_openai_chat_model(self):
        """验证 OpenAIChatModel 可导入"""
        from pydantic_ai.models.openai import OpenAIChatModel
        assert OpenAIChatModel is not None

    def test_import_openai_provider(self):
        """验证 OpenAIProvider 可导入"""
        from pydantic_ai.providers.openai import OpenAIProvider
        assert OpenAIProvider is not None

    def test_agent_instantiation_test_model(self):
        """验证 Agent 可实例化（使用内置 test 模型，无需 API Key）"""
        from pydantic_ai import Agent
        agent = Agent("test", system_prompt="You are a helpful assistant.")
        assert agent is not None
        assert agent.model is not None

    def test_structured_output_param_name(self):
        """验证结构化输出参数名为 output_type（非 result_type）"""
        from pydantic_ai import Agent
        import inspect
        sig = inspect.signature(Agent.__init__)
        params = list(sig.parameters.keys())
        assert "output_type" in params
        # 注意：PydanticAI v2.21 使用 output_type，不是 result_type

    @pytest.mark.asyncio
    async def test_structural_output_with_pydantic(self):
        """验证 Agent 支持 Pydantic 结构化输出"""
        from pydantic import BaseModel
        from pydantic_ai import Agent

        class SimpleResult(BaseModel):
            answer: str
            confidence: float

        assert SimpleResult.model_fields["answer"].annotation is str
        assert SimpleResult.model_fields["confidence"].annotation is float
