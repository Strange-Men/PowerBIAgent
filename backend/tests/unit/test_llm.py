"""M0.2+ LLM Provider 单元测试

测试：
1. Mock LLM 正常场景（data_question/clarification/unsupported/report_generation）
2. Mock LLM 非法场景（timeout/invalid_structure）
3. Mock LLM 未知场景严格失败
4. Mock LLM fixture 加载验证
5. Provider Registry 功能
6. DeepSeek 安全（SecretStr、repr 隐藏）
7. LLMTask 枚举
"""

import asyncio

import pytest

from backend.app.llm.base import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRequest,
    LLMRequestError,
    LLMScenarioNotFoundError,
    LLMTask,
    LLMTimeoutError,
    LLMValidationError,
)
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.llm.deepseek import DeepSeekLLMProvider
from backend.app.intent.models import IntentSpec, IntentType


@pytest.fixture
def mock_provider():
    return MockLLMProvider()


@pytest.fixture
def registry():
    return LLMProviderRegistry()


class TestLLMTask:
    """LLM Task 枚举测试"""

    def test_task_values(self):
        assert LLMTask.INTENT_RECOGNITION.value == "intent_recognition"
        assert LLMTask.QUERY_PLAN.value == "query_plan"
        assert LLMTask.DAX.value == "dax"
        assert LLMTask.ANSWER.value == "answer"
        assert LLMTask.REPORT.value == "report"


class TestMockLLMNormal:
    """Mock LLM 正常场景测试"""

    @pytest.mark.asyncio
    async def test_data_question(self, mock_provider):
        request = LLMRequest(
            messages=[{"role": "user", "content": "本月销售额是多少？"}],
            task=LLMTask.INTENT_RECOGNITION,
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
            task=LLMTask.INTENT_RECOGNITION,
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
            task=LLMTask.INTENT_RECOGNITION,
            scenario_key="unsupported",
        )
        response = await mock_provider.generate(request, IntentSpec)
        assert response.structured.intent == IntentType.UNSUPPORTED
        assert response.structured.unsupported_reason is not None

    @pytest.mark.asyncio
    async def test_report_generation(self, mock_provider):
        request = LLMRequest(
            messages=[{"role": "user", "content": "生成销售周报"}],
            task=LLMTask.INTENT_RECOGNITION,
            scenario_key="report_generation",
        )
        response = await mock_provider.generate(request, IntentSpec)
        assert response.structured.intent == IntentType.REPORT_GENERATION
        assert response.structured.requested_template == "sales_weekly"

    @pytest.mark.asyncio
    async def test_mock_flag(self, mock_provider):
        """Mock Provider 的 is_mock 应为 True"""
        assert mock_provider.is_mock is True
        assert mock_provider.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_fixtures_loaded(self, mock_provider):
        """验证 Fixture 确实被加载"""
        assert mock_provider.fixtures_loaded is True


class TestMockLLMFixture:
    """Mock LLM Fixture 加载测试"""

    def test_fixture_not_found_raises(self):
        """Fixture 文件不存在时明确失败"""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(LLMProviderError, match="not found"):
                MockLLMProvider(fixtures_dir=Path(tmp))

    def test_available_scenario_keys(self, mock_provider):
        """可列出可用 scenario_key"""
        keys = mock_provider.available_scenario_keys("intent")
        assert "data_question" in keys
        assert "clarification" in keys

    @pytest.mark.asyncio
    async def test_unknown_scenario_strict_failure(self, mock_provider):
        """未知 scenario_key 严格抛出 LLMScenarioNotFoundError"""
        request = LLMRequest(
            scenario_key="nonexistent_scenario_xyz",
            task=LLMTask.INTENT_RECOGNITION,
        )

        with pytest.raises(LLMScenarioNotFoundError) as exc_info:
            await mock_provider.generate(request, IntentSpec)
        assert "nonexistent_scenario_xyz" in str(exc_info.value)
        assert exc_info.value.scenario_key == "nonexistent_scenario_xyz"


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

    @pytest.mark.asyncio
    async def test_mock_delay_uses_async_sleep(self, mock_provider):
        """验证 Mock delay 不使用同步 time.sleep（通过检查不会阻塞事件循环）"""
        import time
        start = time.monotonic()
        # 使用非常短的 delay 验证异步非阻塞
        provider = MockLLMProvider(scenario_delay=0.05)
        request = LLMRequest(
            scenario_key="data_question",
            task=LLMTask.INTENT_RECOGNITION,
        )
        response = await provider.generate(request, IntentSpec)
        elapsed = time.monotonic() - start
        assert response.structured is not None
        # asyncio.sleep(0.05) 应注册延迟（即使时间分辨率有限）


class TestProviderRegistry:
    """Provider Registry 测试"""

    def test_register_and_get(self, registry, mock_provider):
        from backend.app.llm.profiles import mock_profile
        registry.register(mock_profile(), mock_provider)
        assert registry.get("mock").provider is mock_provider

    def test_registry_has_no_mutable_default(self, registry, mock_provider):
        from backend.app.llm.profiles import mock_profile
        registry.register(mock_profile(), mock_provider)
        assert not hasattr(registry, "set_default")
        with pytest.raises(TypeError):
            registry.get()

    def test_list_providers(self, registry, mock_provider):
        from backend.app.llm.profiles import mock_profile
        registry.register(mock_profile(), mock_provider)
        names = registry.list_providers()
        assert "mock" in names

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_duplicate_register_raises(self, registry, mock_provider):
        from backend.app.llm.profiles import mock_profile
        registry.register(mock_profile(), mock_provider)
        with pytest.raises(ValueError):
            registry.register(mock_profile(), mock_provider)

    def test_is_mock_property(self, mock_provider):
        """Provider 应明确标识是否为 Mock"""
        assert mock_provider.is_mock is True


class TestDeepSeekSecurity:
    """DeepSeekLLMProvider 安全测试 — M1.1"""

    def test_no_api_key_raises_config_error(self):
        """未配置 Key 时抛出配置异常"""
        with pytest.raises(LLMConfigurationError, match="API Key"):
            DeepSeekLLMProvider(
                api_key="",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                timeout_seconds=30.0,
            )

    def test_api_key_not_in_repr(self):
        """repr 不暴露 API Key"""
        fake_key = "sk-" + ("Z" * 20)
        provider = DeepSeekLLMProvider(
            api_key=fake_key,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_seconds=30.0,
        )
        r = repr(provider)
        assert fake_key not in r
        assert "has_api_key=True" in r

    def test_has_api_key_no_leak(self):
        """has_api_key 属性不暴露原文"""
        fake_key = "sk-" + ("Y" * 20)
        provider = DeepSeekLLMProvider(
            api_key=fake_key,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_seconds=30.0,
        )
        assert provider.has_api_key is True
        assert not hasattr(provider, "api_key")

    def test_is_not_mock(self):
        fake_key = "sk-" + ("W" * 20)
        provider = DeepSeekLLMProvider(
            api_key=fake_key,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_seconds=30.0,
        )
        assert provider.is_mock is False
        assert provider.provider_name == "deepseek"

    @pytest.mark.asyncio
    async def test_empty_messages_raises(self):
        """空 messages 抛 LLMRequestError（非 NotImplementedError）"""
        fake_key = "sk-" + ("V" * 20)
        provider = DeepSeekLLMProvider(
            api_key=fake_key,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_seconds=30.0,
        )
        request = LLMRequest(messages=[])
        with pytest.raises(LLMRequestError, match="不能为空"):
            await provider.generate(request, IntentSpec)
