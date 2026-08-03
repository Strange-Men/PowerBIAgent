"""DeepSeekLLMProvider 离线测试 — M1.1

使用 httpx.MockTransport 完成全部离线测试。
绝对禁止访问互联网。

覆盖：
- 构造阶段无网络
- URL 拼接正确
- 错误分类完整
- 响应解析正确
- Secret 防泄漏
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel, Field

from backend.app.llm.base import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMRequestError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    LLMValidationError,
)
from backend.app.llm.deepseek import DeepSeekLLMProvider


# ── 测试辅助 ──

class _TestModel(BaseModel):
    """简单测试用 Pydantic 模型"""
    status: str
    value: int


def _build_json_response(data: dict | None = None, model: str = "deepseek-chat",
                          finish_reason: str = "stop",
                          prompt_tokens: int = 10,
                          completion_tokens: int = 5) -> httpx.Response:
    """构造成功的 JSON 响应"""
    body = {
        "id": "test-id",
        "object": "chat.completion",
        "created": 1234567890,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps(data or {"status": "ok", "value": 42}),
            },
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return httpx.Response(200, json=body)


def _build_error_response(status_code: int, error_msg: str = "error") -> httpx.Response:
    """构造错误响应"""
    return httpx.Response(status_code, json={"error": {"message": error_msg}})


def _json_messages() -> list[dict[str, str]]:
    """构造包含 JSON 输出要求的消息"""
    return [
        {
            "role": "user",
            "content": 'Return JSON object: {"status":"ok","value":42}',
        },
    ]


def _build_provider(
    api_key: str = "sk-test-key-for-unit-tests",
    base_url: str = "https://api.deepseek.com/v1",
    model: str = "deepseek-chat",
    timeout: float = 30.0,
    transport: httpx.MockTransport | None = None,
) -> DeepSeekLLMProvider:
    """构造带 MockTransport 的 Provider"""
    client = httpx.AsyncClient(transport=transport) if transport else None
    return DeepSeekLLMProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout,
        client=client,
    )


# ══════════════════════════════════════════════════════════════════
# 构造测试
# ══════════════════════════════════════════════════════════════════

class TestConstructor:
    """Provider 构造测试"""

    def test_provider_name(self):
        """provider_name 正确"""
        p = _build_provider()
        assert p.provider_name == "deepseek"

    def test_is_mock_false(self):
        """is_mock 为 False"""
        p = _build_provider()
        assert p.is_mock is False

    def test_no_network_on_construct(self):
        """构造阶段无网络访问"""
        # 没有 client 注入，构造只做校验和存储
        p = DeepSeekLLMProvider(
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_seconds=30.0,
        )
        assert p.provider_name == "deepseek"

    def test_key_empty_raises(self):
        """Key 为空时抛 LLMConfigurationError"""
        with pytest.raises(LLMConfigurationError, match="API Key"):
            DeepSeekLLMProvider(
                api_key="",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                timeout_seconds=30.0,
            )

    def test_key_whitespace_raises(self):
        """Key 为空白时抛 LLMConfigurationError"""
        with pytest.raises(LLMConfigurationError, match="API Key"):
            DeepSeekLLMProvider(
                api_key="   ",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                timeout_seconds=30.0,
            )

    def test_base_url_empty_raises(self):
        """Base URL 为空时抛 LLMConfigurationError"""
        with pytest.raises(LLMConfigurationError, match="Base URL"):
            DeepSeekLLMProvider(
                api_key="sk-test",
                base_url="",
                model="deepseek-chat",
                timeout_seconds=30.0,
            )

    def test_base_url_whitespace_raises(self):
        """Base URL 为空白时抛 LLMConfigurationError"""
        with pytest.raises(LLMConfigurationError, match="Base URL"):
            DeepSeekLLMProvider(
                api_key="sk-test",
                base_url="   ",
                model="deepseek-chat",
                timeout_seconds=30.0,
            )

    def test_model_empty_raises(self):
        """Model 为空时抛 LLMConfigurationError"""
        with pytest.raises(LLMConfigurationError, match="Model"):
            DeepSeekLLMProvider(
                api_key="sk-test",
                base_url="https://api.deepseek.com/v1",
                model="",
                timeout_seconds=30.0,
            )

    def test_model_whitespace_raises(self):
        """Model 为空白时抛 LLMConfigurationError"""
        with pytest.raises(LLMConfigurationError, match="Model"):
            DeepSeekLLMProvider(
                api_key="sk-test",
                base_url="https://api.deepseek.com/v1",
                model="   ",
                timeout_seconds=30.0,
            )


# ══════════════════════════════════════════════════════════════════
# URL 构造测试
# ══════════════════════════════════════════════════════════════════

class TestURLConstruction:
    """URL 拼接测试"""

    def test_url_without_trailing_slash(self):
        """Base URL 无末尾 /"""
        p = _build_provider(base_url="https://api.deepseek.com/v1")
        assert p._build_url() == "https://api.deepseek.com/v1/chat/completions"

    def test_url_with_trailing_slash(self):
        """Base URL 有末尾 /"""
        p = _build_provider(base_url="https://api.deepseek.com/v1/")
        assert p._build_url() == "https://api.deepseek.com/v1/chat/completions"

    def test_url_no_double_slash(self):
        """不产生重复 //"""
        p = _build_provider(base_url="https://api.deepseek.com/v1///")
        assert p._build_url() == "https://api.deepseek.com/v1/chat/completions"


