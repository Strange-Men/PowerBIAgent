"""Native IQ synthetic wire with normal product authorization and lazy catalog."""
from types import SimpleNamespace

import pytest

from backend.app.application.cloud_workspace_service import CloudWorkspaceService
from backend.app.auth.models import AuthFailure
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.app.powerbi.fabric_iq_contract import fail
from backend.tests.unit.test_fabric_iq_adapter import harness, WORKSPACE, MODEL  # noqa: F401
from backend.tests.unit.persistence.test_m63_ownership import factory  # noqa: F401


class REST:
    def __init__(self): self.removed = False; self.calls = []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def catalog_page(self, path, continuation=None):
        self.calls.append(path)
        if path == '/workspaces': return [{'id': WORKSPACE, 'displayName': 'Workspace'}], None
        return [{'id': MODEL, 'workspaceId': WORKSPACE, 'displayName': 'Model', 'type': 'SemanticModel'}], None
    async def verify_resource(self, ws, item=None, kind=None):
        self.calls.append((ws, item, kind))
        if self.removed: raise fail('RESOURCE_NOT_ACCESSIBLE')
        assert ws == WORKSPACE and item in {None, MODEL}


def service(harness):
    auth, session, transport, _ = harness
    rest = REST()
    factory = FabricIQAdapterFactory(auth.settings, auth, transport_factory=lambda *args: transport)
    return CloudWorkspaceService(auth, factory, rest_factory=lambda *args: rest), rest


@pytest.mark.asyncio
async def test_normal_catalog_does_not_bind_then_exact_selection_allows_query_only(harness):
    auth, session, transport, _ = harness
    workspace, rest = service(harness)
    sid, p = session.session_id, session.principal
    try:
        catalog = await workspace.catalog(sid, p)
        assert catalog.product_mode and not catalog.items
        assert transport.calls == []
        page = await workspace.browse(sid, p)
        resources = await workspace.browse(sid, p, workspace_key=page.items[0].key, kind='SemanticModel')
        assert transport.calls == []
        selected = await workspace.select(sid, p, resources.items[0].key, expected_generation=0)
        assert selected.execution_ready and selected.generation == 1
        workspace.require_execution(sid, p)
        for operation, reason in ((workspace.require_disclosure, 'cloud_disclosure_blocked'),
                                  (workspace.require_persistence, 'cloud_persistence_blocked')):
            with pytest.raises(AuthFailure) as caught: operation(sid, p)
            assert caught.value.denial_reason == reason
        assert auth.settings.fabric_test_allowlist is None
        assert (WORKSPACE, MODEL, 'SemanticModel') in rest.calls
    finally: await workspace.aclose()


@pytest.mark.asyncio
async def test_resource_removed_after_catalog_cannot_select(harness):
    _, session, transport, _ = harness
    workspace, rest = service(harness)
    sid, p = session.session_id, session.principal
    try:
        page = await workspace.browse(sid, p)
        resources = await workspace.browse(sid, p, workspace_key=page.items[0].key, kind='SemanticModel')
        rest.removed = True
        with pytest.raises(Exception, match='RESOURCE_NOT_ACCESSIBLE'):
            await workspace.select(sid, p, resources.items[0].key, expected_generation=0)
        assert transport.calls == []
        assert not workspace.status(sid, p).execution_ready
    finally: await workspace.aclose()


@pytest.mark.asyncio
async def test_long_running_commit_rechecks_microsoft_and_rolls_back(harness, factory):
    from backend.app.application.cloud_product_services import _SelectionLease
    auth, session, _, _ = harness
    auth.settings.allow_external_llm_disclosure = auth.settings.allow_business_persistence = True
    workspace, rest = service(harness)
    sid, p = session.session_id, session.principal
    try:
        page = await workspace.browse(sid, p)
        resources = await workspace.browse(sid, p, workspace_key=page.items[0].key, kind='SemanticModel')
        selected = await workspace.select(sid, p, resources.items[0].key, expected_generation=0)
        binding = await workspace.bound_projection(sid, p)
        lease = _SelectionLease(auth, workspace, sid, p, selected)
        repositories = await factory.for_session(lease, sid, p)
        rest.removed = True  # Microsoft revokes while a long analysis is running.
        with pytest.raises(Exception): await repositories.cloud_bindings.save(binding)
        # Inspect only this synthetic owner through the native test factory;
        # the revoked product lease itself must no longer read resources.
        inspected = await factory.for_session(auth, sid, p)
        assert await inspected.cloud_bindings.get(binding.conversation_id) is None
    finally: await workspace.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['removed', 'schema_drift', 'policy_revoke', 'stale_generation'])
