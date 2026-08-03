"""DeepSeek LLM Provider — M1.1 真实实现

通过 OpenAI-compatible API 接入 DeepSeek。
支持可独立调用、可测试、错误可分类。

安全要求：
- API Key 使用 SecretStr 封装，repr 不暴露
- Authorization Header 不输出到日志/Trace
- 不输出完整 Prompt/响应
- 未配置 Key 时抛出明确配置异常
"""

import json
from typing import Optional

import httpx
from pydantic import BaseModel, SecretStr

from backend.app.llm.base import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMRequestError,
    LLMResponse,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    LLMValidationError,
)

# ---------------------------------------------------------------------------
# 错误分类映射
# ---------------------------------------------------------------------------


def _classify_http_error(
    status_code: int,
    provider: str,
) -> tuple[type[LLMProviderError], bool]:
    """根据 HTTP 状态码返回 (异常类型, retryable)"""
    mapping: dict[int, tuple[type[LLMProviderError], bool]] = {
        400: (LLMRequestError, False),
        401: (LLMAuthenticationError, False),
        403: (LLMAuthenticationError, False),
        404: (LLMRequestError, False),
        422: (LLMRequestError, False),
        429: (LLMRateLimitError, True),
    }
    if status_code in mapping:
        exc_type, retryable = mapping[status_code]
        return exc_type, retryable
    if 500 <= status_code < 600:
        return LLMServiceError, True
    return LLMProviderError, False


# ---------------------------------------------------------------------------
# DeepSeekLLMProvider
# ---------------------------------------------------------------------------


