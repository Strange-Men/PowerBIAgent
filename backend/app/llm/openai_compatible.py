"""Shared OpenAI-compatible Chat Completions provider."""

from __future__ import annotations

import json
import re

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

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
from backend.app.llm.profiles import LLMModelProfile, LLMProviderProtocol


_JSON_FENCE = re.compile(
    r"^\s*```(?:json)?\s*(\{.*\})\s*```\s*$", re.DOTALL | re.IGNORECASE
)


def classify_openai_compatible_http_error(
    status_code: int,
) -> tuple[type[LLMProviderError], bool, str]:
    mapping: dict[int, tuple[type[LLMProviderError], bool, str]] = {
        400: (LLMRequestError, False, "invalid_format"),
        401: (LLMAuthenticationError, False, "authentication_failed"),
        402: (LLMConfigurationError, False, "insufficient_balance"),
        403: (LLMAuthenticationError, False, "forbidden"),
        404: (LLMRequestError, False, "not_found"),
        422: (LLMRequestError, False, "invalid_parameters"),
        429: (LLMRateLimitError, True, "rate_limited"),
    }
    if status_code in mapping:
        return mapping[status_code]
    if 500 <= status_code < 600:
        return LLMServiceError, True, f"http_{status_code}"
    return LLMProviderError, False, f"http_{status_code}"


