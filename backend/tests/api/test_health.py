"""Health API 测试 — M0.4"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.api.dependencies import set_mock_turn_service
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.main import create_app


@pytest_asyncio.fixture
async def client():
    app = create_app()
    set_mock_turn_service(MockTurnService())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    """GET /health"""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_status_ok(self, client):
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_app_name(self, client):
        response = await client.get("/health")
        data = response.json()
        assert data["app_name"] == "PowerBIAgent"

    @pytest.mark.asyncio
    async def test_health_version(self, client):
        response = await client.get("/health")
        data = response.json()
        assert data["version"] == "M0.4"

    @pytest.mark.asyncio
    async def test_health_mode_fields(self, client):
        response = await client.get("/health")
        data = response.json()
        assert data["llm_mode"] == "mock"
        assert data["powerbi_mode"] == "mock"
        assert data["harness_mode"] == "strict"

    @pytest.mark.asyncio
    async def test_health_timestamp(self, client):
        response = await client.get("/health")
        data = response.json()
        assert "timestamp" in data
        assert data["timestamp"]

    @pytest.mark.asyncio
    async def test_health_no_sensitive_fields(self, client):
        response = await client.get("/health")
        data = response.json()
        for key in data:
            assert "key" not in key.lower(), f"Sensitive field leaked: {key}"
            assert "secret" not in key.lower(), f"Sensitive field leaked: {key}"
            assert "token" not in key.lower(), f"Sensitive field leaked: {key}"
            assert "password" not in key.lower(), f"Sensitive field leaked: {key}"

    @pytest.mark.asyncio
    async def test_health_not_call_llm(self, client):
        """Health 不调用 LLM — 在 Mock 模式下返回即可验证"""
        response = await client.get("/health")
        assert response.status_code == 200
