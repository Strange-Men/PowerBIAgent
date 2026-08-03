"""LLM Provider Factory — M1.1

统一创建入口：
- Mock 模式：注册 MockLLMProvider，默认 Provider 为 mock
- DeepSeek 模式：注册 Mock + DeepSeek，默认 Provider 为 deepseek
- 不散落模式判断
- 每个 Factory 调用返回独立 Registry 实例
- 构建时不访问网络
"""

from __future__ import annotations

from typing import Optional

import httpx

from backend.app.config.settings import Settings
from backend.app.llm.base import LLMConfigurationError
from backend.app.llm.deepseek import DeepSeekLLMProvider
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.registry import LLMProviderRegistry


def build_llm_registry(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> LLMProviderRegistry:
    """构建 LLM Provider Registry

    Args:
        settings: 应用配置
        client: 可选的外部 httpx AsyncClient（用于测试注入）

    Returns:
        独立的 LLMProviderRegistry 实例

    Raises:
        LLMConfigurationError: DeepSeek 模式但 Key 缺失
    """
    registry = LLMProviderRegistry()

    # ── Mock Provider 始终注册 ──
    mock = MockLLMProvider()
    registry.register("mock", mock)  # 自动设为默认（首个注册）

    # ── DeepSeek 模式 ──
    if settings.llm_mode.value == "deepseek":
        # Key 缺失时明确失败
        if not settings.is_deepseek_configured:
            raise LLMConfigurationError(
                "DeepSeek API Key 未配置。请在 .env 中设置 DEEPSEEK_API_KEY。",
                provider="deepseek",
                retryable=False,
            )

        deepseek = DeepSeekLLMProvider(
            api_key=settings.deepseek_api_key,  # type: ignore[arg-type]
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=float(settings.request_timeout_seconds),
            client=client,
        )
        registry.register("deepseek", deepseek, set_default=True)

    return registry
