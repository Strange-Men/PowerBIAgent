"""Prepared product services reuse M5 and M6.3; synthetic storage only."""
import pytest

from backend.app.application.cloud_product_services import CloudProductServiceFactory
from backend.app.application.deepseek_turn_service import LLMTurnService
from backend.app.auth.models import AuthFailure
from backend.app.llm.factory import build_llm_registry
from backend.app.memory.models import RuntimeDataMode, StructuredWorkMemory
from backend.tests.unit.persistence.test_m63_ownership import factory  # noqa: F401
from backend.tests.unit.test_fabric_iq_adapter import harness, principal  # noqa: F401
from backend.tests.unit.test_cloud_workspace_service import workspace


@pytest.mark.asyncio
async def test_owned_history_and_report_reads_do_not_require_a_selected_model(harness, factory):
    from backend.tests.unit.persistence.test_m63_ownership import snapshot, seed_report
    from backend.app.conversation.models import ConversationNotFoundError
    from backend.app.report.resources import ReportNotFoundError
    auth, a, transport, _ = harness
    ws = workspace(harness)
    registry = build_llm_registry(auth.settings)
    services = CloudProductServiceFactory(auth, ws, factory, registry, registry)
    b = auth.sessions.create(principal(4), object(), 3600)
    owner = await factory.for_session(auth, a.session_id, a.principal)
    await owner.snapshots.save(snapshot('owned-read', 'owned-conversation'), RuntimeDataMode.REAL)
    artifact = await seed_report(owner, conversation='owned-conversation')
    before = len(transport.calls)
    try:
        # Tightened product replay now refuses native Real before storage.
        for operation in [lambda:services.list_history(a.session_id,a.principal,limit=10),
            lambda:services.read_history(a.session_id,a.principal,'owned-conversation',limit=10),
            lambda:services.read_report(a.session_id,a.principal,artifact.report_id)]:
            with pytest.raises(AuthFailure): await operation()
        page = await owner.history_service.list_recent(RuntimeDataMode.REAL, limit=10)
        assert [item.conversation_id for item in page.items] == ['owned-conversation']
        history = await owner.history_service.get_history(RuntimeDataMode.REAL, 'owned-conversation', limit=10)
        assert 'owned-read' in {item.request_id for item in history.items}
        assert (await owner.reports.read_html(artifact.report_id))[0].report_id == artifact.report_id
        other=await factory.for_session(auth,b.session_id,b.principal)
        assert not (await other.history_service.list_recent(RuntimeDataMode.REAL,limit=10)).items
        with pytest.raises(ConversationNotFoundError):
            await other.history_service.get_history(RuntimeDataMode.REAL, 'owned-conversation', limit=10)
        with pytest.raises(ReportNotFoundError):
            await other.reports.read_html(artifact.report_id)
        with pytest.raises(AuthFailure):
            await services.list_history(a.session_id, b.principal, limit=10)
        assert len(transport.calls) == before
        assert ws.status(a.session_id, a.principal).selected_model_key is None
    finally:
        await ws.aclose(); await registry.aclose()


@pytest.mark.asyncio
async def test_logout_after_owned_history_read_discards_completed_response(harness, factory, monkeypatch):
    from backend.app.application.conversation_history_service import ConversationHistoryService
    auth, session, _, _ = harness
    ws = workspace(harness)
    registry = build_llm_registry(auth.settings)
    services = CloudProductServiceFactory(auth, ws, factory, registry, registry)
    original = ConversationHistoryService.list_recent
    async def logout_after_read(service, *args, **kwargs):
        result = await original(service, *args, **kwargs)
        auth.logout(session.session_id, None)
        return result
    monkeypatch.setattr(ConversationHistoryService, 'list_recent', logout_after_read)
    try:
        with pytest.raises(AuthFailure):
            await services.list_history(session.session_id, session.principal, limit=10)
    finally:
        await ws.aclose(); await registry.aclose()


@pytest.mark.asyncio
async def test_composition_reuses_native_pipeline_and_owner_repositories(harness, factory):
    auth, a, transport, _ = harness
    ws = workspace(harness)
    registry = build_llm_registry(auth.settings)
    services = CloudProductServiceFactory(auth, ws, factory, registry, registry)
    b = auth.sessions.create(principal(4), object(), 3600)
    try:
        bundles = []
        for session in (a, b):
            catalog = await ws.catalog(session.session_id, session.principal)
            await ws.select(session.session_id, session.principal, catalog.items[0].key)
            bundles.append(await services.prepare(session.session_id, session.principal))
        first, second = bundles
        assert isinstance(first.turn_service, LLMTurnService)
        assert first.repositories.owner_scope.owner_id != second.repositories.owner_scope.owner_id
        await first.repositories.memory.create_pending(StructuredWorkMemory(
            request_id="synthetic-a", conversation_id=first.conversation_id), RuntimeDataMode.REAL)
        assert await second.repositories.memory.get_by_request_id("synthetic-a", RuntimeDataMode.REAL) is None
        before = len(transport.calls)
        with pytest.raises(AuthFailure):
            await first.execute("synthetic", request_id="must-not-run")
        assert len(transport.calls) == before
        assert await first.repositories.memory.get_by_request_id("must-not-run", RuntimeDataMode.REAL) is None
    finally:
        await ws.aclose(); await registry.aclose()


