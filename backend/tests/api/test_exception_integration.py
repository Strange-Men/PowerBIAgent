"""M1.6.5 TEST-165-002: API异常真实ASGI集成测试

M1.6.4 现有异常测试只读取 routes.py 源码并搜索异常名。
本轮通过 ASGI 真实请求验证每个异常类型的HTTP映射。

测试方法：
- 构建 FastAPI 测试应用
- monkeypatch service.execute() 抛出指定异常
- 真实 POST /api/v1/chat
- 验证 HTTP状态码、error_type、detail、request_id、Content-Type
- 验证不泄漏Secret、API Key、Prompt、堆栈

禁止调用真实 DeepSeek。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import Settings
from backend.app.main import create_app
from backend.app.llm.base import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    LLMValidationError,
)
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def make_error_app():
    """创建Mock模式应用，供测试注入异常"""
    settings = Settings()
    app = create_app(settings=settings)
    return app


async def post_with_exception(app, exception_instance):
    """向app发送POST请求，service.execute()将抛出指定异常"""
    # 用monkeypatch在lifespan后替换service的execute
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        # 替换service.execute为抛出异常的mock
        original_execute = app.state.turn_service.execute
        mock_execute = AsyncMock(side_effect=exception_instance)
        app.state.turn_service.execute = mock_execute

        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.post("/api/v1/chat", json={
                "message": "测试异常",
                "conversation_id": "conv-err-test",
                "request_id": "req-err-test",
            })
            result = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            yield response, result

        # 恢复
        app.state.turn_service.execute = original_execute


# ── Convenience wrapper ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def error_client(request):
    """使用indirect parametrize传递异常实例"""
    exception_instance = request.param
    app = make_error_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        original_execute = app.state.turn_service.execute
        mock_execute = AsyncMock(side_effect=exception_instance)
        app.state.turn_service.execute = mock_execute
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, exception_instance
        app.state.turn_service.execute = original_execute


# ═════════════════════════════════════════════════════════════════════════════
# LLM 认证错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMAuthenticationError:
    """LLMAuthenticationError → 502 deepseek_authentication_failed"""

    @pytest.mark.asyncio
    async def test_auth_error_502(self):
        exc = LLMAuthenticationError("Invalid API Key", provider="deepseek",
                                      status_code=401, error_code="authentication_failed")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-auth",
                    "request_id": "req-auth",
                })
        assert response.status_code == 502
        data = response.json()
        assert data["error_type"] == "llm_authentication_failed"
        assert "detail" in data
        assert "request_id" in data
        # 不泄漏异常字符串
        assert "Invalid API Key" not in str(data)
        # Content-Type
        assert "application/json" in response.headers.get("content-type", "")
        # 不泄漏 Secret
        response_text = str(data)
        assert "sk-" not in response_text
        assert "Bearer" not in response_text
        assert "Authorization" not in response_text


# ═════════════════════════════════════════════════════════════════════════════
# LLM 配置错误 — api_key_missing
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMConfigurationErrorAPIKeyMissing:
    """LLMConfigurationError(api_key_missing) → 503 deepseek_api_key_missing"""

    @pytest.mark.asyncio
    async def test_api_key_missing_503(self):
        exc = LLMConfigurationError("API Key not found", provider="deepseek",
                                     error_code="api_key_missing")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-cfg-key",
                    "request_id": "req-cfg-key",
                })
        assert response.status_code == 503
        data = response.json()
        assert data["error_type"] == "llm_api_key_missing"
        assert "detail" in data
        assert "request_id" in data


# ═════════════════════════════════════════════════════════════════════════════
# LLM 配置错误 — insufficient_balance
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMConfigurationErrorInsufficientBalance:
    """LLMConfigurationError(insufficient_balance) → 402 deepseek_insufficient_balance"""

    @pytest.mark.asyncio
    async def test_insufficient_balance_402(self):
        exc = LLMConfigurationError("Insufficient balance", provider="deepseek",
                                     status_code=402, error_code="insufficient_balance")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-bal",
                    "request_id": "req-bal",
                })
        assert response.status_code == 402
        data = response.json()
        assert data["error_type"] == "llm_insufficient_balance"
        assert "detail" in data


# ═════════════════════════════════════════════════════════════════════════════
# LLM 配置错误 — invalid_base_url
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMConfigurationErrorInvalidBaseURL:
    """LLMConfigurationError(invalid_base_url) → 503 deepseek_invalid_base_url"""

    @pytest.mark.asyncio
    async def test_invalid_base_url_503(self):
        exc = LLMConfigurationError("Invalid base URL", provider="deepseek",
                                     error_code="invalid_base_url")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-url",
                    "request_id": "req-url",
                })
        assert response.status_code == 503
        data = response.json()
        assert data["error_type"] == "llm_invalid_base_url"


# ═════════════════════════════════════════════════════════════════════════════
# LLM 配置错误 — invalid_model
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMConfigurationErrorInvalidModel:
    """LLMConfigurationError(invalid_model) → 503 deepseek_invalid_model"""

    @pytest.mark.asyncio
    async def test_invalid_model_503(self):
        exc = LLMConfigurationError("Invalid model name", provider="deepseek",
                                     error_code="invalid_model")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-model",
                    "request_id": "req-model",
                })
        assert response.status_code == 503
        data = response.json()
        assert data["error_type"] == "llm_invalid_model"


# ═════════════════════════════════════════════════════════════════════════════
# LLM 配置错误 — 未知/其他 error_code（关键Bug修复验证）
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMConfigurationErrorUnknown:
    """LLMConfigurationError(unknown) → 不得伪装为 deepseek_api_key_missing

    本轮关键修复：未知LLMConfigurationError应返回 deepseek_configuration_error，
    而非 deepseek_api_key_missing。只有真实 api_key_missing 才允许 api_key_missing。
    """

    @pytest.mark.asyncio
    async def test_unknown_config_error_not_api_key_missing(self):
        """未知配置错误不得伪装为api_key_missing"""
        exc = LLMConfigurationError("Unknown config problem", provider="deepseek",
                                     error_code="some_unknown_error")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-unknown",
                    "request_id": "req-unknown",
                })
        assert response.status_code == 503
        data = response.json()
        # 关键断言：不是 api_key_missing
        assert data["error_type"] != "deepseek_api_key_missing", (
            f"未知配置错误不得伪装为deepseek_api_key_missing: got={data['error_type']}"
        )
        # 应是通用配置错误
        assert data["error_type"] == "llm_configuration_error", (
            f"未知配置错误应返回llm_configuration_error: got={data['error_type']}"
        )

    @pytest.mark.asyncio
    async def test_config_error_without_error_code_not_api_key_missing(self):
        """无error_code的配置错误也不得伪装为api_key_missing"""
        exc = LLMConfigurationError("Configuration problem", provider="deepseek")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-no-ec",
                    "request_id": "req-no-ec",
                })
        assert response.status_code == 503
        data = response.json()
        assert data["error_type"] != "deepseek_api_key_missing", (
            f"无error_code的配置错误不得伪装: got={data['error_type']}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# LLM 请求错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMRequestError:
    """LLMRequestError → 502 deepseek_request_error"""

    @pytest.mark.asyncio
    async def test_request_error_502(self):
        exc = LLMRequestError("Bad request", provider="deepseek",
                              status_code=400, error_code="invalid_format")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-req",
                    "request_id": "req-req",
                })
        assert response.status_code == 502
        data = response.json()
        assert data["error_type"] == "llm_request_error"


# ═════════════════════════════════════════════════════════════════════════════
# LLM 响应错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMResponseError:
    """LLMResponseError → 502 deepseek_response_error"""

    @pytest.mark.asyncio
    async def test_response_error_502(self):
        exc = LLMResponseError("Bad response format", provider="deepseek")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-resp",
                    "request_id": "req-resp",
                })
        assert response.status_code == 502
        data = response.json()
        assert data["error_type"] == "llm_response_error"


# ═════════════════════════════════════════════════════════════════════════════
# LLM 校验错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMValidationError:
    """LLMValidationError → 502 deepseek_validation_error"""

    @pytest.mark.asyncio
    async def test_validation_error_502(self):
        exc = LLMValidationError("Schema validation failed", provider="deepseek",
                                  error_code="output_schema_invalid")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-val",
                    "request_id": "req-val",
                })
        assert response.status_code == 502
        data = response.json()
        assert data["error_type"] == "llm_validation_error"
        # 不得泄漏校验错误详情
        assert "Schema validation failed" not in str(data)


# ═════════════════════════════════════════════════════════════════════════════
# LLM 超时错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMTimeoutError:
    """LLMTimeoutError → 504 deepseek_timeout"""

    @pytest.mark.asyncio
    async def test_timeout_error_504(self):
        exc = LLMTimeoutError("Request timed out", provider="deepseek",
                               error_code="read_timeout")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-timeout",
                    "request_id": "req-timeout",
                })
        assert response.status_code == 504
        data = response.json()
        assert data["error_type"] == "llm_timeout"


# ═════════════════════════════════════════════════════════════════════════════
# LLM 连接错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMConnectionError:
    """LLMConnectionError → 502 deepseek_connection_failed"""

    @pytest.mark.asyncio
    async def test_connection_error_502(self):
        exc = LLMConnectionError("Connection refused", provider="deepseek",
                                  error_code="connect_error")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-conn",
                    "request_id": "req-conn",
                })
        assert response.status_code == 502
        data = response.json()
        assert data["error_type"] == "llm_connection_failed"


# ═════════════════════════════════════════════════════════════════════════════
# LLM 限流错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMRateLimitError:
    """LLMRateLimitError → 503 deepseek_rate_limited"""

    @pytest.mark.asyncio
    async def test_rate_limit_error_503(self):
        exc = LLMRateLimitError("Rate limited", provider="deepseek",
                                 status_code=429, error_code="rate_limited")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-rate",
                    "request_id": "req-rate",
                })
        assert response.status_code == 503
        data = response.json()
        assert data["error_type"] == "llm_rate_limited"


# ═════════════════════════════════════════════════════════════════════════════
# LLM 服务错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMServiceError:
    """LLMServiceError → 502/503 deepseek_service_unavailable"""

    @pytest.mark.asyncio
    async def test_service_error_5xx_502(self):
        exc = LLMServiceError("Internal server error", provider="deepseek",
                               status_code=500, error_code="http_500")
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-svc",
                    "request_id": "req-svc",
                })
        assert response.status_code == 502
        data = response.json()
        assert data["error_type"] == "llm_service_unavailable"


# ═════════════════════════════════════════════════════════════════════════════
# LLM Provider 兜底错误
# ═════════════════════════════════════════════════════════════════════════════


class TestLLMProviderError:
    """LLMProviderError → 502 deepseek_provider_error（不落入500 internal_error）"""

    @pytest.mark.asyncio
    async def test_provider_error_502_not_500(self):
        exc = LLMProviderError("Unknown provider error", provider="deepseek",
                                retryable=False)
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-prov",
                    "request_id": "req-prov",
                })
        # 关键：不得落入500
        assert response.status_code != 500, (
            f"LLMProviderError不应落入500 internal_error: status={response.status_code}"
        )
        assert response.status_code == 502
        data = response.json()
        assert data["error_type"] == "llm_provider_error"
        # 不得泄漏原始异常
        assert "Unknown provider error" not in str(data)


# ═════════════════════════════════════════════════════════════════════════════
# 幂等冲突错误
# ═════════════════════════════════════════════════════════════════════════════


class TestIdempotencyConflictError:
    """IdempotencyConflictError → 409 request_id_conflict"""

    @pytest.mark.asyncio
    async def test_conflict_error_409(self):
        exc = IdempotencyConflictError(
            detail="Request fingerprint mismatch",
            request_id="req-conflict",
        )
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-conflict",
                    "request_id": "req-conflict",
                })
        assert response.status_code == 409
        data = response.json()
        assert data["error_type"] == "request_id_conflict"
        assert data["request_id"] == "req-conflict"


# ═════════════════════════════════════════════════════════════════════════════
# 幂等协调错误
# ═════════════════════════════════════════════════════════════════════════════


class TestIdempotencyCoordinationError:
    """IdempotencyCoordinationError → 503 idempotency_coordination_unavailable"""

    @pytest.mark.asyncio
    async def test_coordination_error_503(self):
        exc = IdempotencyCoordinationError(
            detail="Owner/Waiter coordination failed",
            request_id="req-coord",
        )
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test",
                    "conversation_id": "conv-coord",
                    "request_id": "req-coord",
                })
        assert response.status_code == 503
        data = response.json()
        assert data["error_type"] == "idempotency_coordination_unavailable"
        assert data["request_id"] == "req-coord"


# ═════════════════════════════════════════════════════════════════════════════
# 综合安全验证
# ═════════════════════════════════════════════════════════════════════════════


class TestExceptionResponseSecurity:
    """所有异常响应不得泄漏Secret、API Key、Prompt或堆栈"""

    EXCEPTIONS_TO_TEST = [
        ("auth", LLMAuthenticationError("Invalid auth", provider="deepseek", status_code=401)),
        ("rate", LLMRateLimitError("Too many requests", provider="deepseek", status_code=429)),
        ("timeout", LLMTimeoutError("Timeout", provider="deepseek", error_code="read_timeout")),
        ("connection", LLMConnectionError("No route", provider="deepseek", error_code="connect_error")),
        ("service", LLMServiceError("Service down", provider="deepseek", status_code=503)),
        ("provider", LLMProviderError("Unknown error", provider="deepseek")),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,exc", EXCEPTIONS_TO_TEST)
    async def test_exception_response_no_secret_leak(self, label, exc):
        """异常响应对每个类型验证无Secret泄漏"""
        app = make_error_app()
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            app.state.turn_service.execute = AsyncMock(side_effect=exc)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                response = await c.post("/api/v1/chat", json={
                    "message": "test with API_KEY=sk-abc123",
                    "conversation_id": f"conv-sec-{label}",
                    "request_id": f"req-sec-{label}",
                })
        data = response.json()
        response_text = str(data)
        # 无Secret泄漏
        assert "sk-" not in response_text, f"{label}: 不应含sk-前缀"
        assert "Bearer" not in response_text, f"{label}: 不应含Bearer"
        assert "Authorization" not in response_text, f"{label}: 不应含Authorization"
        # 无堆栈
        assert "Traceback" not in response_text, f"{label}: 不应含Traceback"
        assert "File \"" not in response_text, f"{label}: 不应含文件路径"
        # 无Prompt
        assert "test with API_KEY=sk-abc123" not in response_text, (
            f"{label}: 不应含原始Prompt"
        )
        # 不得为internal_error（所有已知Provider异常应被显式处理）
        if "error_type" in data:
            assert data["error_type"] != "internal_error", (
                f"{label}: 已知Provider异常不得落入internal_error"
            )
