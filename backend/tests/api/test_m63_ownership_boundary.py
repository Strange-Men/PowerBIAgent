"""Ephemeral test-only HTTP harness; production product gate stays closed."""
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from backend.app.auth.dependencies import require_principal
from backend.app.conversation.models import ConversationNotFoundError
from backend.app.main import create_app
from backend.app.memory.models import RuntimeDataMode
from backend.app.persistence.database import create_engine, create_session_factory
from backend.app.persistence.models import Base
from backend.app.persistence.ownership import PrincipalScopedRepositoryFactory
from backend.tests.api.test_auth_security import FakeIdentity, ORIGIN, config, login


def test_server_derives_owner_and_denies_idor_without_existence_oracle(tmp_path):
    identity = FakeIdentity()
    settings = config(persistence_database_path=str(tmp_path / "synthetic.db"))
    app = create_app(settings, identity_client=identity)
    native_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with native_lifespan(application):
            engine = create_engine(settings)
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                application.state.test_factory = PrincipalScopedRepositoryFactory(
                    create_session_factory(engine), tmp_path / "reports")
                yield
            finally:
                await engine.dispose()
    app.router.lifespan_context = lifespan

    async def resources(request: Request, principal=Depends(require_principal)):
        auth = request.app.state.auth_service
        return await request.app.state.test_factory.for_session(auth,
            request.cookies.get(auth.settings.auth_cookie_name), principal)

    class Creation(BaseModel):
        conversation_id: str
        model_config = ConfigDict(extra="forbid")

    @app.post("/m63-test/conversations")
    async def create(body: Creation, owned=Depends(resources)):
        await owned.history.record_failed(RuntimeDataMode.REAL, body.conversation_id,
            title="synthetic", error_type="synthetic")
        return {"created": True}

    @app.api_route("/m63-test/conversations/{cid}", methods=["GET", "PATCH", "DELETE", "POST"])
    async def lifecycle(cid: str, request: Request, owned=Depends(resources)):
        try:
            if request.method == "GET":
                await owned.history.get_history(RuntimeDataMode.REAL, cid, limit=10, after=None)
            elif request.method == "PATCH":
                await owned.history.rename(RuntimeDataMode.REAL, cid, "synthetic rename")
            elif request.method == "DELETE":
                await owned.history_service.delete(RuntimeDataMode.REAL, cid)
            else:
                await owned.history.archive(RuntimeDataMode.REAL, cid)
            return {"accessible": True}
        except ConversationNotFoundError:
            raise HTTPException(404, "resource_not_found") from None

    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/m63-test/conversations/a").status_code == 401
        assert login(client).status_code == 302
        def headers():
            return {"Origin": ORIGIN, "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"]}
        assert client.post("/m63-test/conversations", json={"conversation_id": "a"}, headers=headers()).status_code == 200
        assert client.get("/m63-test/conversations/a").status_code == 200
        assert client.post("/auth/logout", headers=headers()).status_code == 200
        identity.claim_changes = {"oid": str(UUID(int=4)), "sub": "synthetic-B"}
        assert login(client).status_code == 302
        for method in ("GET", "PATCH", "DELETE", "POST"):
            foreign = client.request(method, "/m63-test/conversations/a", headers=headers())
            missing = client.request(method, "/m63-test/conversations/unknown", headers=headers())
            assert foreign.status_code == missing.status_code == 404
            assert foreign.json() == missing.json()
        assert client.post("/m63-test/conversations", headers=headers(), json={
            "conversation_id": "b", "tenant_id": "spoof", "principal_id": "spoof"}).status_code == 422
        assert client.post("/m63-test/conversations", headers=headers(), json={"conversation_id": "a"}).status_code == 200
        assert client.delete("/m63-test/conversations/a", headers=headers()).status_code == 200
        assert client.post("/auth/logout", headers=headers()).status_code == 200
        identity.claim_changes = {}
        assert login(client).status_code == 302
        assert client.get("/m63-test/conversations/a").status_code == 200
        # Explicit assertions on native application routes (no test dependency).
        assert client.post("/api/v1/chat", headers=headers(), json={"message": "synthetic"}).status_code == 403
        assert app.state.turn_service is None
        assert app.state.conversation_history_service is None
        assert app.state.report_repository is None
    with TestClient(create_app(config()), base_url=ORIGIN) as native:
        assert native.get("/m63-test/conversations/a").status_code == 404
