"""M5.2 safe semantic-model discovery API tests."""

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.application.semantic_model_discovery_service import (
    SemanticModelDiscoveryService,
)
from backend.app.config.settings import Settings
from backend.app.main import create_app
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.models import SemanticModelCatalog, SemanticModelOption
from backend.app.query_plan.semantic_catalog import GlossaryCatalogError
from backend.app.query_plan.semantic_catalog import SemanticCatalog
from backend.app.schemas.data_contracts import (
    DAXRequest,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
)


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
    assert [item["key"] for item in payload["items"]] == ["mock_sales_model"]
    sales = payload["items"][0]
    assert sales == {
        "key": "mock_sales_model",
        "display_name": "Mock 销售模型",
        "source": "mock",
        "type": "semantic_model",
        "available": True,
        "connected": True,
        "agent_compatible": True,
        "selectable": True,
        "schema_drift": False,
        "compatibility_status": "compatible",
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


class _RealDiscoveryAdapter(PowerBIAdapter):
    def __init__(self, schema: SemanticModelSchema):
        self.schema = schema

    @property
    def provider_name(self) -> str:
        return "fake_local"

    @property
    def is_mock(self) -> bool:
        return False

    async def health_check(self) -> bool:
        return True

    async def discover_semantic_models(self) -> SemanticModelCatalog:
        return SemanticModelCatalog(
            runtime_mode="real",
            items=[
                SemanticModelOption(
                    key=self.schema.key,
                    display_name="当前 Desktop 模型",
                    source="local_desktop",
                    available=True,
                    connected=True,
                )
            ],
        )

    async def get_semantic_model_schema(self, semantic_model_key: str):
        assert semantic_model_key == self.schema.key
        return self.schema

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        raise AssertionError("compatibility discovery must not execute DAX")

    async def normalize_result(self, raw: object) -> QueryResult:
        raise AssertionError("not used")

    async def normalize_error(self, raw: object) -> PowerBIError:
        raise AssertionError("not used")


@pytest.mark.asyncio
async def test_real_discovery_marks_glossary_compatible_model_selectable():
    schema = SemanticModelSchema(name="Desktop", key="local_desktop_model")
    service = SemanticModelDiscoveryService(
        _RealDiscoveryAdapter(schema), Settings(_env_file=None)
    )
    with patch(
        "backend.app.application.semantic_model_discovery_service."
        "SemanticCatalogBuilder.build",
        return_value=SemanticCatalog(
            semantic_model_key=schema.key,
            schema_fingerprint="0" * 64,
            schema_drift=False,
            objects=(),
        ),
    ):
        catalog = await service.discover()

    assert catalog.items[0].agent_compatible is True
    assert catalog.items[0].selectable is True
    assert catalog.items[0].schema_drift is False
    assert catalog.items[0].compatibility_status == "compatible"


@pytest.mark.asyncio
async def test_real_discovery_keeps_drifted_complete_model_selectable():
    schema = SemanticModelSchema(name="Desktop", key="local_desktop_model")
    service = SemanticModelDiscoveryService(
        _RealDiscoveryAdapter(schema), Settings(_env_file=None)
    )
    with patch(
        "backend.app.application.semantic_model_discovery_service."
        "SemanticCatalogBuilder.build",
        return_value=SemanticCatalog(
            semantic_model_key=schema.key,
            schema_fingerprint="1" * 64,
            schema_drift=True,
            objects=(),
        ),
    ):
        catalog = await service.discover()

    model = catalog.items[0]
    assert model.connected is True
    assert model.agent_compatible is True
    assert model.selectable is True
    assert model.schema_drift is True
    assert model.compatibility_status == "compatible"


@pytest.mark.asyncio
async def test_real_discovery_keeps_connected_but_incompatible_model_explicit():
    schema = SemanticModelSchema(name="Desktop", key="local_desktop_model")
    service = SemanticModelDiscoveryService(
        _RealDiscoveryAdapter(schema), Settings(_env_file=None)
    )
    with patch(
        "backend.app.application.semantic_model_discovery_service."
        "SemanticCatalogBuilder.build",
        side_effect=GlossaryCatalogError("glossary_unknown_object"),
    ):
        catalog = await service.discover()

    model = catalog.items[0]
    assert model.connected is True
    assert model.agent_compatible is False
    assert model.selectable is False
    assert model.schema_drift is False
    assert model.compatibility_status == "incompatible"
    serialized = catalog.model_dump_json().lower()
    assert "fingerprint" not in serialized
    assert "dax" not in serialized
