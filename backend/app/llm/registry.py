"""LLM Provider Registry

统一管理所有 Provider 实例。业务层通过 Registry 获取 Provider，不散落模式判断。
"""

from typing import Optional

from backend.app.llm.base import LLMProvider


class LLMProviderRegistry:
    """LLM Provider 注册表

    用法:
        registry = LLMProviderRegistry()
        registry.register("mock", mock_provider)
        registry.register("deepseek", deepseek_provider)
        provider = registry.get()  # 使用默认 Provider
    """

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._default: Optional[str] = None

    def register(self, name: str, provider: LLMProvider, set_default: bool = False) -> None:
        """注册 Provider

        Args:
            name: Provider 名称（如 "mock", "deepseek"）
            provider: Provider 实例
            set_default: 是否设为默认
        """
        if name in self._providers:
            raise ValueError(f"Provider '{name}' already registered")
        self._providers[name] = provider
        if set_default or self._default is None:
            self._default = name

    def get(self, name: Optional[str] = None) -> LLMProvider:
        """获取 Provider

        Args:
            name: Provider 名称，为 None 时使用默认

        Returns:
            LLMProvider 实例

        Raises:
            KeyError: Provider 未注册
        """
        key = name or self._default
        if key is None:
            raise KeyError("No provider registered")
        if key not in self._providers:
            raise KeyError(f"Provider '{key}' not found. Available: {list(self._providers.keys())}")
        return self._providers[key]

    def list_providers(self) -> list[str]:
        """列出所有已注册的 Provider 名称"""
        return list(self._providers.keys())

    @property
    def default_name(self) -> Optional[str]:
        """当前默认 Provider 名称"""
        return self._default

    def set_default(self, name: str) -> None:
        """设置默认 Provider"""
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not registered")
        self._default = name