@pytest.mark.asyncio
async def test_native_composed_service_direct_call_cannot_bypass_disclosure_gate(harness,factory,monkeypatch):
    """Embedding the prepared service must not bypass the HTTP/prepared gate."""
    auth,session,transport,_ = harness
    ws = workspace(harness)
    registry = build_llm_registry(auth.settings)
    services = CloudProductServiceFactory(auth,ws,factory,registry,registry)
    called = []
    async def forbidden_core(*args,**kwargs):
        called.append(True)
        raise AssertionError('native core must not see unapproved data')
    monkeypatch.setattr(LLMTurnService,'execute',forbidden_core)
    try:
        catalog = await ws.catalog(session.session_id,session.principal)
        await ws.select(session.session_id,session.principal,catalog.items[0].key)
        prepared = await services.prepare(session.session_id,session.principal)
        before = len(transport.calls)
        with pytest.raises(AuthFailure):
            await prepared.turn_service.execute('SYNTHETIC_PRIVATE_MARKER',
                conversation_id=prepared.conversation_id,request_id='unapproved-native',
                semantic_model_key=prepared.semantic_model_key)
        assert not called and len(transport.calls)==before
        assert await prepared.repositories.memory.get_by_request_id('unapproved-native',RuntimeDataMode.REAL) is None
    finally:
        await ws.aclose(); await registry.aclose()


@pytest.mark.asyncio
async def test_late_prepare_cannot_restore_invalidated_selection(harness, factory, monkeypatch):
    """A pending service composition must not revive a revoked catalog epoch."""
    auth, session, _, _ = harness
    ws = workspace(harness)
    registry = build_llm_registry(auth.settings)
    services = CloudProductServiceFactory(auth, ws, factory, registry, registry)
    try:
        catalog = await ws.catalog(session.session_id, session.principal)
        await ws.select(session.session_id, session.principal, catalog.items[0].key)
        original_select = ws.select
        async def intervening_refresh(sid, principal, key, **kwargs):
            from backend.tests.unit.test_cloud_workspace_service import RestContext
            original_workspaces = RestContext.workspaces
            monkeypatch.setattr(RestContext, "workspaces", [])
            await ws.catalog(sid, principal)
            monkeypatch.setattr(RestContext, "workspaces", original_workspaces)
            await ws.catalog(sid, principal)
            return await original_select(sid, principal, key, **kwargs)
        monkeypatch.setattr(ws, "select", intervening_refresh)
        with pytest.raises(ValueError, match="^cloud_selection_changed$"):
            await services.prepare(session.session_id, session.principal)
        assert ws.status(session.session_id, session.principal).selected_model_key is None
    finally:
        await ws.aclose(); await registry.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidate", ["logout", "catalog_revoked"])
async def test_logout_or_selection_invalidation_prevents_repository_writes(harness, factory, monkeypatch, invalidate):
    auth, session, _, _ = harness
    ws = workspace(harness)
    registry = build_llm_registry(auth.settings)
    services = CloudProductServiceFactory(auth, ws, factory, registry, registry)
    try:
        catalog = await ws.catalog(session.session_id, session.principal)
        await ws.select(session.session_id, session.principal, catalog.items[0].key)
        prepared = await services.prepare(session.session_id, session.principal)
        if invalidate == "logout":
            auth.logout(session.session_id, None)
        else:
            from backend.tests.unit.test_cloud_workspace_service import RestContext
            monkeypatch.setattr(RestContext, "workspaces", [])
            await ws.catalog(session.session_id, session.principal)
        with pytest.raises(AuthFailure):
            await prepared.repositories.memory.create_pending(StructuredWorkMemory(
                request_id="late", conversation_id=prepared.conversation_id), RuntimeDataMode.REAL)
    finally:
        await ws.aclose(); await registry.aclose()


@pytest.mark.asyncio
async def test_native_relogin_preserves_owner_history_but_not_session_model_binding(harness, factory):
    from backend.tests.unit.persistence.test_m63_ownership import snapshot, seed_report
    from backend.app.conversation.models import ConversationNotFoundError
    from backend.app.report.resources import ReportNotFoundError
    auth, a, _, _ = harness
    ws = workspace(harness)
    registry = build_llm_registry(auth.settings)
    services = CloudProductServiceFactory(auth, ws, factory, registry, registry)
    async def prepare(session):
        catalog = await ws.catalog(session.session_id, session.principal)
        await ws.select(session.session_id, session.principal, catalog.items[0].key)
        return await services.prepare(session.session_id, session.principal)
    try:
        first = await prepare(a)
        await first.repositories.snapshots.save(snapshot("a-history", first.conversation_id), RuntimeDataMode.REAL)
        artifact = await seed_report(first.repositories, conversation=first.conversation_id)
        auth.logout(a.session_id, None)
        await ws.prune()
        b = auth.sessions.create(principal(4), object(), 3600)
        second = await prepare(b)
        with pytest.raises(ConversationNotFoundError):
            await second.repositories.history_service.get_history(RuntimeDataMode.REAL, first.conversation_id, limit=10)
        with pytest.raises(ReportNotFoundError):
            await second.repositories.reports.read_html(artifact.report_id)
        returned_a = auth.sessions.create(a.principal, object(), 3600)
        assert ws.status(returned_a.session_id, returned_a.principal).selected_model_key is None
        returned = await prepare(returned_a)
        assert returned.semantic_model_key != first.semantic_model_key
        assert returned.conversation_id != first.conversation_id
        history = await returned.repositories.history_service.get_history(RuntimeDataMode.REAL, first.conversation_id, limit=10)
        assert "a-history" in {item.request_id for item in history.items}
        assert (await returned.repositories.reports.read_html(artifact.report_id))[0].report_id == artifact.report_id
        with pytest.raises(AuthFailure):
            await first.repositories.snapshots.get("a-history", RuntimeDataMode.REAL)
        assert not ws.status(returned_a.session_id, returned_a.principal).execution_ready
    finally:
        await ws.aclose(); await registry.aclose()
