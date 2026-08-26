"""LLM Provider 抽象基类

所有 LLM Provider 必须实现此接口。
Provider 支持多种 task：意图识别、QueryPlan、DAX、AnswerSpec、ReportSpec。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class LLMTask(str, Enum):
    """LLM 任务类型枚举 — 避免任意字符串拼写错误"""
    INTENT_RECOGNITION = "intent_recognition"
    SEMANTIC_SELECTION = "semantic_selection"
    DISPLAY_TRANSLATION = "display_translation"
    QUERY_PLAN = "query_plan"
    DAX = "dax"
    ANSWER = "answer"
    REPORT = "report"
    # M3.4: 受控报表规划 weak-signal 草稿。LLM 只输出 registry-owned
    # section ID；与 factual authority（DAX/ReportData/Report factual）
    # 分开计数，绝不计入事实类 LLM 调用。
    REPORT_INTENT = "report_intent"


@dataclass
class LLMRequest:
    """统一的 LLM 请求结构"""

    messages: list[dict[str, str]] = field(default_factory=list)
    task: LLMTask = LLMTask.INTENT_RECOGNITION
    scenario_key: Optional[str] = None  # Mock 场景选择键
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """统一的 LLM 响应结构"""

    content: str
    structured: Optional[BaseModel] = None  # 已解析的 Pydantic 对象
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


class LLMProvider(ABC):
    """LLM Provider 抽象基类

    所有 Provider（Mock、DeepSeek、未来的其他模型）必须实现此接口。
    业务层不得散落 if mode == "deepseek" 等分支，Provider 选择统一由 Registry 完成。
    """

    @abstractmethod
    async def generate(self, request: LLMRequest, output_type: type[BaseModel]) -> LLMResponse:
        """生成结构化响应

        Args:
            request: 统一的 LLM 请求
            output_type: 期望的 Pydantic 输出类型

        Returns:
            LLMResponse: 包含原始内容和结构化对象的响应

        Raises:
            LLMProviderError: Provider 调用失败
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称"""
        ...

    @property
    @abstractmethod
    def is_mock(self) -> bool:
        """是否为 Mock Provider"""
        ...


class LLMProviderError(Exception):
    """LLM Provider 通用异常"""

    def __init__(
        self,
        message: str,
        provider: str = "",
        retryable: bool = False,
        status_code: int | None = None,
        error_code: str | None = None,
        usage: dict[str, int] | None = None,
        model: str | None = None,
        finish_reason: str | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code
        self.error_code = error_code
        self.usage = usage
        self.model = model
        self.finish_reason = finish_reason


class LLMConfigurationError(LLMProviderError):
    """LLM 配置错误 — Key 缺失、Base URL 为空、Model 为空等"""
    pass


class LLMAuthenticationError(LLMProviderError):
    """LLM 鉴权失败 — HTTP 401/403"""
    pass


class LLMRateLimitError(LLMProviderError):
    """LLM 限流 — HTTP 429"""
    pass


class LLMConnectionError(LLMProviderError):
    """LLM 连接错误 — ConnectError/DNS"""
    pass


class LLMRequestError(LLMProviderError):
    """LLM 请求错误 — HTTP 400/404/422、messages 非法等"""
    pass


class LLMServiceError(LLMProviderError):
    """LLM 服务端错误 — HTTP 5xx"""
    pass


class LLMResponseError(LLMProviderError):
    """LLM 响应解析错误 — HTTP Body 非法 JSON、choices 缺失等"""
    pass


class LLMTimeoutError(LLMProviderError):
    """LLM 调用超时"""
    pass


class LLMValidationError(LLMProviderError):
    """LLM 输出校验失败 — 可携带安全 usage/model/finish_reason"""

    def __init__(
        self,
        message: str,
        provider: str = "",
        retryable: bool = False,
        status_code: int | None = None,
        error_code: str | None = None,
        usage: dict[str, int] | None = None,
        model: str | None = None,
        finish_reason: str | None = None,
    ):
        super().__init__(
            message,
            provider=provider,
            retryable=retryable,
            status_code=status_code,
            error_code=error_code,
            usage=usage,
            model=model,
            finish_reason=finish_reason,
        )


class LLMScenarioNotFoundError(LLMProviderError):
    """Mock 场景未找到 — 未知 scenario_key 时抛出"""

    def __init__(self, scenario_key: str, available_keys: list[str], provider: str = ""):
        self.scenario_key = scenario_key
        self.available_keys = available_keys
        msg = (
            f"Mock scenario '{scenario_key}' not found. "
            f"Available keys: {available_keys}"
        )
        super().__init__(msg, provider=provider, retryable=False)