async def test_selected_product_binding_failures_are_closed(harness, case):
    from backend.app.application.cloud_product_services import _SelectionLease
    auth, session, transport, _ = harness
    auth.settings.allow_external_llm_disclosure = auth.settings.allow_business_persistence = True
    workspace, rest = service(harness)
    sid, p = session.session_id, session.principal
    try:
        page = await workspace.browse(sid, p)
        resources = await workspace.browse(sid, p, workspace_key=page.items[0].key, kind='SemanticModel')
        selected = await workspace.select(sid, p, resources.items[0].key, expected_generation=0)
        lease = _SelectionLease(auth, workspace, sid, p, selected)
        if case == 'removed': rest.removed = True
        if case == 'schema_drift': transport.schema['schema']['Tables'][0]['Columns'][0]['Name'] = 'Changed'
        if case == 'policy_revoke': auth.settings.allow_external_llm_disclosure = False
        if case == 'stale_generation': await workspace.new_chat(sid, p, selected.generation)
        with pytest.raises(Exception): await lease.revalidate_resource()
        if case in {'removed', 'schema_drift'}:
            assert not workspace.status(sid, p).execution_ready
        assert not any(name == 'ExecuteQuery' for name, _ in transport.calls)
    finally: await workspace.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('source_mode', ['real', 'mock'])
async def test_owned_history_summary_before_selection_has_no_iq_fanout(harness, factory, source_mode):
    from backend.app.application.cloud_product_services import CloudProductServiceFactory
    from backend.app.memory.models import RuntimeDataMode, StructuredWorkMemory
    from backend.app.persistence.cloud_bindings import CloudConversationBinding
    auth, session, transport, _ = harness
    auth.settings.allow_business_persistence = True
    workspace, rest = service(harness)
    sid, p = session.session_id, session.principal
    repos = await factory.for_session(auth, sid, p)
    await repos.memory.create_pending(StructuredWorkMemory(request_id='summary-request',
        conversation_id='summary-conversation'), RuntimeDataMode.REAL)
    await repos.cloud_bindings.save(CloudConversationBinding(conversation_id='summary-conversation',
        model_key='server-owned-model', workspace_id=WORKSPACE, model_id=MODEL,
        schema_fingerprint='a'*64, source_mode=source_mode))
    product = CloudProductServiceFactory(auth, workspace, factory, None, None)
    try:
        if source_mode == 'mock':
            with pytest.raises(AuthFailure): await product.list_history(sid, p, limit=20)
        else:
            page = await product.list_history(sid, p, limit=20)
            assert len(page.items) == 1
            assert (WORKSPACE, MODEL, 'SemanticModel') in rest.calls
            rest.removed = True
            with pytest.raises(Exception, match='RESOURCE_NOT_ACCESSIBLE'):
                await product.list_history(sid, p, limit=20)
        assert transport.calls == []
        assert workspace.status(sid, p).selected_model_key is None
    finally: await workspace.aclose()


@pytest.mark.asyncio
async def test_iq_permission_revoke_clears_product_selection_status(harness):
    from backend.app.schemas.data_contracts import DAXRequest
    from backend.app.powerbi.base import PowerBIAdapterError
    _, session, transport, _ = harness
    workspace, _ = service(harness)
    sid, p = session.session_id, session.principal
    try:
        page = await workspace.browse(sid, p)
        resources = await workspace.browse(sid, p, workspace_key=page.items[0].key)
        selected = await workspace.select(sid, p, resources.items[0].key, expected_generation=0)
        adapter, _ = workspace.selected_context(sid, p)
        transport.query = {'Error': {'HttpStatusCode': 403}}
        with pytest.raises(PowerBIAdapterError):
            await adapter.execute_dax(DAXRequest(semantic_model_key=selected.selected_model_key,
                dax='EVALUATE ROW("probe",1)'))
        status = workspace.status(sid, p)
        assert not status.execution_ready
        assert status.selected_model_key is None and status.conversation_id is None
        assert status.generation > selected.generation
    finally: await workspace.aclose()
