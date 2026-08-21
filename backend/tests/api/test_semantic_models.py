"""M5.2 safe semantic-model discovery API tests."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as value:
            yield value


@pytest.mark.asyncio
async def test_discovery_endpoint_returns_backend_catalog(client):
    response = await client.get("/api/v1/semantic-models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_mode"] == "mock"
    assert payload["error_type"] is None
    assert payload["items"]
    sales = next(item for item in payload["items"] if item["key"] == "mock_sales_model")
    assert sales == {
        "key": "mock_sales_model",
        "display_name": "Mock 销售模型",
        "source": "mock",
        "type": "semantic_model",
        "available": True,
        "connected": True,
    }


@pytest.mark.asyncio
async def test_discovery_response_excludes_connection_and_schema_details(client):
    response = await client.get("/api/v1/semantic-models")
    text = response.text.lower()

    assert response.status_code == 200
    for forbidden in (
        "connectionstring",
        "localhost",
        "processid",
        "port",
        "dax",
        "columns",
        "measures",
    ):
        assert forbidden not in text


def test_openapi_declares_read_only_discovery_route():
    operation = create_app().openapi()["paths"]["/api/v1/semantic-models"]
    assert set(operation) == {"get"}
