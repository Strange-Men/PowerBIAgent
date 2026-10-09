"""M6.1 fail-closed identity boundary; all identities are synthetic."""
from uuid import UUID

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from backend.app.auth.dependencies import require_principal
from backend.app.auth.identity import IdentityResult
from backend.app.auth.models import PrincipalContext
from backend.app.config.settings import Settings
from backend.app.main import create_app

TENANT = str(UUID(int=1))
CLIENT = str(UUID(int=2))
ORIGIN = "http://localhost:5173"


def config(**changes):
    values = dict(identity_mode="ENTRA_BFF", entra_tenant_id=TENANT,
                  entra_client_id=CLIENT, entra_client_secret="NOT_A_REAL_SECRET_AUTH",
                  auth_cookie_secure=False)
    return Settings(_env_file=None, **(values | changes))


class FakeIdentity:
    def __init__(self):
        self.claim_changes = {}
        self.destroyed = []
        self.error = None

    def initiate(self):
        return {"state": "synthetic-state", "nonce": "synthetic-nonce",
                "code_verifier": "synthetic-verifier", "auth_uri": "https://login.microsoftonline.com/authorize"}, object()

    def complete(self, flow, response, context):
        if self.error:
            raise self.error
        claims = {"tid": TENANT, "oid": str(UUID(int=3)), "sub": "synthetic-subject",
                  "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
                  "aud": CLIENT, "exp": 9999999999, "nbf": 0,
                  "name": "Test A", "preferred_username": "a@example.invalid"}
        claims.update(self.claim_changes)
        return IdentityResult(claims=claims, context=context)

    def destroy(self, context):
        self.destroyed.append(context)

    def delegated_token(self, context, principal, scopes):
        return "synthetic-access-value"


@pytest.fixture
def harness():
    identity = FakeIdentity()
    application = create_app(config(), identity_client=identity)
    @application.get("/test-principal")
    def principal(value=Depends(require_principal)):
        return {"name": value.display_name}
    with TestClient(application, base_url=ORIGIN) as client:
        yield client, application, identity


def login(client):
    assert client.get("/auth/login", follow_redirects=False).status_code == 302
    return client.get("/auth/callback?state=synthetic-state&code=synthetic-code", follow_redirects=False)


def failure(response, code):
    assert response.json()["failure"]["code"] == code


def test_missing_invalid_and_spoofed_identity(harness):
    c, _, _ = harness
    r = c.get("/test-principal", headers={"X-User-ID": "attacker"})
    assert r.status_code == 401
    failure(r, "AUTH_REQUIRED")
    c.cookies.set("pbiagent_session", "invalid")
    assert c.get("/test-principal").status_code == 401


