"""DeepSeek LLM Provider 骨架

通过 OpenAI-compatible API 接入 DeepSeek。
M0.2 仅骨架，M1 实现真实网络调用。

安全要求：
- API Key 使用 SecretStr 封装，不可通过属性直接读取原文
- repr 和日志不暴露 Key
- Trace 不得记录 Key
- 未配置 Key 时抛出明确配置异常
"""

from typing import Optional

from pydantic import BaseModel, SecretStr

from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
)


class DeepSeekConfigError(LLMProviderError):
    """DeepSeek 配置异常 — API Key 未设置等"""
    pass


class DeepSeekProvider(LLMProvider):
    """DeepSeek LLM Provider

    通过 OpenAI-compatible API 接入 DeepSeek。
    M0.2 仅骨架，M1 实现真实网络调用。
    """

    PROVIDER_NAME = "deepseek"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        if not api_key:
            raise DeepSeekConfigError(
                "DeepSeek API Key 未配置。"
                "M0.2 阶段请使用 MockLLMProvider 进行测试。",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )
        self._api_key = SecretStr(api_key)
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def is_mock(self) -> bool:
        return False

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    @property
    def has_api_key(self) -> bool:
        """检查是否已配置 API Key（不暴露原文）"""
        key = self._api_key.get_secret_value() if self._api_key else ""
        return bool(key)

    def _get_api_key(self) -> str:
        """内部获取 API Key 原文 — 仅用于构建 HTTP 请求"""
        return self._api_key.get_secret_value()

    async def generate(self, request: LLMRequest, output_type: type[BaseModel]) -> LLMResponse:
        """[骨架] 调用 DeepSeek API 生成结构化响应

        M0.2 阶段仅定义接口，M1 实现真实调用。
        """
        # TODO: M1 — 实现真实 DeepSeek 网络调用
        # 1. 构建 OpenAI-compatible messages
        # 2. 调用 httpx → {base_url}/v1/chat/completions
        # 3. 解析响应为 output_type Pydantic 实例
        # 4. 校验结构化输出
        # 5. 超时和重试处理

        raise NotImplementedError(
            "TODO: M1 — 实现真实 DeepSeek 网络调用。"
            "M0.2/M0.3 阶段请使用 MockLLMProvider 进行测试。"
        )

    def __repr__(self) -> str:
        return (
            f"DeepSeekProvider(model={self._model}, "
            f"base_url={self._base_url}, "
            f"has_api_key={self.has_api_key})"
        )
