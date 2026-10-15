"""Workspace is the operator boundary; new items need current-principal proof."""
from types import SimpleNamespace
import copy
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx2
import pytest

from backend.app.config.cloud_test_policy import CloudTestAllowlist, CloudTestPolicy
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.cloud_catalog_transport import FabricCatalogTransport
from backend.app.powerbi.fabric_iq_transport import FabricIQConnection
from backend.tests.unit.test_cloud_test_isolation import native, scoped_settings, WORKSPACE, MODEL, FOREIGN

NEW = str(UUID(int=777))


def test_workspace_scope_needs_no_model_or_report_list():
    scope = CloudTestAllowlist(workspaces=[{'workspace_id': WORKSPACE, 'query_execution': True}])
    policy = CloudTestPolicy(SimpleNamespace(fabric_test_mode=True, fabric_test_allowlist=scope))
    policy.model(WORKSPACE, NEW)
    policy.report(WORKSPACE, NEW)
    assert policy.capability(WORKSPACE, NEW, 'query_execution')
    assert not policy.capability(WORKSPACE, NEW, 'external_llm_disclosure')
    assert not policy.capability(FOREIGN, NEW, 'query_execution')


@pytest.mark.asyncio
async def test_new_workspace_items_are_paged_without_global_or_individual_enumeration():
    auth, session, _, adapter = native()
    paths = []
    def respond(request):
        paths.append(request.url.path)
        collection = request.url.path.rsplit('/', 1)[-1]
        kind = {'semanticModels': 'SemanticModel', 'reports': 'Report'}[collection]
        item_id = NEW if request.url.params.get('continuationToken') else MODEL
        body = {'value': [{'id': item_id, 'workspaceId': WORKSPACE,
            'type': kind, 'displayName': 'Synthetic item'}]}
        if item_id == MODEL: body['continuationToken'] = 'synthetic-next'
        return httpx2.Response(200, json=body)
    try:
        async with FabricCatalogTransport(auth, session.session_id, session.principal,
                http_transport=httpx2.MockTransport(respond)) as rest:
            for method in (rest.list_models, rest.list_reports):
                assert [row['id'] for row in await method(WORKSPACE)] == [MODEL, NEW]
        assert paths == [f'/v1/workspaces/{WORKSPACE}/semanticModels'] * 2 + [f'/v1/workspaces/{WORKSPACE}/reports'] * 2
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['list_models', 'list_reports'])
async def test_foreign_workspace_denied_before_token_and_http(method):
    auth, session, _, adapter = native()
    auth.get_delegated_token = Mock(side_effect=AssertionError('no token'))
    try:
        async with FabricCatalogTransport(auth, session.session_id, session.principal,
                http_transport=httpx2.MockTransport(lambda _: pytest.fail('no request'))) as rest:
            with pytest.raises(PowerBIAdapterError): await getattr(rest, method)(FOREIGN)
        auth.get_delegated_token.assert_not_called()
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('attack', ['foreign_row', 'foreign_continuation'])
async def test_foreign_collection_response_is_rejected_without_followup(attack):
    auth, session, _, adapter = native()
    calls = []
    def respond(request):
        calls.append(request.url.path)
        body = {'value': [{'id': NEW, 'workspaceId': FOREIGN if attack == 'foreign_row' else WORKSPACE,
            'type': 'SemanticModel', 'displayName': 'Synthetic'}]}
        if attack == 'foreign_continuation':
            body.update(continuationToken='next', continuationUri=
                f'https://api.fabric.microsoft.com/v1/workspaces/{FOREIGN}/semanticModels?continuationToken=next')
        return httpx2.Response(200, json=body)
    try:
        async with FabricCatalogTransport(auth, session.session_id, session.principal,
                http_transport=httpx2.MockTransport(respond)) as rest:
            with pytest.raises(PowerBIAdapterError, match='CONTRACT_DRIFT'): await rest.list_models(WORKSPACE)
        assert len(calls) == 1
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.parametrize('resource', [None, (FOREIGN, MODEL), (WORKSPACE, NEW)])
def test_iq_artifact_requires_exact_server_workspace_context(resource):
    policy = CloudTestPolicy(scoped_settings())
    with pytest.raises(PowerBIAdapterError):
        policy.iq_call('ExecuteQuery', {'artifactId': MODEL}, resource=resource)


def test_iq_new_model_context_is_allowed_but_resolve_cannot_change_workspace():
    policy = CloudTestPolicy(scoped_settings())
    context = (WORKSPACE, NEW)
    policy.iq_call('ExecuteQuery', {'artifactId': NEW}, resource=context)
    with pytest.raises(PowerBIAdapterError):
        policy.iq_call('ResolveFabricItem', {'fabricItemId':
            f'https://app.powerbi.com/groups/{FOREIGN}/datasets/{NEW}/details'}, resource=context)


@pytest.mark.asyncio
async def test_new_model_still_requires_exact_resolve_and_current_principal_schema():
    auth, session, wire, adapter = native()
    async def call(name, args):
        wire.calls.append((name, args))
        if name == 'ResolveFabricItem':
            return {'fabricItemId': NEW, 'workspaceId': WORKSPACE, 'itemType': 'SemanticModel'}
        result = copy.deepcopy(wire.schema)
        result['semanticModel']['ArtifactId'] = NEW
        return result
    wire.call = call
    try:
        ref = await adapter.bind_catalog_model(WORKSPACE, NEW)
        assert adapter.bound_resource_identity(ref.server_model_key) == (WORKSPACE, NEW)
        assert [name for name, _ in wire.calls] == ['ResolveFabricItem', 'GetSemanticModelSchema']
        wire.calls.clear()
        async def foreign_resolve(name, args):
            wire.calls.append((name, args))
            return {'fabricItemId': NEW, 'workspaceId': FOREIGN, 'itemType': 'SemanticModel'}
        wire.call = foreign_resolve
        with pytest.raises(PowerBIAdapterError): await adapter.bind_catalog_model(WORKSPACE, NEW)
        assert [name for name, _ in wire.calls] == ['ResolveFabricItem']
        assert adapter.binding_count == 0
        # A candidate is never enough to bypass Resolve's returned identity.
    finally:
        await adapter.aclose(); auth.close()


@pytest.mark.asyncio
async def test_iq_revocation_during_await_drops_result():
    config = scoped_settings()
    async def revoke(*args):
        config.fabric_test_allowlist = None
        return {'synthetic': 'must not return'}
    upstream = SimpleNamespace(call_tool=AsyncMock(side_effect=revoke))
    inventory = [{'name': 'ExecuteQuery', 'inputSchema': {'properties': {}}}]
    connection = FabricIQConnection(upstream, inventory, lambda: None, CloudTestPolicy(config),
        resource=(WORKSPACE, MODEL))
    with pytest.raises(PowerBIAdapterError): await connection.call('ExecuteQuery', {'artifactId': MODEL})
    upstream.call_tool.assert_awaited_once()
