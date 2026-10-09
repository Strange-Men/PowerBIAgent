"""Real MCP SDK against an in-memory HTTP peer, including auth on every frame."""
import asyncio
import json
import logging

import httpx2
import pytest

from backend.app.auth.models import AuthFailure
from backend.app.auth.service import AuthService
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_transport import FabricIQTransport
from backend.tests.unit.test_fabric_iq_adapter import Identity, principal, result, settings, tools


class Peer:
    def __init__(self):
        self.frames = []
        self.status = None
        self.inventory = tools()
        self.closed = False
        self.tool_error = False

    async def handle(self, request):
        assert request.headers["Authorization"] == "Bearer SYNTHETIC_DELEGATED_TOKEN"
        assert request.headers["X-Variants"] == "Fabric.Routing.FabricIQ.V1"
        assert str(request.url) == "https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq"
        if self.status:
            return httpx2.Response(self.status, headers={"location": "https://evil.invalid/stolen"})
        if request.method == "DELETE":
            self.closed = True
            return httpx2.Response(200)
        if request.method == "GET": return httpx2.Response(405)
        frame = json.loads(request.content)
        self.frames.append(frame["method"])
        if "id" not in frame: return httpx2.Response(202)
        if frame["method"] == "initialize":
            data = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                    "serverInfo": {"name": "synthetic-fabric", "version": "1"}}
        elif frame["method"] == "tools/list": data = {"tools": self.inventory}
        elif frame["method"] == "tools/call":
            data = ({"isError": True, "content": [{"type": "text", "text": "Synthetic invalid DAX private detail"}]}
                    if self.tool_error else {"content": [{"type": "text", "text": json.dumps(result())}]})
        else: raise AssertionError(frame["method"])
        return httpx2.Response(200, json={"jsonrpc": "2.0", "id": frame["id"], "result": data},
                               headers={"Mcp-Session-Id": "synthetic-session"})


def transport(peer, identity=None):
    config = settings(powerbi_mode="fabric_iq")
    auth = AuthService(config, identity or Identity())
    record = auth.sessions.create(principal(), object(), 3600)
    return FabricIQTransport(config, auth, record.session_id, record.principal,
                             http_transport=httpx2.MockTransport(peer.handle)), auth, record


@pytest.mark.asyncio
async def test_official_sdk_initialize_list_call_headers_close_and_safe_evidence(caplog):
    peer = Peer()
    client, _, _ = transport(peer)
    with caplog.at_level(logging.DEBUG):
        async with client.connection() as connection:
            await connection.call("ExecuteQuery", {"artifactId": "synthetic", "daxQueries": ['EVALUATE ROW("secret-business",1)'], "maxRows": 5})
    assert peer.frames.count("initialize") == peer.frames.count("tools/list") == peer.frames.count("tools/call") == 1
    assert peer.closed
    assert client.capability_evidence["client_version"] == "2.0.0"
    assert len(client.capability_evidence["fingerprint"]) == 64
    assert "SYNTHETIC_DELEGATED_TOKEN" not in caplog.text
    assert "secret-business" not in caplog.text
    await client.aclose()
    with pytest.raises(PowerBIAdapterError):
        async with client.connection(): pass


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(302, "UPSTREAM_UNAVAILABLE"), (401, "AUTH_EXPIRED"),
    (403, "RESOURCE_NOT_ACCESSIBLE"), (429, "RATE_LIMITED"), (503, "UPSTREAM_UNAVAILABLE")])
async def test_status_safe_failure_no_redirect_no_query_retry(status, code):
    peer = Peer()
    peer.status = status
    client, _, _ = transport(peer)
    with pytest.raises((PowerBIAdapterError, AuthFailure)) as captured:
        async with client.connection(): pass
    assert str(captured.value) == code
    assert peer.frames == []


@pytest.mark.asyncio
async def test_token_failure_prevents_any_mcp_request():
    peer, identity = Peer(), Identity()
    identity.token_error = AuthFailure("AUTH_CONSENT_REQUIRED")
    client, auth, record = transport(peer, identity)
    with pytest.raises(AuthFailure, match="AUTH_CONSENT_REQUIRED"):
        async with client.connection(): pass
    assert peer.frames == []
    assert auth.sessions.lookup(record.session_id)[0] is None


@pytest.mark.asyncio
async def test_logout_during_inflight_result_denied_and_teardown():
    peer = Peer()
    client, auth, record = transport(peer)
    with pytest.raises(AuthFailure):
        async with client.connection() as connection:
            auth.logout(record.session_id, None)
            await connection.call("ExecuteQuery", {"artifactId": "synthetic", "daxQueries": ["EVALUATE bad"], "maxRows": 5})
    assert "tools/call" not in peer.frames


@pytest.mark.asyncio
async def test_missing_capability_never_calls_query():
    peer = Peer()
    peer.inventory.pop()
    client, _, _ = transport(peer)
    with pytest.raises(PowerBIAdapterError, match="CONTRACT_DRIFT"):
        async with client.connection(): pytest.fail("must not yield")
    assert "tools/call" not in peer.frames
    assert peer.closed


@pytest.mark.asyncio
async def test_cleanup_auth_failure_keeps_primary_typed_failure():
    from backend.app.powerbi.fabric_iq_contract import fail
    peer = Peer()
    client, auth, record = transport(peer)
    with pytest.raises(PowerBIAdapterError, match="QUERY_REJECTED"):
        async with client.connection():
            auth.logout(record.session_id, None)
            raise fail("QUERY_REJECTED")


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, "", "invalid whitespace"])
async def test_invalid_token_broker_output_never_reaches_wire(token):
    class InvalidIdentity(Identity):
        def delegated_token(self, context, principal, scopes): return token
    peer = Peer()
    client, _, _ = transport(peer, InvalidIdentity())
    with pytest.raises(AuthFailure, match="AUTH_EXPIRED"):
        async with client.connection(): pass
    assert peer.frames == []


@pytest.mark.asyncio
async def test_sdk_tool_error_is_query_rejected_without_raw_detail_or_retry():
    from backend.app.powerbi.fabric_iq_normalization import normalize_query
    from backend.app.schemas.data_contracts import DAXRequest
    peer = Peer()
    peer.tool_error = True
    client, _, _ = transport(peer)
    with pytest.raises(PowerBIAdapterError, match="^QUERY_REJECTED$"):
        async with client.connection() as connection:
            raw = await connection.call("ExecuteQuery", {"artifactId": "synthetic", "daxQueries": ["EVALUATE bad"], "maxRows": 2})
            normalize_query(raw, "synthetic", DAXRequest(semantic_model_key="synthetic", dax="EVALUATE bad"))
    assert peer.frames.count("tools/call") == 1 and peer.closed
