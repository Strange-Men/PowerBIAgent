"""M0.2 LLM Provider 单元测试

测试：
4. Mock LLM 正常 data_question
5. Mock LLM clarification
6. Mock LLM unsupported
7. Mock LLM 非法场景
8. Provider Registry 选择
"""

import pytest

from backend.app.llm.base import LLMRequest, LLMTimeoutError, LLMValidationError
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.intent.models import IntentSpec, IntentType


@pytest.fixture
def mock_provider():
    return MockLLMProvider()


@pytest.fixture
def registry():
    return LLMProviderRegistry()


class TestMockLLMNormal:
    """Mock LLM 正常场景测试"""

    @pytest.mark.asyncio
    async def test_data_question(self, mock_provider):
        request = LLMRequest(
            messages=[{"role": "user", "content": "本月销售额是多少？"}],
            task="intent_recognition",
            scenario_key="data_question",
        )
        response = await mock_provider.generate(request, IntentSpec)
        assert response.structured is not None
        assert response.structured.intent == IntentType.DATA_QUESTION
        assert response.structured.confidence == 0.95

    @pytest.mark.asyncio
    async def test_clarification(self, mock_provider):
        request = LLMRequest(
            messages=[{"role": "user", "content": "帮我看看数据"}],
            scenario_key="clarification",
        )
        response = await mock_provider.generate(request, IntentSpec)
        assert response.structured.intent == IntentType.CLARIFICATION
        assert response.structured.needs_clarification is True
        assert response.structured.clarification_question is not None

    @pytest.mark.asyncio
    async def test_unsupported(self, mock_provider):
        request = LLMRequest(
            messages=[{"role": "user", "content": "删除所有数据"}],
            scenario_key="unsupported",
        )
        response = await mock_provider.generate(request, IntentSpec)
        assert response.structured.intent == IntentType.UNSUPPORTED
        assert response.structured.unsupported_reason is not None

    @pytest.mark.asyncio
    async def test_report_generation(self, mock_provider):
        request = LLMRequest(
            messages=[{"role": "user", "content": "生成销售周报"}],
            scenario_key="report_generation",
        )
        response = await mock_provider.generate(request, IntentSpec)
        assert response.structured.intent == IntentType.REPORT_GENERATION
        assert response.structured.requested_template == "销售周报模板"

    @pytest.mark.asyncio
    async def test_default_fallback(self, mock_provider):
        """未知 scenario_key 应 fallback 到 data_question"""
        request = LLMRequest(
            messages=[{"role": "user", "content": "hello"}],
            scenario_key="nonexistent",
        )
        response = await mock_provider.generate(request, IntentSpec)
        assert response.structured.intent == IntentType.DATA_QUESTION

    @pytest.mark.asyncio
    async def test_mock_flag(self, mock_provider):
        """Mock Provider 的 is_mock 应为 True"""
        assert mock_provider.is_mock is True
        assert mock_provider.provider_name == "mock"


class TestMockLLMInvalid:
    """Mock LLM 非法场景测试"""

    @pytest.mark.asyncio
    async def test_timeout_scenario(self, mock_provider):
        request = LLMRequest(scenario_key="timeout")
        with pytest.raises(LLMTimeoutError):
            await mock_provider.generate(request, IntentSpec)

    @pytest.mark.asyncio
    async def test_invalid_structure(self, mock_provider):
        request = LLMRequest(scenario_key="invalid_structure")
        with pytest.raises(LLMValidationError):
            await mock_provider.generate(request, IntentSpec)


class TestProviderRegistry:
    """Provider Registry 测试"""

    def test_register_and_get(self, registry, mock_provider):
        registry.register("mock", mock_provider)
        assert registry.get("mock") is mock_provider

    def test_default_provider(self, registry, mock_provider):
        registry.register("mock", mock_provider)
        assert registry.get() is mock_provider  # 自动设为默认

    def test_set_default(self, registry, mock_provider):
        registry.register("mock", mock_provider)
        registry.register("mock2", MockLLMProvider())
        registry.set_default("mock2")
        assert registry.default_name == "mock2"
        assert registry.get() is not mock_provider

    def test_list_providers(self, registry, mock_provider):
        registry.register("mock", mock_provider)
        registry.register("deepseek", mock_provider)  # 用 mock 占位测试
        names = registry.list_providers()
        assert "mock" in names
        assert "deepseek" in names

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_duplicate_register_raises(self, registry, mock_provider):
        registry.register("mock", mock_provider)
        with pytest.raises(ValueError):
            registry.register("mock", mock_provider)

    def test_is_mock_property(self, mock_provider):
        """Provider 应明确标识是否为 Mock"""
        assert mock_provider.is_mock is True
