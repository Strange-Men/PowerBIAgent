"""Cloud control plane is explicitly allowlisted; execution never opens."""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.api.test_auth_security import config, FakeIdentity, login, ORIGIN


@pytest.fixture
def cloud():
    app = create_app(config(powerbi_mode="fabric_iq"), identity_client=FakeIdentity())
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, app


def test_status_requires_native_session_and_contains_no_identity(cloud):
    client, app = cloud
    assert client.get("/api/v1/cloud/status").status_code == 401
    login(client)
    response = client.get("/api/v1/cloud/status")
    assert response.status_code == 200
    body = response.json()
    assert body["execution_ready"] is False and body["selected_model_key"] is None
    assert set(body) == {"execution_ready", "blockers", "generation", "selected_model_key", "conversation_id"}
    assert app.state.turn_service is None and app.state._persistence_engine is None


def test_selection_rejects_forged_keys_csrf_and_extra_identity(cloud):
    client, _ = cloud
    login(client)
    path = "/api/v1/cloud/selection"
    assert client.post(path, json={"key":"fabric_iq:forged"}).status_code == 403
    headers = {"Origin":ORIGIN,"X-CSRF-Token":client.get("/auth/session").json()["csrf_token"]}
    assert client.post(path, json={"key":"fabric_iq:forged","expected_generation":0},headers=headers).status_code == 403
    response = client.post(path, json={"key":"fabric_iq:forged", "expected_generation":0,"tenant_id":"spoof"},headers=headers)
    assert response.status_code == 422 and "spoof" not in response.text
    assert client.post(path, content=b"not-json", headers=headers).status_code == 422
    assert client.post(path, content=b'{"key":"a","key":"b","expected_generation":0}', headers=headers).status_code == 422
    assert client.post(path, content=b'x'*1025, headers=headers).status_code == 422


def test_allowlist_cannot_open_queries_docs_or_adjacent_paths(cloud):
    client, _ = cloud
    login(client)
    for path in ["/api/v1/chat", "/api/v1/cloud/chat", "/api/v1/cloud/status/extra", "/openapi.json",
                 "/api/reports", "/api/conversations", "/api/v1/semantic-models"]:
        assert client.get(path).status_code == 403
    headers = {"Origin":ORIGIN,"X-CSRF-Token":client.get("/auth/session").json()["csrf_token"]}
    assert client.post("/api/v1/chat",json={"message":"synthetic"},headers=headers).status_code == 403
    assert client.get("/api/v1/cloud/status?principal_id=spoof").status_code == 422
    assert client.request("GET","/api/v1/cloud/status",json={"principal_id":"spoof"}).status_code == 422


def test_metadata_control_plane_is_not_available_for_non_cloud_entra():
    app = create_app(config(),identity_client=FakeIdentity())
    with TestClient(app,base_url=ORIGIN) as client:
        login(client)
        assert client.get("/api/v1/cloud/status").status_code == 403


def test_native_business_refusal_is_distinct_from_auth_and_never_clears_session(cloud):
    client, app = cloud
    login(client)
    response=client.get('/api/v1/cloud/history')
    assert response.status_code==403
    assert response.json()['failure']['code']=='AUTH_FORBIDDEN'
    assert 'state' not in response.json() and 'authenticated' not in response.json()
    assert client.get('/auth/session').json()['authenticated'] is True
    # Formal-product fixture: persistence and execution are distinct service
    # denials. Disabling test scope is not an execution/retention grant.
    app.state.auth_service.settings.fabric_test_mode=False
    history=client.get('/api/v1/cloud/history')
    assert history.status_code==403 and history.json()['denial_reason']=='cloud_persistence_blocked'
    headers={'Origin':ORIGIN,'X-CSRF-Token':client.get('/auth/session').json()['csrf_token']}
    chat=client.post('/api/v1/cloud/chat',json={'message':'synthetic','request_id':'synthetic',
        'expected_generation':0},headers=headers)
    assert chat.status_code==403 and chat.json()['denial_reason']=='cloud_execution_blocked'
    assert client.get('/auth/session').json()['authenticated'] is True
    assert app.state._persistence_engine is None
    assert app.state.cloud_product_services._repositories._engine is None


def test_logout_purges_control_plane_context(cloud):
    client, app = cloud
    login(client)
    assert client.get("/api/v1/cloud/status").status_code == 200
    assert app.state.cloud_workspace_service.context_count == 1
    headers = {"Origin":ORIGIN,"X-CSRF-Token":client.get("/auth/session").json()["csrf_token"]}
    assert client.post("/auth/logout",headers=headers).status_code == 200
    assert app.state.cloud_workspace_service.context_count == 0
    assert client.get("/api/v1/cloud/status").status_code == 401