class OpenAICompatibleLLMProvider(LLMProvider):
    """One reusable implementation for configured Chat Completions profiles."""

    def __init__(
        self,
        *,
        profile: LLMModelProfile,
        api_key: SecretStr | str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if profile.provider_protocol != LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS:
            raise LLMConfigurationError(
                "LLM profile protocol is not OpenAI-compatible",
                provider=profile.profile_key,
                error_code="invalid_provider_protocol",
            )
        key_value = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not key_value or not key_value.strip():
            raise LLMConfigurationError(
                f"{profile.display_name} API Key 未配置",
                provider=profile.profile_key,
                error_code="api_key_missing",
            )
        self._validate_base_url(profile)
        self._profile = profile
        self._api_key = api_key if isinstance(api_key, SecretStr) else SecretStr(key_value)
        self._client = client
        self._owns_client = client is None
        self._owned_client: httpx.AsyncClient | None = None

    @staticmethod
    def _validate_base_url(profile: LLMModelProfile) -> None:
        if not profile.base_url:
            raise LLMConfigurationError(
                f"{profile.display_name} Base URL 为空",
                provider=profile.profile_key,
                error_code="invalid_base_url",
            )
        try:
            parsed = httpx.URL(profile.base_url)
        except Exception as exc:
            raise LLMConfigurationError(
                "LLM Base URL 无效",
                provider=profile.profile_key,
                error_code="invalid_base_url",
            ) from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise LLMConfigurationError(
                "LLM Base URL 无效或包含不允许的凭据/query/fragment",
                provider=profile.profile_key,
                error_code="invalid_base_url",
            )

    @property
    def profile(self) -> LLMModelProfile:
        return self._profile

    @property
    def provider_name(self) -> str:
        return self._profile.profile_key

    @property
    def is_mock(self) -> bool:
        return False

    @property
    def base_url(self) -> str:
        return self._profile.base_url

    @property
    def model(self) -> str:
        return self._profile.model

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key.get_secret_value())

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._profile.timeout_seconds)
            )
        return self._owned_client

    async def aclose(self) -> None:
        if self._owns_client and self._owned_client is not None:
            client = self._owned_client
            self._owned_client = None
            await client.aclose()

    def _build_url(self) -> str:
        return f"{self._profile.base_url}/chat/completions"

    def _validate_request(self, request: LLMRequest) -> None:
        if not request.messages:
            raise LLMRequestError(
                "messages 不能为空", provider=self.provider_name,
                error_code="messages_empty",
            )
        has_json_instruction = any(
            isinstance(message.get("content"), str)
            and any(
                keyword in message["content"].lower()
                for keyword in ("json", "json_object", "json object")
            )
            for message in request.messages
        )
        if not has_json_instruction:
            raise LLMRequestError(
                "消息中必须包含 JSON 输出要求",
                provider=self.provider_name,
                error_code="json_instruction_missing",
            )
        for message in request.messages:
            role = message.get("role", "")
            content = message.get("content", "")
            if role not in {"system", "user", "assistant"}:
                raise LLMRequestError(
                    f"非法的 message role: {role}", provider=self.provider_name,
                    error_code="invalid_message_role",
                )
            if not isinstance(content, str) or not content.strip():
                raise LLMRequestError(
                    f"message content 不能为空 (role={role})",
                    provider=self.provider_name,
                    error_code="empty_message_content",
                )

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        return [{"role": message["role"], "content": message["content"]} for message in request.messages]

    def _build_payload(self, messages: list[dict[str, str]]) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self._profile.model,
            "messages": messages,
            "stream": False,
        }
        if self._profile.capabilities.deterministic_temperature:
            payload["temperature"] = 0
        if self._profile.capabilities.json_object_response:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    async def generate(self, request: LLMRequest, output_type: type[BaseModel]) -> LLMResponse:
        self._validate_request(request)
        try:
            response = await self._get_client().post(
                self._build_url(),
                json=self._build_payload(self._build_messages(request)),
                headers=self._build_headers(),
            )
        except httpx.TimeoutException as exc:
            timeout_codes = {
                httpx.ConnectTimeout: "connect_timeout",
                httpx.ReadTimeout: "read_timeout",
                httpx.WriteTimeout: "write_timeout",
                httpx.PoolTimeout: "pool_timeout",
            }
            error_code = next(
                (code for kind, code in timeout_codes.items() if isinstance(exc, kind)),
                "timeout",
            )
            raise LLMTimeoutError(
                f"{self._profile.display_name} 请求超时",
                provider=self.provider_name,
                retryable=True,
                error_code=error_code,
            ) from exc
        except httpx.LocalProtocolError as exc:
            raise LLMRequestError(
                f"{self._profile.display_name} 本地请求协议错误",
                provider=self.provider_name,
                error_code="local_protocol_error",
            ) from exc
        except httpx.RequestError as exc:
            error_codes = {
                httpx.ConnectError: "connect_error",
                httpx.ReadError: "read_error",
                httpx.WriteError: "write_error",
                httpx.CloseError: "close_error",
                httpx.RemoteProtocolError: "remote_protocol_error",
            }
            error_code = next(
                (code for kind, code in error_codes.items() if isinstance(exc, kind)),
                "connection_error",
            )
            raise LLMConnectionError(
                f"{self._profile.display_name} 连接失败",
                provider=self.provider_name,
                retryable=True,
                error_code=error_code,
            ) from exc

        if response.status_code != 200:
            exc_type, retryable, error_code = classify_openai_compatible_http_error(response.status_code)
            raise exc_type(
                f"{self._profile.display_name} API 返回 HTTP {response.status_code}",
                provider=self.provider_name,
                retryable=retryable,
                status_code=response.status_code,
                error_code=error_code,
            )
        return self._parse_response(response, output_type)

    @staticmethod
    def _normalize_json_content(raw_content: str) -> str:
        match = _JSON_FENCE.fullmatch(raw_content)
        return match.group(1).strip() if match else raw_content.strip()

    def _parse_response(self, response: httpx.Response, output_type: type[BaseModel]) -> LLMResponse:
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMResponseError(
                f"{self._profile.display_name} 响应 Body 不是合法 JSON",
                provider=self.provider_name,
                error_code="invalid_http_json",
            ) from exc
        if not isinstance(body, dict):
            raise LLMResponseError("LLM 响应 Body 不是 JSON 对象", provider=self.provider_name, error_code="invalid_response_body")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseError("LLM 响应 choices 缺失或为空", provider=self.provider_name, error_code="invalid_choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise LLMResponseError("LLM 响应 choice 非法", provider=self.provider_name, error_code="invalid_choice")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise LLMResponseError("LLM 响应 message 非法", provider=self.provider_name, error_code="invalid_message")
        raw_content = message.get("content")
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise LLMResponseError("LLM 响应 content 为空", provider=self.provider_name, error_code="empty_content")
        finish_reason = choice.get("finish_reason", "stop")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise LLMResponseError("LLM 响应 finish_reason 类型非法", provider=self.provider_name, error_code="invalid_finish_reason")
        response_model = body.get("model", self._profile.model)
        if not isinstance(response_model, str) or not response_model.strip():
            raise LLMResponseError("LLM 响应 model 非法", provider=self.provider_name, error_code="invalid_model")
        usage_data = body.get("usage", {})
        if not isinstance(usage_data, dict):
            raise LLMResponseError("LLM 响应 usage 类型非法", provider=self.provider_name, error_code="invalid_usage")
        usage: dict[str, int] = {}
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage_data.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LLMResponseError(f"LLM 响应 {field} 类型非法", provider=self.provider_name, error_code="invalid_token_usage")
            usage[field] = value
        safe_finish = finish_reason or "stop"
        try:
            parsed = json.loads(self._normalize_json_content(raw_content))
        except json.JSONDecodeError as exc:
            raise LLMValidationError(
                "LLM 响应 content 不是合法 JSON", provider=self.provider_name,
                error_code="invalid_content_json", usage=usage,
                model=response_model, finish_reason=safe_finish,
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMValidationError(
                "LLM 响应 content JSON 不是对象", provider=self.provider_name,
                error_code="invalid_content_json", usage=usage,
                model=response_model, finish_reason=safe_finish,
            )
        try:
            structured = output_type.model_validate(parsed)
        except ValidationError as exc:
            raise LLMValidationError(
                f"LLM 响应不符合 {output_type.__name__}", provider=self.provider_name,
                error_code="output_schema_invalid", usage=usage,
                model=response_model, finish_reason=safe_finish,
            ) from exc
        return LLMResponse(
            content=raw_content,
            structured=structured,
            model=response_model,
            usage=usage,
            finish_reason=safe_finish,
        )

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleLLMProvider("
            f"profile_key={self.provider_name!r}, model={self.model!r}, "
            f"has_api_key={self.has_api_key})"
        )
