"""DeepSeek LLM Provider 骨架

本轮仅创建骨架（Base URL、Model、API Key、超时、重试、错误类型、接口签名）。
真实网络调用在 M1 实现。

M0.2 所有 raise NotImplementedError 标记了 M1 的实现位置。
"""

from typing import Optional

from pydantic import BaseModel

from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMValidationError,
)


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
        self._api_key = api_key
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
    def api_key(self) -> str:
        return self._api_key

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: LLMRequest, output_type: type[BaseModel]) -> LLMResponse:
        """[骨架] 调用 DeepSeek API 生成结构化响应

        M0.2 阶段仅定义接口，M1 实现真实调用。
        """
        # TODO: M1 — 实现真实 DeepSeek 网络调用
        # 1. 构建 OpenAI-compatible messages
        # 2. 调用 httpx/requests → {base_url}/v1/chat/completions
        # 3. 解析响应为 output_type Pydantic 实例
        # 4. 校验结构化输出
        # 5. 超时和重试处理

        if not self._api_key:
            raise LLMProviderError(
                "DeepSeek API Key 未配置。M0.2 阶段请使用 Mock LLM。",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        raise NotImplementedError(
            "TODO: M1 — 实现真实 DeepSeek 网络调用。"
            "M0.2 阶段请使用 MockLLMProvider 进行测试。"
        )
