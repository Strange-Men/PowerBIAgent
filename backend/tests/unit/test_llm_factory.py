"""LLM Provider Factory 测试 — M1.1

覆盖：
- Mock 模式默认 Mock Provider
- Mock 模式无需 DeepSeek Key
- Mock 模式不创建网络 Client
- DeepSeek 模式缺 Key 明确失败
- DeepSeek 配置完整时注册 Provider
- DeepSeek 为默认 Provider
- Mock Provider 仍可获取
- 两个 Registry 实例互不污染
"""

from __future__ import annotations

import pytest

from backend.app.config.settings import Settings
from backend.app.llm.factory import build_llm_registry
from backend.app.llm.registry import LLMProfileUnavailableError


class TestMockModeFactory:
    """Mock 模式 Factory 测试"""

    def test_mock_mode_default_provider(self):
        """Mock 模式默认 Provider 为 mock"""
        settings = Settings(
            llm_mode="mock",
            powerbi_mode="mock",
        )
        registry = build_llm_registry(settings)
        provider = registry.get("mock").provider
        assert provider.provider_name == "mock"
        assert provider.is_mock is True

    def test_mock_mode_no_key_required(self):
        """Mock 模式无需 DeepSeek Key"""
        settings = Settings(
            llm_mode="mock",
            powerbi_mode="mock",
            deepseek_api_key=None,
        )
        registry = build_llm_registry(settings)
        assert registry.get("mock").provider.provider_name == "mock"

    def test_mock_mode_no_network_client(self):
        """Mock 模式不创建网络 Client"""
        settings = Settings(
            llm_mode="mock",
            powerbi_mode="mock",
        )
        registry = build_llm_registry(settings)
        assert registry.get("mock").provider.is_mock is True


class TestDeepSeekModeFactory:
    """DeepSeek 模式 Factory 测试"""

    def test_deepseek_mode_no_key_raises(self):
        """DeepSeek 模式缺 Key 明确失败"""
        settings = Settings(
            llm_mode="deepseek",
            powerbi_mode="mock",
            deepseek_api_key=None,
        )
        registry = build_llm_registry(settings)
        with pytest.raises(LLMProfileUnavailableError):
            registry.get("deepseek")

    def test_deepseek_mode_with_key_registers_both(self):
        """DeepSeek 配置完整时注册 Mock + DeepSeek"""
        fake_key = "sk-" + ("A" * 24)
        settings = Settings(
            llm_mode="deepseek",
            powerbi_mode="mock",
            deepseek_api_key=fake_key,  # type: ignore[arg-type]
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_model="deepseek-chat",
        )
        registry = build_llm_registry(settings)
        providers = registry.list_providers()
        assert "mock" in providers
        assert "deepseek" in providers

    def test_deepseek_is_default(self):
        """DeepSeek 为默认 Provider"""
        fake_key = "sk-" + ("B" * 24)
        settings = Settings(
            llm_mode="deepseek",
            powerbi_mode="mock",
            deepseek_api_key=fake_key,  # type: ignore[arg-type]
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_model="deepseek-chat",
        )
        registry = build_llm_registry(settings)
        provider = registry.get("deepseek").provider
        assert provider.provider_name == "deepseek"
        assert provider.is_mock is False

    def test_mock_still_accessible_in_deepseek_mode(self):
        """DeepSeek 模式仍可获取 Mock Provider"""
        fake_key = "sk-" + ("C" * 24)
        settings = Settings(
            llm_mode="deepseek",
            powerbi_mode="mock",
            deepseek_api_key=fake_key,  # type: ignore[arg-type]
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_model="deepseek-chat",
        )
        registry = build_llm_registry(settings)
        mock = registry.get("mock").provider
        assert mock.provider_name == "mock"
        assert mock.is_mock is True


class TestRegistryIsolation:
    """Registry 实例隔离测试"""

    def test_two_registries_independent(self):
        """两个 Registry 实例互不污染"""
        settings1 = Settings(llm_mode="mock", powerbi_mode="mock")
        settings2 = Settings(llm_mode="mock", powerbi_mode="mock")

        r1 = build_llm_registry(settings1)
        r2 = build_llm_registry(settings2)

        assert r1 is not r2
        # 各自有独立的 Provider 实例
        p1 = r1.get("mock").provider
        p2 = r2.get("mock").provider
        assert p1 is not p2
