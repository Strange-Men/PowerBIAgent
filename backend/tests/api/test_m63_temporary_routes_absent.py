"""Acceptance probes must never be mounted on the native product application."""
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.api.test_auth_security import FakeIdentity, ORIGIN, config, login


def test_native_application_excludes_acceptance_routes_and_keeps_product_closed():
    app = create_app(config(), identity_client=FakeIdentity())
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any("m63" in path.lower() or "debug" in path.lower() for path in paths)
    with TestClient(app, base_url=ORIGIN) as client:
        for path in (
            "/auth/m63-security", "/auth/m63-security-matrix",
            "/auth/m63-root-cause", "/auth/m63-type-contract",
            "/auth/m63-late-acceptance", "/auth/m63-late-evidence",
            "/m63-test/conversations/synthetic",
        ):
            assert client.get(path).status_code == 404
        assert client.post("/api/v1/chat", json={"message": "synthetic"}).status_code == 401
        assert login(client).status_code == 302
        headers = {"Origin": ORIGIN, "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"]}
        assert client.post("/auth/m63-security/late/start", headers=headers).status_code == 404
        assert client.post("/api/v1/chat", headers=headers, json={"message": "synthetic"}).status_code == 403
        assert app.state.turn_service is None
        assert app.state.conversation_history_service is None
        assert app.state.report_repository is None