class DeepSeekLLMProvider(LLMProvider):
    """DeepSeek LLM Provider — M1.1 真实实现

    通过 OpenAI-compatible API 接入 DeepSeek。
    构造时不访问网络。Provider 不编写业务 Prompt。
    """

    PROVIDER_NAME = "deepseek"

    def __init__(
        self,
        api_key: SecretStr | str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ):
        # ── 参数校验 ──
        if isinstance(api_key, SecretStr):
            key_value = api_key.get_secret_value()
        else:
            key_value = api_key

        if not key_value or not key_value.strip():
            raise LLMConfigurationError(
                "DeepSeek API Key 未配置",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        base_url = base_url.strip()
        if not base_url:
            raise LLMConfigurationError(
                "DeepSeek Base URL 为空",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        model = model.strip()
        if not model:
            raise LLMConfigurationError(
                "DeepSeek Model 为空",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        # ── 存储 ──
        self._api_key = SecretStr(key_value) if isinstance(api_key, str) else api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = float(timeout_seconds)
        self._client = client  # 外部注入的 Client（不由我们关闭）
        self._owns_client = client is None

    # ── 属性 ──

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
        key = self._api_key.get_secret_value()
        return bool(key)

    # ── Client 管理 ──

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx AsyncClient"""
        if self._client is not None:
            return self._client
        if not hasattr(self, "_owned_client") or self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds),
            )
        return self._owned_client

    async def aclose(self) -> None:
        """关闭自建 Client（可重复调用）"""
        if self._owns_client and hasattr(self, "_owned_client") and self._owned_client is not None:
            client = self._owned_client
            self._owned_client = None
            await client.aclose()

    # ── 构造 URL ──

    def _build_url(self) -> str:
        """构造请求 URL：<base_url>/chat/completions（不产生重复 //）"""
        return f"{self._base_url}/chat/completions"

    # ── 生成 ──

    async def generate(
        self,
        request: LLMRequest,
        output_type: type[BaseModel],
    ) -> LLMResponse:
        """调用 DeepSeek API 生成结构化响应

        错误映射：
        - Key 缺失 → LLMConfigurationError (retryable=false)
        - Base URL/Model 为空 → LLMConfigurationError (retryable=false)
        - messages 非法 → LLMRequestError (retryable=false)
        - HTTP 400/404/422 → LLMRequestError (retryable=false)
        - HTTP 401/403 → LLMAuthenticationError (retryable=false)
        - HTTP 429 → LLMRateLimitError (retryable=true)
        - ConnectError/DNS → LLMConnectionError (retryable=true)
        - Timeout → LLMTimeoutError (retryable=true)
        - HTTP 5xx → LLMServiceError (retryable=true)
        - Body 非法 JSON → LLMResponseError (retryable=false)
        - choices/message/content 缺失 → LLMResponseError (retryable=false)
        - content 非法 JSON → LLMValidationError (retryable=false)
        - content 不符合 output_type → LLMValidationError (retryable=false)

        本轮不自动重试。不自动去除 Markdown 代码块。不自动修复 JSON。
        """
        self._validate_request(request)

        messages = self._build_messages(request)
        payload = self._build_payload(messages)
        headers = self._build_headers()

        url = self._build_url()
        client = self._get_client()

        # ── 发送请求 ──
        try:
            http_response = await client.post(
                url,
                json=payload,
                headers=headers,
            )
        except httpx.TimeoutException:
            raise LLMTimeoutError(
                f"DeepSeek 请求超时 ({self._timeout_seconds}s)",
                provider=self.PROVIDER_NAME,
                retryable=True,
            )
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"DeepSeek 连接失败: {e}",
                provider=self.PROVIDER_NAME,
                retryable=True,
                error_code="connect_error",
            )
        except httpx.ReadError as e:
            raise LLMConnectionError(
                f"DeepSeek 读取响应失败: {e}",
                provider=self.PROVIDER_NAME,
                retryable=True,
                error_code="read_error",
            )
        except httpx.WriteError as e:
            raise LLMConnectionError(
                f"DeepSeek 发送请求失败: {e}",
                provider=self.PROVIDER_NAME,
                retryable=True,
                error_code="write_error",
            )
        except httpx.CloseError as e:
            raise LLMConnectionError(
                f"DeepSeek 连接关闭: {e}",
                provider=self.PROVIDER_NAME,
                retryable=True,
                error_code="close_error",
            )
        except httpx.RemoteProtocolError as e:
            raise LLMConnectionError(
                f"DeepSeek 远端协议错误: {e}",
                provider=self.PROVIDER_NAME,
                retryable=True,
                error_code="remote_protocol_error",
            )
        except httpx.LocalProtocolError as e:
            raise LLMRequestError(
                f"DeepSeek 本地请求协议错误: {e}",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="local_protocol_error",
            )

        # ── 解析 HTTP 状态码 ──
        if http_response.status_code != 200:
            exc_type, retryable = _classify_http_error(
                http_response.status_code, self.PROVIDER_NAME
            )
            raise exc_type(
                f"DeepSeek API 返回 HTTP {http_response.status_code}",
                provider=self.PROVIDER_NAME,
                retryable=retryable,
                status_code=http_response.status_code,
            )

        # ── 解析响应 Body ──
        return self._parse_response(http_response, output_type)

    # ── 请求校验 ──

    def _validate_request(self, request: LLMRequest) -> None:
        """校验 LLMRequest 合法性"""
        if not request.messages:
            raise LLMRequestError(
                "messages 不能为空",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        # 检查是否要求 JSON 输出
        has_json_instruction = False
        for msg in request.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                if any(
                    keyword in content.lower()
                    for keyword in ["json", "json_object", "json object"]
                ):
                    has_json_instruction = True
                    break

        if not has_json_instruction:
            raise LLMRequestError(
                "消息中必须包含 JSON 输出要求",
                provider=self.PROVIDER_NAME,
                retryable=False,
            )

        # 校验 role 和 content
        for msg in request.messages:
            role = msg.get("role", "")
            if role not in ("system", "user", "assistant"):
                raise LLMRequestError(
                    f"非法的 message role: {role}",
                    provider=self.PROVIDER_NAME,
                    retryable=False,
                )
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.strip():
                raise LLMRequestError(
                    f"message content 不能为空 (role={role})",
                    provider=self.PROVIDER_NAME,
                    retryable=False,
                )

    # ── 请求构造 ──

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        """构造发送给 DeepSeek 的消息列表

        scenario_key 和 metadata 不发送。
        """
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in request.messages
        ]

    def _build_payload(self, messages: list[dict[str, str]]) -> dict:
        """构造请求 Body"""
        return {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    def _build_headers(self) -> dict[str, str]:
        """构造 HTTP Headers（含 Authorization）

        注意：返回的 Header 不得输出到日志/Trace。
        """
        return {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    # ── 响应解析 ──

    def _parse_response(
        self,
        http_response: httpx.Response,
        output_type: type[BaseModel],
    ) -> LLMResponse:
        """解析 DeepSeek HTTP 响应为 LLMResponse

        严格验证响应结构的每一层，任何结构异常转为 LLMResponseError，
        不泄漏为 AttributeError/TypeError/KeyError/IndexError。
        """

        # 1. HTTP Body 必须是合法 JSON，且必须是 dict
        try:
            body = http_response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise LLMResponseError(
                f"DeepSeek 响应 Body 不是合法 JSON: {e}",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_http_json",
            )
        if not isinstance(body, dict):
            raise LLMResponseError(
                "DeepSeek 响应 Body 不是 JSON 对象",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_response_body",
            )

        # 2. choices 必须是非空 list
        choices = body.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            raise LLMResponseError(
                "DeepSeek 响应 choices 缺失或为空",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_choices",
            )

        # 3. choices[0] 必须是 dict
        choice = choices[0]
        if not isinstance(choice, dict):
            raise LLMResponseError(
                "DeepSeek 响应 choices[0] 不是对象",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_choice",
            )

        # 4. message 必须是 dict
        message = choice.get("message")
        if not isinstance(message, dict):
            raise LLMResponseError(
                "DeepSeek 响应 message 缺失或不是对象",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_message",
            )

        # 5. content 必须是非空字符串
        raw_content = message.get("content", "")
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise LLMResponseError(
                "DeepSeek 响应 content 为空",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="empty_content",
            )

        # 6. finish_reason 缺失时使用 stop，存在时必须为字符串
        finish_reason = choice.get("finish_reason", "stop")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise LLMResponseError(
                f"DeepSeek 响应 finish_reason 类型非法: {type(finish_reason).__name__}",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_finish_reason",
            )

        # 7. model 缺失时使用配置模型，存在时必须为非空字符串
        response_model = body.get("model", self._model)
        if response_model is not None and (not isinstance(response_model, str) or not response_model.strip()):
            raise LLMResponseError(
                "DeepSeek 响应 model 非法",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_model",
            )

        # 8. usage 缺失时使用全零，存在时必须是 dict
        usage_data = body.get("usage", {})
        if usage_data is not None and not isinstance(usage_data, dict):
            raise LLMResponseError(
                f"DeepSeek 响应 usage 类型非法: {type(usage_data).__name__}",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_usage",
            )

        # 9. 三个 Token 字段必须是非负整数，bool 不得作为合法 Token 整数
        usage: dict[str, int] = {}
        for token_field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            token_val = usage_data.get(token_field, 0) if isinstance(usage_data, dict) else 0
            if isinstance(token_val, bool) or not isinstance(token_val, int) or token_val < 0:
                raise LLMResponseError(
                    f"DeepSeek 响应 {token_field} 类型非法",
                    provider=self.PROVIDER_NAME,
                    retryable=False,
                    error_code="invalid_token_usage",
                )
            usage[token_field] = int(token_val)

        # 10. content 执行 json.loads() 后必须是 JSON 对象
        try:
            parsed_content = json.loads(raw_content)
        except json.JSONDecodeError as e:
            raise LLMValidationError(
                f"DeepSeek 响应 content 不是合法 JSON: {e}",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_content_json",
            )
        if not isinstance(parsed_content, dict):
            raise LLMValidationError(
                "DeepSeek 响应 content JSON 不是对象",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="invalid_content_json",
            )

        # 11. 使用 output_type.model_validate()
        try:
            structured = output_type.model_validate(parsed_content)
        except Exception as e:
            raise LLMValidationError(
                f"DeepSeek 响应不符合 {output_type.__name__}: {e}",
                provider=self.PROVIDER_NAME,
                retryable=False,
                error_code="output_schema_invalid",
            )

        return LLMResponse(
            content=raw_content,
            structured=structured,
            model=str(response_model) if response_model else self._model,
            usage=usage,
            finish_reason=str(finish_reason) if finish_reason else "stop",
        )

    # ── 安全 repr ──

    def __repr__(self) -> str:
        return (
            f"DeepSeekLLMProvider(model={self._model}, "
            f"base_url={self._base_url}, "
            f"has_api_key={self.has_api_key})"
        )