def test_session_rotation_logout_csrf_origin_and_replay(harness):
    c, app, _ = harness
    login(c)
    old = c.cookies.get("pbiagent_session")
    login(c)
    assert c.cookies.get("pbiagent_session") != old
    assert app.state.auth_service.sessions.lookup(old)[0] is None
    session = c.get("/auth/session").json()
    assert session["authenticated"] is True
    assert c.post("/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
    headers = {"Origin": "https://evil.invalid", "X-CSRF-Token": session["csrf_token"]}
    assert c.post("/auth/logout", headers=headers).status_code == 403
    headers["Origin"] = ORIGIN
    sid = c.cookies.get("pbiagent_session")
    assert c.post("/auth/logout", headers=headers).status_code == 200
    c.cookies.set("pbiagent_session", sid)
    assert c.get("/test-principal").status_code == 401
    assert c.get("/auth/logout").status_code == 405


@pytest.mark.parametrize("case", ["state", "correlation", "expiry", "pkce", "nonce", "replay"])
def test_invalid_flow_denied(harness, case):
    c, app, _ = harness
    c.get("/auth/login", follow_redirects=False)
    correlation = c.cookies.get("pbiagent_flow")
    flow = app.state.auth_service.flows.peek(correlation)
    state = "synthetic-state"
    if case == "state": state = "wrong-state"
    if case == "correlation": c.cookies.clear()
    if case == "expiry": flow.expires_at = 0
    if case == "pkce": flow.payload.pop("code_verifier")
    if case == "nonce": flow.payload.pop("nonce")
    response = c.get(f"/auth/callback?state={state}&code=synthetic-code", follow_redirects=False)
    if case == "replay":
        assert response.status_code == 302
        c.cookies.set("pbiagent_flow", correlation)
        response = c.get("/auth/callback?state=synthetic-state&code=synthetic-code", follow_redirects=False)
    assert response.headers["location"] == "/"
    failure(c.get("/auth/session"), "AUTH_REQUIRED")


@pytest.mark.parametrize("claim,value", [("tid", str(UUID(int=4))), ("iss", "https://evil.invalid"),
    ("aud", "wrong"), ("exp", 0), ("sub", ""), ("oid", "")])
def test_claim_policy_denies_wrong_tenant_issuer_audience_expiry(harness, claim, value):
    c, _, identity = harness
    identity.claim_changes[claim] = value
    login(c)
    assert c.get("/auth/session").status_code == 401
    assert identity.destroyed


@pytest.mark.parametrize("target", ["https://evil.invalid", "//evil.invalid", "/%2f%2fevil.invalid", "/\\evil", "/auth/login", "/?code=bad"])
def test_unsafe_return_to(harness, target):
    c, _, _ = harness
    assert c.get("/auth/login", params={"return_to": target}).status_code == 400


def test_expiry_purges_token_context(harness):
    c, app, identity = harness
    login(c)
    sid = c.cookies.get("pbiagent_session")
    app.state.auth_service.sessions.peek(sid).expires_at = 0
    r = c.get("/auth/session")
    assert r.status_code == 401
    failure(r, "AUTH_EXPIRED")
    assert identity.destroyed


def test_all_existing_product_routes_fail_closed_before_dependencies(harness):
    c, app, _ = harness
    from backend.app.api.routes import router
    for signed_in in (False, True):
        if signed_in: login(c)
        for route in router.routes:
            if route.path.startswith("/api/"):
                for method in route.methods - {"HEAD", "OPTIONS"}:
                    r = c.request(method, route.path.replace("{conversation_id}", "synthetic").replace("{report_id}", "synthetic"))
                    assert r.status_code in (401, 403), (method, route.path, r.status_code)
    assert app.state.turn_service is None
    assert app.state.conversation_history_service is None
    assert app.state._persistence_engine is None


def test_parallel_principal_isolation(harness):
    _, app, _ = harness
    service = app.state.auth_service
    def create(name, oid):
        principal = PrincipalContext(tenant_id=TENANT, principal_id=oid, subject="s",
            issuer=f"https://login.microsoftonline.com/{TENANT}/v2.0", display_name=name,
            preferred_username=None, session_epoch=1, authorization_epoch=1)
        return service.sessions.create(principal, object(), 600)
    a, b = create("Test A", str(UUID(int=5))), create("Test B", str(UUID(int=6)))
    # Use one lifespan for both simultaneous request clients (no nested lifespan teardown).
    from httpx import ASGITransport, AsyncClient
    import asyncio
    async def parallel():
        async with AsyncClient(transport=ASGITransport(app), base_url=ORIGIN) as http:
            responses = await asyncio.gather(*[http.get("/test-principal", headers={"Cookie": f"pbiagent_session={r.session_id}"}) for r in [a, b] * 10])
        return [r.json()["name"] for r in responses]
    assert asyncio.run(parallel()) == ["Test A", "Test B"] * 10
    assert not hasattr(app.state, "current_user")


def test_safe_dto_cookie_headers_and_no_log_leak(harness, caplog):
    c, _, identity = harness
    response = login(c)
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert response.headers["referrer-policy"] == "no-referrer"
    session = c.get("/auth/session")
    assert set(session.json()) == {"identity_mode", "authenticated", "display_name", "preferred_username", "state", "csrf_token", "expires_in"}
    assert "no-store" in session.headers["cache-control"]
    assert TENANT not in session.text and CLIENT not in session.text
    identity.error = ValueError("synthetic-access-value NOT_A_REAL_SECRET_AUTH")
    login(c)
    assert "synthetic-access-value" not in caplog.text
    assert "NOT_A_REAL_SECRET_AUTH" not in caplog.text


@pytest.mark.parametrize("changes", [dict(auth_cookie_secure=False), dict(auth_cookie_secure=True)])
def test_production_rejects_insecure_or_inmemory(changes):
    with pytest.raises(ValueError):
        config(app_env="production", entra_redirect_uri="https://app.example.invalid/auth/callback",
               auth_allowed_origin="https://app.example.invalid", **changes)


def test_token_broker_is_principal_session_and_resource_bound(harness):
    c, app, identity = harness
    login(c)
    service = app.state.auth_service
    a = service.require_session(c.cookies.get("pbiagent_session"))
    identity.claim_changes = {"oid": str(UUID(int=10)), "name": "Test B"}
    # Separate browser does not rotate A's session.
    c.cookies.clear()
    login(c)
    b = service.require_session(c.cookies.get("pbiagent_session"))
    assert a.context is not b.context
    assert a.principal != b.principal
    assert service.get_delegated_token(a.session_id, a.principal) == "synthetic-access-value"
    from backend.app.auth.models import AuthFailure
    with pytest.raises(AuthFailure):
        service.get_delegated_token(a.session_id, b.principal)
    with pytest.raises(AuthFailure):
        service.get_delegated_token(a.session_id, a.principal, ("https://evil.invalid/read",))
    service.logout(a.session_id, None)
    assert service.require_session(b.session_id).principal == b.principal
    assert a.context is None
    with pytest.raises(AuthFailure):
        service.get_delegated_token(a.session_id, a.principal)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_uniform_unsafe_method_policy(harness, method):
    c, _, _ = harness
    login(c)
    session = c.get("/auth/session").json()
    assert c.request(method, "/api/v1/chat").status_code == 403
    assert c.request(method, "/api/v1/chat", headers={"Origin":ORIGIN,
        "X-CSRF-Token":session["csrf_token"]}).status_code == 403


def test_startup_error_never_renders_credential_input():
    with pytest.raises(ValueError) as caught:
        config(entra_tenant_id="invalid")
    assert "NOT_A_REAL_SECRET_AUTH" not in str(caught.value)


def test_periodic_prune_destroys_idle_expired_auth_state(harness):
    c, app, identity = harness
    c.get("/auth/login", follow_redirects=False)
    app.state.auth_service.flows.peek(c.cookies.get("pbiagent_flow")).expires_at = 0
    app.state.auth_service.prune()
    assert identity.destroyed
    assert not app.state.auth_service.flows.peek(c.cookies.get("pbiagent_flow"))
