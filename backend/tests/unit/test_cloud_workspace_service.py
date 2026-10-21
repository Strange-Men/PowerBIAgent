"""M6.4 native Auth/Adapter contracts; all HTTP and identities synthetic."""

import pytest

from backend.app.application.cloud_workspace_service import CloudWorkspaceService
from backend.app.auth.models import AuthFailure
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.tests.unit.test_cloud_catalog_binding import REST
from backend.tests.unit.test_fabric_iq_adapter import harness, principal  # noqa: F401


def workspace(harness, **kwargs):
    auth, session, transport, _ = harness
    # These legacy control-plane tests exercise acceptance-mode denial and
    # eager authorization. Normal product lazy selection has its own matrix.
    if auth.settings.fabric_test_allowlist is None:
        from backend.app.config.cloud_test_policy import CloudTestAllowlist
        from backend.tests.unit.test_fabric_iq_adapter import WORKSPACE
        auth.settings.fabric_test_mode = True
        auth.settings.fabric_test_allowlist = CloudTestAllowlist(workspaces=[{'workspace_id': WORKSPACE}])
    factory = FabricIQAdapterFactory(auth.settings, auth, transport_factory=lambda *args: transport)
    return CloudWorkspaceService(auth, factory, rest_factory=lambda *args: RestContext(), **kwargs)


class RestContext(REST):
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


@pytest.mark.asyncio
async def test_catalog_does_not_select_and_selected_key_is_revalidated(harness):
    auth, session, transport, _ = harness
    service = workspace(harness)
    try:
        catalog = await service.catalog(session.session_id, session.principal)
        assert service.status(session.session_id, session.principal).selected_model_key is None
        before = len(transport.calls)
        selection = await service.select(session.session_id, session.principal, catalog.items[0].key)
        assert selection.selected_model_key == catalog.items[0].key
        assert len(transport.calls) > before
        assert not selection.execution_ready
        again = await service.select(session.session_id, session.principal, catalog.items[0].key)
        assert again.conversation_id == selection.conversation_id
    finally: await service.aclose()


@pytest.mark.asyncio
async def test_foreign_key_and_spoofed_principal_never_get_authority(harness):
    auth, session, transport, _ = harness
    service = workspace(harness)
    b = auth.sessions.create(principal(4), object(), 3600)
    try:
        catalog = await service.catalog(session.session_id, session.principal)
        await service.catalog(b.session_id, b.principal)
        before = len(transport.calls)
        with pytest.raises(AuthFailure):
            await service.select(b.session_id, b.principal, catalog.items[0].key)
        with pytest.raises(AuthFailure):
            await service.catalog(session.session_id, b.principal)
        assert len(transport.calls) == before
    finally: await service.aclose()


@pytest.mark.asyncio
async def test_logout_discards_late_selection_and_purges_context(harness):
    auth, session, transport, _ = harness
    service = workspace(harness)
    try:
        catalog = await service.catalog(session.session_id, session.principal)
        original = transport.call
        async def late(name, args):
            raw = await original(name, args)
            auth.logout(session.session_id, None)
            return raw
        transport.call = late
        with pytest.raises(AuthFailure):
            await service.select(session.session_id, session.principal, catalog.items[0].key)
        await service.prune()
        assert service.context_count == 0
    finally: await service.aclose()


@pytest.mark.asyncio
async def test_execution_remains_closed_without_query_or_repository_activity(harness):
    auth, session, transport, _ = harness
    service = workspace(harness)
    try:
        catalog = await service.catalog(session.session_id, session.principal)
        await service.select(session.session_id, session.principal, catalog.items[0].key)
        before = len(transport.calls)
        with pytest.raises(AuthFailure, match="^AUTH_FORBIDDEN$"):
            service.require_execution(session.session_id, session.principal)
        assert len(transport.calls) == before
        assert not service.status(session.session_id, session.principal).execution_ready
    finally: await service.aclose()


@pytest.mark.asyncio
async def test_stale_selection_generation_cannot_override_newer_intent(harness):
    auth, session, transport, _ = harness
    service = workspace(harness)
    try:
        catalog = await service.catalog(session.session_id, session.principal)
        first = await service.select(session.session_id, session.principal, catalog.items[0].key, expected_generation=0)
        before = len(transport.calls)
        with pytest.raises(ValueError, match="^cloud_selection_changed$"):
            await service.select(session.session_id, session.principal, catalog.items[0].key, expected_generation=0)
        assert len(transport.calls) == before
        assert service.status(session.session_id, session.principal) == first
    finally: await service.aclose()


@pytest.mark.asyncio
async def test_catalog_deadline_includes_queue_without_mutating_active_selection(harness):
    import asyncio
    from backend.app.powerbi.base import PowerBIAdapterError
    auth, session, transport, _ = harness
    service = workspace(harness)
    try:
        catalog = await service.catalog(session.session_id, session.principal)
        selected = await service.select(session.session_id, session.principal, catalog.items[0].key)
        # Accelerated synthetic deadline; no production configuration or validator changes.
        auth.settings = auth.settings.model_copy(update={"request_timeout_seconds": 0.02})
        context = service._contexts[session.session_id]
        before = len(transport.calls)
        async with context.lock:
            with pytest.raises(PowerBIAdapterError, match="^QUERY_TIMEOUT$"):
                await asyncio.wait_for(service.catalog(session.session_id, session.principal), timeout=0.5)
            assert service.status(session.session_id, session.principal) == selected
        assert len(transport.calls) == before
    finally: await service.aclose()
