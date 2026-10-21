"""The browser can select metadata; it cannot assert authorization fields."""
import pytest

from backend.tests.api.test_cloud_control_plane import cloud  # noqa: F401
from backend.tests.api.test_auth_security import login, ORIGIN


@pytest.mark.parametrize('path', [
    '/catalog/workspaces?principal_id=forged',
    '/catalog/workspaces?query=a&query=b',
    '/catalog/resources?workspace_id=forged',
    '/catalog/resources?workspace_key=unknown&kind=SQLDatabase',
    '/catalog/resources?workspace_key=unknown&permission=read',
])
def test_catalog_rejects_forged_authority_and_ambiguous_query(cloud, path):
    client, app = cloud
    app.state.settings.fabric_test_mode = False
    assert client.get('/api/v1/cloud' + path).status_code == 401
    login(client)
    assert client.get('/api/v1/cloud' + path).status_code == 422
    assert client.get('/auth/session').status_code == 200


def test_product_unknown_candidate_and_workspace_are_closed_without_storage(cloud):
    client, app = cloud
    app.state.settings.fabric_test_mode = False
    login(client)
    csrf = client.get('/auth/session').json()['csrf_token']
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': csrf}
    assert client.get('/api/v1/cloud/catalog/resources?workspace_key=unknown').status_code == 403
    assert client.post('/api/v1/cloud/selection', headers=headers,
        json={'key':'forged-workspace/model-guid', 'expected_generation':0}).status_code == 403
    assert client.post('/api/v1/cloud/selection', headers=headers,
        json={'key':'forged', 'expected_generation':0, 'schema_fingerprint':'forged'}).status_code == 422
    assert app.state.cloud_product_services._repositories._engine is None
    assert client.get('/api/v1/cloud/status').json()['execution_ready'] is False


@pytest.mark.asyncio
async def test_disconnected_body_is_a_bounded_request_refusal():
    from fastapi import HTTPException
    from starlette.requests import ClientDisconnect
    from backend.app.api.cloud_routes import body_as, GenerationRequest
    class Disconnected:
        async def stream(self):
            yield b'{'
            raise ClientDisconnect()
    with pytest.raises(HTTPException) as caught:
        await body_as(Disconnected(), GenerationRequest)
    assert caught.value.status_code == 400
    assert caught.value.detail == 'invalid_cloud_request'


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path', [
    ('GET','/catalog/workspaces'), ('GET','/history'), ('GET','/reports/example'),
    ('GET','/reports/example/download'), ('POST','/selection'), ('POST','/chat'),
    ('POST','/new-chat'), ('POST','/restore'), ('POST','/presentations/example'),
    ('POST','/history/example/rename'),
])
async def test_http_disconnect_before_body_completion_has_zero_service_calls(method, path):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from fastapi import FastAPI
    from backend.app.api.cloud_routes import router
    from backend.app.auth.dependencies import require_principal
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_principal] = lambda: object()
    services = AsyncMock()
    app.state.cloud_workspace_service = app.state.cloud_product_services = services
    app.state.settings = SimpleNamespace(auth_cookie_name='synthetic')
    incoming = iter([{'type':'http.request','body':b'','more_body':True},
                     {'type':'http.disconnect'}])
    async def receive(): return next(incoming)
    sent = []
    async def send(message): sent.append(message)
    scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
        'method':method,'scheme':'http','path':'/api/v1/cloud'+path,'root_path':'',
        'query_string':b'','headers':[],'client':('127.0.0.1',1000),'server':('test',80)}
    await asyncio.wait_for(app(scope, receive, send), 2)
    assert sent[0]['type'] == 'http.response.start' and sent[0]['status'] == 400
    assert services.mock_calls == []  # No execution, Facts, Memory or resource mutation.


@pytest.mark.asyncio
async def test_bounded_body_preserves_async_cancellation():
    import asyncio
    from backend.app.api.cloud_routes import bounded_body
    class Cancelled:
        async def stream(self):
            yield b''
            raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError): await bounded_body(Cancelled(), 1024)
