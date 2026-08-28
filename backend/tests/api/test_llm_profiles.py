"""M5.8 safe public LLM profile catalog and selection errors."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.llm.base import LLMValidationError
from backend.app.main import create_app


def _settings(**overrides) -> Settings:
    values = {
        "llm_mode": LLMMode.OPENAI_COMPATIBLE,
        "llm_default_profile": "deepseek",
        "powerbi_mode": PowerBIMode.MOCK,
        "deepseek_api_key": "deepseek-test-secret",
        "kimi_api_key": "kimi-test-secret",
        "kimi_base_url": "https://gateway.example.test/v1",
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_profile_catalog_is_public_safe_and_backend_owned() -> None:
    app = create_app(settings=_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/llm-profiles")

    assert response.status_code == 200
    payload = response.json()
    assert [item["profile_key"] for item in payload["items"]] == [
        "mock",
        "deepseek",
        "kimi-k2.6",
    ]
    assert next(item for item in payload["items"] if item["profile_key"] == "deepseek")["default"] is True
    serialized = response.text
    assert "deepseek-test-secret" not in serialized
    assert "kimi-test-secret" not in serialized
    assert "gateway.example.test" not in serialized


@pytest.mark.asyncio
async def test_unknown_profile_is_rejected_before_any_provider_call() -> None:
    app = create_app(settings=_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "message": "总销售额是多少？",
                    "request_id": "unknown-profile-request",
                    "conversation_id": "unknown-profile-conversation",
                    "llm_profile_key": "not-registered",
                },
            )

    assert response.status_code == 422
    assert response.json()["error_type"] == "llm_profile_unknown"


@pytest.mark.asyncio
async def test_known_but_unavailable_profile_fails_closed() -> None:
    settings = _settings(kimi_api_key=None, kimi_base_url="")
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "message": "总销售额是多少？",
                    "request_id": "unavailable-profile-request",
                    "conversation_id": "unavailable-profile-conversation",
                    "llm_profile_key": "kimi-k2.6",
                },
            )

    assert response.status_code == 503
    assert response.json()["error_type"] == "llm_profile_unavailable"


@pytest.mark.asyncio
async def test_provider_error_preserves_safe_frozen_profile_metadata() -> None:
    app = create_app(settings=_settings())
    error = LLMValidationError(
        "sensitive provider payload",
        provider="kimi-k2.6",
        error_code="output_schema_invalid",
    )
    async with app.router.lifespan_context(app):
        app.state.turn_service.execute = AsyncMock(side_effect=error)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "message": "总销售额是多少？",
                    "request_id": "kimi-validation-error-request",
                    "conversation_id": "kimi-validation-error-conversation",
                    "llm_profile_key": "kimi-k2.6",
                },
            )

    assert response.status_code == 502
    payload = response.json()
    assert payload["error_type"] == "llm_validation_error"
    assert payload["llm_profile_key"] == "kimi-k2.6"
    assert payload["llm_model"] == "azure/Kimi-K2.6"
    assert payload["llm_provider_protocol"] == "openai_chat_completions"
    assert payload["llm_error_category"] == "response_validation"
    assert payload["llm_error_class"] == "LLMValidationError"
    serialized = response.text
    assert "sensitive provider payload" not in serialized
    assert "Authorization" not in serialized
    assert "Bearer" not in serialized


@pytest.mark.asyncio
async def test_unexpected_turn_error_still_preserves_requested_profile_identity() -> None:
    app = create_app(settings=_settings())
    async with app.router.lifespan_context(app):
        app.state.turn_service.execute = AsyncMock(
            side_effect=RuntimeError("sensitive internal detail")
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "message": "总销售额是多少？",
                    "request_id": "kimi-internal-error-request",
                    "conversation_id": "kimi-internal-error-conversation",
                    "llm_profile_key": "kimi-k2.6",
                },
            )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error_type"] == "internal_error"
    assert payload["llm_profile_key"] == "kimi-k2.6"
    assert payload["llm_model"] == "azure/Kimi-K2.6"
    assert payload["llm_provider_protocol"] == "openai_chat_completions"
    assert payload["llm_error_category"] == ""
    assert payload["llm_error_class"] == ""
    assert "sensitive internal detail" not in response.text
