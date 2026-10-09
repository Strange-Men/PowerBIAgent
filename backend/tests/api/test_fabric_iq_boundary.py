"""New factory must not reopen unowned business APIs."""
from fastapi import Depends
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.powerbi.fabric_iq_dependencies import get_fabric_iq_adapter
from backend.tests.api.test_auth_security import FakeIdentity, ORIGIN, login
from backend.tests.unit.test_fabric_iq_adapter import settings


def test_factory_request_isolation_and_existing_product_gate():
    app = create_app(settings(powerbi_mode="fabric_iq"), identity_client=FakeIdentity())
    retained = []
    @app.get("/synthetic-cloud-dependency")
    async def probe(adapter=Depends(get_fabric_iq_adapter)):
        retained.append(adapter)
        return {"provider": adapter.provider_name}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/synthetic-cloud-dependency").status_code == 401
        login(client)
        assert app.state.fabric_iq_adapter_factory is not None
        for _ in range(2):
            assert client.get("/synthetic-cloud-dependency").json() == {"provider": "fabric_iq"}
        assert retained[0] is not retained[1]
        assert all(a._closed for a in retained)
        for path in ("/api/v1/chat", "/api/v1/conversations", "/api/v1/reports", "/api/v1/semantic-models"):
            assert client.get(path).status_code == 403
        for name in ("turn_service", "mock_turn_service", "report_repository", "conversation_history_service",
                     "semantic_model_discovery_service", "_persistence_engine"):
            assert getattr(app.state, name) is None
    assert app.state.fabric_iq_adapter_factory is None
