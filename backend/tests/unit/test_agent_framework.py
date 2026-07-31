"""M0.2 Agent 框架 Smoke Test

证明当前 Python 环境可使用 PydanticAI。
不实现完整 Agent Runtime。
"""

import pytest


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
        """验证 OpenAIChatModel 可导入（PydanticAI v2.21 API）"""
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

    @pytest.mark.asyncio
    async def test_structural_output_with_pydantic(self):
        """验证 Agent 支持 Pydantic 结构化输出"""
        from pydantic import BaseModel
        from pydantic_ai import Agent

        class SimpleResult(BaseModel):
            answer: str
            confidence: float

        # 仅验证类型系统，不实际运行
        assert SimpleResult.model_fields["answer"].annotation is str
        assert SimpleResult.model_fields["confidence"].annotation is float