# ══════════════════════════════════════════════════════════════════
# 请求构造测试
# ══════════════════════════════════════════════════════════════════

class TestRequestBuilding:
    """请求构造测试"""

    def test_messages_passed_correctly(self):
        """messages 正确传递"""
        p = _build_provider()
        msgs = [
            {"role": "user", "content": "Return JSON: {\"x\":1}"},
        ]
        req = LLMRequest(messages=msgs)
        built = p._build_messages(req)
        assert len(built) == 1
        assert built[0]["role"] == "user"
        assert built[0]["content"] == "Return JSON: {\"x\":1}"

    def test_scenario_key_not_in_messages(self):
        """scenario_key 不发送给 DeepSeek"""
        p = _build_provider()
        req = LLMRequest(
            messages=_json_messages(),
            scenario_key="test_scenario",
        )
        built = p._build_messages(req)
        for msg in built:
            assert "scenario_key" not in msg

    def test_metadata_not_in_messages(self):
        """metadata 不发送给 DeepSeek"""
        p = _build_provider()
        req = LLMRequest(
            messages=_json_messages(),
            metadata={"key": "value"},
        )
        built = p._build_messages(req)
        for msg in built:
            assert "metadata" not in msg

    def test_response_format_json_object(self):
        """response_format 为 json_object"""
        p = _build_provider()
        payload = p._build_payload(_json_messages())
        assert payload["response_format"] == {"type": "json_object"}

    def test_stream_false(self):
        """stream 为 false"""
        p = _build_provider()
        payload = p._build_payload(_json_messages())
        assert payload["stream"] is False

    def test_temperature_zero(self):
        """temperature 为 0"""
        p = _build_provider()
        payload = p._build_payload(_json_messages())
        assert payload["temperature"] == 0

    def test_model_from_config(self):
        """model 读取配置"""
        p = _build_provider(model="deepseek-v3")
        payload = p._build_payload(_json_messages())
        assert payload["model"] == "deepseek-v3"

    def test_authorization_header_exists(self):
        """Authorization Header 存在"""
        p = _build_provider(api_key="sk-test-123")
        headers = p._build_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_messages_empty_raises(self):
        """messages 为空时抛 LLMRequestError"""
        p = _build_provider()
        req = LLMRequest(messages=[])
        with pytest.raises(LLMRequestError, match="不能为空"):
            p._validate_request(req)

    def test_no_json_instruction_raises(self):
        """消息未要求 JSON 输出时抛 LLMRequestError"""
        p = _build_provider()
        req = LLMRequest(messages=[
            {"role": "user", "content": "Hello, how are you?"},
        ])
        with pytest.raises(LLMRequestError, match="JSON"):
            p._validate_request(req)


# ══════════════════════════════════════════════════════════════════
# 成功路径测试
# ══════════════════════════════════════════════════════════════════

