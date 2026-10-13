"""M6.4 failure-first REST boundary; synthetic principals and HTTP only."""
import asyncio
from uuid import UUID

import httpx2
import pytest

from backend.app.auth.models import AuthFailure
from backend.app.auth.identity import CATALOG_SCOPES
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.cloud_catalog_transport import FabricCatalogTransport
from backend.tests.unit.test_fabric_iq_adapter import Identity, principal, settings
from backend.app.auth.service import AuthService

WS = str(UUID(int=11))
MODEL = str(UUID(int=10))


@pytest.fixture
def context():
    identity = Identity()
    identity.calls = []
    def token(context, principal, scopes):
        identity.calls.append((principal, scopes))
        return "SYNTHETIC_CATALOG_TOKEN"
    identity.delegated_token = token
    auth = AuthService(settings(powerbi_mode="fabric_iq"), identity)
    session = auth.sessions.create(principal(), object(), 3600)
    yield auth, session, identity
    auth.close()


def transport(context, handler, **kwargs):
    auth, session, _ = context
    return FabricCatalogTransport(auth, session.session_id, session.principal,
        http_transport=httpx2.MockTransport(handler), **kwargs)


@pytest.mark.asyncio
async def test_catalog_scope_is_exact_and_auth_owned(context):
    auth, session, identity = context
    assert auth.get_delegated_token(session.session_id, session.principal, CATALOG_SCOPES)
    assert identity.calls[-1] == (session.principal, CATALOG_SCOPES)
    for scopes in [(), ("https://graph.microsoft.com/User.Read",), CATALOG_SCOPES * 2]:
        with pytest.raises(AuthFailure):
            auth.get_delegated_token(session.session_id, session.principal, scopes)
    assert len(identity.calls) == 1


@pytest.mark.asyncio
async def test_pagination_reconstructs_fixed_path_and_requests_recursive(context):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer SYNTHETIC_CATALOG_TOKEN"
        if not request.url.params.get("continuationToken"):
            return httpx2.Response(200, json={"value": [{"id": MODEL}],
                "continuationToken": "opaque+/=", "continuationUri":
                f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/semanticModels?recursive=true&continuationToken=opaque%2B%2F%3D"})
        return httpx2.Response(200, json={"value": [{"id": str(UUID(int=12))}]})
    async with transport(context, handler) as rest:
        assert len(await rest.list_models(WS)) == 2
    assert len(requests) == 2
    assert all(r.url.params["recursive"] == "true" for r in requests)
    assert requests[-1].url.params["continuationToken"] == "opaque+/="
    assert all(scopes == CATALOG_SCOPES for _, scopes in context[2].calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", ["https://evil.invalid/steal", "http://api.fabric.microsoft.com/v1/workspaces",
    "https://api.fabric.microsoft.com.evil.invalid/v1/workspaces", "https://api.fabric.microsoft.com/v1/admin/workspaces",
    "https://user@api.fabric.microsoft.com/v1/workspaces", "https://api.fabric.microsoft.com/v1/workspaces#x",
    "https://api.fabric.microsoft.com/v1/workspaces?continuationToken=other"])
async def test_hostile_continuation_never_receives_token(context, uri):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json={"value": [], "continuationToken": "next", "continuationUri": uri})
    async with transport(context, handler) as rest:
        with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
            await rest.list_workspaces()
    assert len(requests) == len(context[2].calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"value": {}}, {"value": [1]},
    {"value": [], "continuationToken": 1}, {"value": [], "continuationUri": "https://evil.invalid"},
    {"value": [], "continuationToken": ""}, {"value": [], "error": {"code": "bad"}}])
async def test_malformed_page_fails_closed(context, body):
    async with transport(context, lambda _: httpx2.Response(200, json=body)) as rest:
        with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
            await rest.list_workspaces()


@pytest.mark.asyncio
async def test_loop_and_page_budget_are_bounded(context):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(200, json={"value": [], "continuationToken": "loop"})
    async with transport(context, handler, max_pages=3) as rest:
        with pytest.raises(PowerBIAdapterError, match="^CONTRACT_DRIFT$"):
            await rest.list_workspaces()
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(401,"AUTH_EXPIRED"), (403,"RESOURCE_NOT_ACCESSIBLE"),
    (404,"RESOURCE_NOT_ACCESSIBLE"), (429,"RATE_LIMITED"), (503,"UPSTREAM_UNAVAILABLE"), (302,"CONTRACT_DRIFT")])
