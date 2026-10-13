"""Exact resource recovery, all identities/schema/storage synthetic."""
import pytest

from backend.app.auth.models import AuthFailure
from backend.app.application.cloud_product_services import CloudProductServiceFactory
from backend.tests.unit.persistence.test_m63_ownership import factory, snapshot  # noqa: F401
from backend.tests.unit.test_fabric_iq_adapter import harness, principal  # noqa: F401
from backend.tests.unit.test_cloud_workspace_service import workspace


@pytest.mark.asyncio
async def test_missing_persistent_binding_cannot_replay_owned_history(harness, factory):
    auth, a, _, _ = harness
    ws = workspace(harness)
    repos = await factory.for_session(auth, a.session_id, a.principal)
    await repos.snapshots.save(snapshot('legacy', 'legacy'), 'real')
    services = CloudProductServiceFactory(auth, ws, factory, None, None)
    try:
        with pytest.raises(AuthFailure):
            await services.read_history(a.session_id, a.principal, 'legacy', limit=10)
    finally:
        await ws.aclose()


@pytest.mark.asyncio
async def test_binding_repository_denies_foreign_owner_and_mutation(harness, factory):
    from backend.app.persistence.cloud_bindings import CloudConversationBinding
    from backend.tests.unit.test_fabric_iq_adapter import WORKSPACE, MODEL
    auth, a, _, _ = harness
    b = auth.sessions.create(principal(4), object(), 3600)
    ra = await factory.for_session(auth, a.session_id, a.principal)
    rb = await factory.for_session(auth, b.session_id, b.principal)
    binding = CloudConversationBinding(conversation_id='bound', model_key='fabric_iq:synthetic',
        workspace_id=WORKSPACE, model_id=MODEL, schema_fingerprint='a'*64, source_mode='real')
    await ra.cloud_bindings.save(binding)
    assert await rb.cloud_bindings.get('bound') is None
    assert await ra.cloud_bindings.get('bound') == binding
    with pytest.raises(AuthFailure):
        await ra.cloud_bindings.save(binding.model_copy(update={'model_id':__import__('uuid').UUID(int=999)}))


@pytest.mark.asyncio
async def test_native_business_service_gate_denies_before_repository_even_when_test_policy_disabled(harness):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    auth, a, _, _ = harness
    ws = workspace(harness)
    repos = SimpleNamespace(for_session=AsyncMock(side_effect=AssertionError('must not open')))
    services = CloudProductServiceFactory(auth, ws, repos, None, None)
    try:
        for operation in [services.list_history(a.session_id,a.principal,limit=10),
                          services.read_report(a.session_id,a.principal,'synthetic')]:
            with pytest.raises(AuthFailure): await operation
        repos.for_session.assert_not_awaited()
    finally:
        await ws.aclose()