class TestSuccessfulResponse:
    """成功响应解析测试"""

    @pytest.mark.asyncio
    async def test_parse_pydantic_output(self):
        """正确解析 Pydantic 输出"""
        transport = httpx.MockTransport(
            lambda req: _build_json_response({"status": "ok", "value": 99})
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        resp = await p.generate(req, _TestModel)
        assert resp.structured is not None
        assert resp.structured.status == "ok"
        assert resp.structured.value == 99

    @pytest.mark.asyncio
    async def test_parse_model(self):
        """正确解析 model 字段"""
        transport = httpx.MockTransport(
            lambda req: _build_json_response(model="deepseek-chat-custom")
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        resp = await p.generate(req, _TestModel)
        assert resp.model == "deepseek-chat-custom"

    @pytest.mark.asyncio
    async def test_parse_finish_reason(self):
        """正确解析 finish_reason"""
        transport = httpx.MockTransport(
            lambda req: _build_json_response(finish_reason="length")
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        resp = await p.generate(req, _TestModel)
        assert resp.finish_reason == "length"

    @pytest.mark.asyncio
    async def test_parse_usage(self):
        """正确解析 usage"""
        transport = httpx.MockTransport(
            lambda req: _build_json_response(
                prompt_tokens=100, completion_tokens=50
            )
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        resp = await p.generate(req, _TestModel)
        assert resp.usage["prompt_tokens"] == 100
        assert resp.usage["completion_tokens"] == 50
        assert resp.usage["total_tokens"] == 150


# ══════════════════════════════════════════════════════════════════
# HTTP 错误分类测试
# ══════════════════════════════════════════════════════════════════

class TestErrorClassification:
    """错误分类测试"""

    @pytest.mark.asyncio
    async def test_http_400_request_error(self):
        """HTTP 400 → LLMRequestError, retryable=false"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(400)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMRequestError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_http_401_auth_error(self):
        """HTTP 401 → LLMAuthenticationError, retryable=false"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(401)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMAuthenticationError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_http_403_auth_error(self):
        """HTTP 403 → LLMAuthenticationError, retryable=false"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(403)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMAuthenticationError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_http_429_rate_limit(self):
        """HTTP 429 → LLMRateLimitError, retryable=true"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(429)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMRateLimitError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True

    @pytest.mark.asyncio
    async def test_http_500_service_error(self):
        """HTTP 500 → LLMServiceError, retryable=true"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(500)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMServiceError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True

    @pytest.mark.asyncio
    async def test_http_503_service_error(self):
        """HTTP 503 → LLMServiceError, retryable=true"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(503)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMServiceError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True

    @pytest.mark.asyncio
    async def test_http_422_request_error(self):
        """HTTP 422 → LLMRequestError, retryable=false"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(422)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMRequestError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False


# ══════════════════════════════════════════════════════════════════
# 连接/超时/响应解析错误测试
# ══════════════════════════════════════════════════════════════════

class TestConnectionAndTimeout:
    """连接和超时错误测试"""

    @pytest.mark.asyncio
    async def test_connect_error(self):
        """ConnectError → LLMConnectionError, retryable=true"""

        def _connect_error(req):
            raise httpx.ConnectError("connection refused")

        transport = httpx.MockTransport(_connect_error)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMConnectionError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """TimeoutException → LLMTimeoutError, retryable=true"""

        def _timeout(req):
            raise httpx.TimeoutException("timeout")

        transport = httpx.MockTransport(_timeout)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMTimeoutError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True


class TestResponseParsing:
    """响应解析错误测试"""

    @pytest.mark.asyncio
    async def test_body_not_json(self):
        """HTTP Body 非法 JSON → LLMResponseError, retryable=false"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=b"not json")
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_choices_missing(self):
        """choices 缺失 → LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"id": "test"})
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_choices_empty(self):
        """choices 为空 → LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"choices": []})
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_message_missing(self):
        """message 缺失 → LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"index": 0}],
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_content_empty(self):
        """content 为空 → LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": ""}}],
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_content_not_valid_json(self):
        """content 非法 JSON → LLMValidationError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": "not valid json!!!"}}],
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMValidationError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False

    @pytest.mark.asyncio
    async def test_output_type_validation_fails(self):
        """output_type 验证失败 → LLMValidationError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": '{"wrong_field": true}'}}],
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMValidationError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False


# ══════════════════════════════════════════════════════════════════
# retryable 分类验证
# ══════════════════════════════════════════════════════════════════

class TestRetryableClassification:
    """retryable 分类完整验证"""

    @pytest.mark.parametrize("status,retryable", [
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (422, False),
        (429, True),
        (500, True),
        (502, True),
        (503, True),
    ])
    @pytest.mark.asyncio
    async def test_retryable_by_status(self, status, retryable):
        """HTTP 状态码 retryable 分类正确"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(status)
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMProviderError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable == retryable, (
            f"status {status}: expected retryable={retryable}"
        )


# ══════════════════════════════════════════════════════════════════
# Secret 防泄漏测试
# ══════════════════════════════════════════════════════════════════

class TestSecretProtection:
    """Secret 防泄漏测试"""

    def test_repr_no_key(self):
        """repr 不含 Key"""
        secret = "sk-" + "very-secret-key-12345"
        p = _build_provider(api_key=secret)
        r = repr(p)
        assert secret not in r
        assert "has_api_key=True" in r

    def test_exception_no_key(self):
        """异常文本不含 Key"""
        transport = httpx.MockTransport(
            lambda req: _build_error_response(401)
        )
        p = _build_provider(api_key="sk-secret-123", transport=transport)

        async def _run():
            req = LLMRequest(messages=_json_messages())
            try:
                await p.generate(req, _TestModel)
            except LLMAuthenticationError as e:
                return str(e)
            return ""

        import asyncio
        msg = asyncio.run(_run())
        assert "sk-secret-123" not in msg

    def test_external_client_not_closed(self):
        """外部注入的 Client 不被 Provider 关闭"""
        client = httpx.AsyncClient()
        p = DeepSeekLLMProvider(
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_seconds=30.0,
            client=client,
        )
        assert p._owns_client is False
        # 外部 client 仍可用
        assert not client.is_closed

    @pytest.mark.asyncio
    async def test_self_owned_client_can_close(self):
        """自建 Client 可以被 aclose() 关闭"""
        transport = httpx.MockTransport(
            lambda req: _build_json_response()
        )
        client = httpx.AsyncClient(transport=transport)
        p = DeepSeekLLMProvider(
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_seconds=30.0,
            client=client,
        )
        # 外部注入
        p._owns_client = True  # 模拟自建
        p._owned_client = client
        await p.aclose()
        # 重复调用不报错
        await p.aclose()

    def test_has_api_key_no_leak(self):
        """has_api_key 属性不暴露原文"""
        p = _build_provider(api_key="sk-secret-value-123")
        assert p.has_api_key is True
        assert not hasattr(p, "api_key")


# ══════════════════════════════════════════════════════════════════
# 并发测试
# ══════════════════════════════════════════════════════════════════

class TestConcurrency:
    """并发请求无共享状态"""

    @pytest.mark.asyncio
    async def test_concurrent_requests_independent(self):
        """并发请求无共享请求状态"""
        import asyncio

        call_count = 0

        def _handler(req):
            nonlocal call_count
            call_count += 1
            return _build_json_response({"status": "ok", "value": call_count})

        transport = httpx.MockTransport(_handler)
        p = _build_provider(transport=transport)

        async def _make_request(n: int):
            req = LLMRequest(messages=_json_messages())
            return await p.generate(req, _TestModel)

        results = await asyncio.gather(*[_make_request(i) for i in range(5)])
        assert len(results) == 5
        for r in results:
            assert r.structured.status == "ok"

    @pytest.mark.asyncio
    async def test_no_second_request_auto_sent(self):
        """不会自动发送第二次请求（无自动重试）"""
        call_count = 0

        def _handler(req):
            nonlocal call_count
            call_count += 1
            return _build_error_response(500)

        transport = httpx.MockTransport(_handler)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMServiceError):
            await p.generate(req, _TestModel)
        assert call_count == 1  # 只发送了一次


# ══════════════════════════════════════════════════════════════════
# M1.2 收口：网络异常分类扩充
# ══════════════════════════════════════════════════════════════════

class TestM12NetworkErrors:
    """M1.2 补齐的网络异常分类"""

    @pytest.mark.asyncio
    async def test_read_error_maps_to_connection_retryable(self):
        """ReadError → LLMConnectionError, retryable=true"""
        def _read_error(req):
            raise httpx.ReadError("read error")

        transport = httpx.MockTransport(_read_error)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMConnectionError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True
        assert exc.value.error_code == "read_error"

    @pytest.mark.asyncio
    async def test_write_error_maps_to_connection_retryable(self):
        """WriteError → LLMConnectionError, retryable=true"""
        def _write_error(req):
            raise httpx.WriteError("write error")

        transport = httpx.MockTransport(_write_error)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMConnectionError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True
        assert exc.value.error_code == "write_error"

    @pytest.mark.asyncio
    async def test_close_error_maps_to_connection_retryable(self):
        """CloseError → LLMConnectionError, retryable=true"""
        def _close_error(req):
            raise httpx.CloseError("close error")

        transport = httpx.MockTransport(_close_error)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMConnectionError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True
        assert exc.value.error_code == "close_error"

    @pytest.mark.asyncio
    async def test_remote_protocol_error_maps_to_connection_retryable(self):
        """RemoteProtocolError → LLMConnectionError, retryable=true"""
        def _remote_proto_error(req):
            raise httpx.RemoteProtocolError("remote protocol error")

        transport = httpx.MockTransport(_remote_proto_error)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMConnectionError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is True
        assert exc.value.error_code == "remote_protocol_error"

    @pytest.mark.asyncio
    async def test_local_protocol_error_not_retryable(self):
        """LocalProtocolError → LLMRequestError, retryable=false"""
        def _local_proto_error(req):
            raise httpx.LocalProtocolError("local protocol error")

        transport = httpx.MockTransport(_local_proto_error)
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMRequestError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.retryable is False
        assert exc.value.error_code == "local_protocol_error"

    @pytest.mark.asyncio
    async def test_network_error_no_key_leak(self):
        """网络错误不泄漏 Key"""
        secret = "sk-" + "secret-leak-test-key"
        def _connect_error(req):
            raise httpx.ConnectError("connection refused")

        transport = httpx.MockTransport(_connect_error)
        p = _build_provider(api_key=secret, transport=transport)
        req = LLMRequest(messages=_json_messages())
        try:
            await p.generate(req, _TestModel)
        except LLMConnectionError as e:
            msg = str(e)
            assert "sk-secret" not in msg
            assert "sk-" not in msg or "secret" not in msg


# ══════════════════════════════════════════════════════════════════
# M1.2 收口：响应结构防御加强
# ══════════════════════════════════════════════════════════════════

class TestM12ResponseStructureDefense:
    """M1.2 加强的响应结构严格验证"""

    @pytest.mark.asyncio
    async def test_body_is_list_returns_response_error(self):
        """Body 为 list 时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=[])
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_response_body"

    @pytest.mark.asyncio
    async def test_choices_not_list_returns_response_error(self):
        """choices 不是 list 时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"choices": "not_a_list"})
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_choices"

    @pytest.mark.asyncio
    async def test_choice_not_dict_returns_response_error(self):
        """choice 不是 dict 时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"choices": ["not_a_dict"]})
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_choice"

    @pytest.mark.asyncio
    async def test_message_not_dict_returns_response_error(self):
        """message 不是 dict 时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": "not_a_dict"}],
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_message"

    @pytest.mark.asyncio
    async def test_usage_not_dict_returns_response_error(self):
        """usage 不是 dict 时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": '{"status":"ok","value":1}'}}],
                "usage": "not_a_dict",
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_usage"

    @pytest.mark.asyncio
    async def test_token_as_string_returns_response_error(self):
        """Token 为字符串时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": '{"status":"ok","value":1}'}}],
                "usage": {"prompt_tokens": "not_an_int", "completion_tokens": 5, "total_tokens": 5},
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_token_usage"

    @pytest.mark.asyncio
    async def test_token_negative_returns_response_error(self):
        """Token 为负数时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": '{"status":"ok","value":1}'}}],
                "usage": {"prompt_tokens": -1, "completion_tokens": 5, "total_tokens": 4},
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_token_usage"

    @pytest.mark.asyncio
    async def test_token_as_bool_returns_response_error(self):
        """Token 为 bool 时返回 LLMResponseError"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": '{"status":"ok","value":1}'}}],
                "usage": {"prompt_tokens": True, "completion_tokens": 5, "total_tokens": 5},
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        with pytest.raises(LLMResponseError) as exc:
            await p.generate(req, _TestModel)
        assert exc.value.error_code == "invalid_token_usage"

    @pytest.mark.asyncio
    async def test_exception_no_raw_body_leak(self):
        """异常不泄漏原始 Body 内容"""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={
                "choices": [{"message": {"content": '{"status":"ok","value":1}'}}],
                "usage": {"prompt_tokens": "bad_value", "completion_tokens": 5, "total_tokens": 5},
            })
        )
        p = _build_provider(transport=transport)
        req = LLMRequest(messages=_json_messages())
        try:
            await p.generate(req, _TestModel)
        except LLMResponseError as e:
            msg = str(e)
            # token 非法值不应直接出现在异常消息中（不泄漏完整响应）
            assert "bad_value" not in msg