async def test_status_errors_are_safe_and_never_follow_redirects(context, status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(status, headers={"Location":"https://evil.invalid", "Retry-After":"999"},
            text="SENSITIVE_UPSTREAM_RESPONSE")
    async with transport(context, handler) as rest:
        with pytest.raises((AuthFailure, PowerBIAdapterError), match=f"^{code}$"):
            await rest.list_workspaces()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_429_retry_after_then_success_and_retry_cap(context):
    waits, calls = [], []
    async def sleep(seconds): waits.append(seconds)
    def handler(request):
        calls.append(request)
        return httpx2.Response(429, headers={"Retry-After":"2"}) if len(calls) < 3 else httpx2.Response(200, json={"value":[]})
    async with transport(context, handler, sleep=sleep) as rest:
        assert await rest.list_workspaces() == []
    assert waits == [2,2] and len(calls) == 3


@pytest.mark.asyncio
async def test_logout_during_response_discards_catalog(context):
    auth, session, _ = context
    def handler(request):
        auth.logout(session.session_id, None)
        return httpx2.Response(200, json={"value":[{"id":WS}]})
    async with transport(context, handler) as rest:
        with pytest.raises(AuthFailure): await rest.list_workspaces()


@pytest.mark.asyncio
async def test_foreign_principal_and_invalid_workspace_rejected_before_http(context):
    auth, session, identity = context
    with pytest.raises(AuthFailure):
        FabricCatalogTransport(auth, session.session_id, session.principal.model_copy(update={"principal_id":str(UUID(int=99))}))
    async with transport(context, lambda _: pytest.fail("No request allowed")) as rest:
        with pytest.raises(PowerBIAdapterError): await rest.list_models("../admin")
    assert identity.calls == []


@pytest.mark.asyncio
async def test_timeout_and_cancellation_are_distinct(context):
    def timeout(request): raise httpx2.ReadTimeout("SENSITIVE", request=request)
    async with transport(context, timeout) as rest:
        with pytest.raises(PowerBIAdapterError, match="^QUERY_TIMEOUT$"): await rest.list_workspaces()
    def cancel(request): raise asyncio.CancelledError()
    async with transport(context, cancel) as rest:
        with pytest.raises(asyncio.CancelledError): await rest.list_workspaces()


@pytest.mark.asyncio
async def test_page_item_budgets_and_persistent_429(context):
    calls = []
    def pages(request):
        calls.append(request)
        return httpx2.Response(200,json={"value":[],"continuationToken":str(len(calls))})
    async with transport(context,pages,max_pages=3) as rest:
        with pytest.raises(PowerBIAdapterError): await rest.list_workspaces()
    assert len(calls) == 3
    async with transport(context,lambda _: httpx2.Response(200,json={"value":[{},{}]}),max_items=1) as rest:
        with pytest.raises(PowerBIAdapterError): await rest.list_workspaces()
    calls.clear()
    waits = []
    async def sleep(seconds): waits.append(seconds)
    def limited(request):
        calls.append(request)
        return httpx2.Response(429,headers={"Retry-After":"0"})
    async with transport(context,limited,sleep=sleep) as rest:
        with pytest.raises(PowerBIAdapterError,match="^RATE_LIMITED$"): await rest.list_workspaces()
    assert len(calls) == 3 and waits == [0,0]


@pytest.mark.asyncio
async def test_report_listing_uses_same_authorization_and_folder_recursion(context):
    def handler(request):
        assert str(request.url).startswith(f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/reports?")
        assert request.url.params["recursive"] == "true"
        return httpx2.Response(200,json={"value":[]})
    async with transport(context,handler) as rest:
        assert await rest.list_reports(WS) == []


@pytest.mark.asyncio
async def test_expired_and_epoch_changed_session_fail_before_token(context):
    auth,session,identity = context
    rest = transport(context,lambda _: pytest.fail("No request allowed"))
    session.expires_at = 0
    try:
        with pytest.raises(AuthFailure): await rest.list_workspaces()
    finally: await rest.aclose()
    assert not identity.calls
