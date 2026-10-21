"""Product REST pages and exact-resource proofs, synthetic HTTP only."""
import httpx2
import pytest

from backend.app.auth.identity import CATALOG_SCOPES, DELEGATED_SCOPES
from backend.app.powerbi.base import PowerBIAdapterError
from backend.tests.unit.test_cloud_catalog_transport import context, transport, WS, MODEL  # noqa: F401


@pytest.mark.asyncio
async def test_exact_resource_requests_existing_item_read_scopes(context):
    def respond(request):
        return httpx2.Response(200, json={'id': MODEL, 'workspaceId': WS,
            'displayName': 'Model', 'type': 'SemanticModel'})
    async with transport(context, respond) as rest:
        await rest.verify_resource(WS, MODEL, 'SemanticModel')
    assert context[2].calls[-1][1] == DELEGATED_SCOPES


@pytest.mark.asyncio
async def test_single_metadata_page_does_not_fetch_continuation(context):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx2.Response(200, json={'value': [{'id': WS, 'displayName': 'Workspace',
            'description': 'PRIVATE_METADATA_EXCLUDED'}], 'continuationToken': 'next'})
    async with transport(context, respond) as rest:
        rows, token = await rest.catalog_page('/workspaces')
    assert len(calls) == 1 and token == 'next'
    assert rows == [{'id': WS, 'displayName': 'Workspace'}]
    assert context[2].calls[-1][1] == CATALOG_SCOPES


@pytest.mark.asyncio
@pytest.mark.parametrize('uri', ['https://evil.invalid/steal',
    'https://api.fabric.microsoft.com/v1/admin/workspaces?continuationToken=next',
    'https://api.fabric.microsoft.com/v1/workspaces?continuationToken=other'])
async def test_metadata_continuation_cannot_change_authority(context, uri):
    async with transport(context, lambda _: httpx2.Response(200, json={
            'value': [], 'continuationToken': 'next', 'continuationUri': uri})) as rest:
        with pytest.raises(PowerBIAdapterError): await rest.catalog_page('/workspaces')
    assert len(context[2].calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/admin/workspaces', 'https://evil.invalid', '/workspaces/../admin'])
async def test_forged_metadata_path_rejected_before_token(context, path):
    async with transport(context, lambda _: pytest.fail('no HTTP')) as rest:
        with pytest.raises(PowerBIAdapterError): await rest.catalog_page(path)
    assert context[2].calls == []


@pytest.mark.asyncio
async def test_wrong_exact_identity_never_proves_access(context):
    async with transport(context, lambda _: httpx2.Response(200, json={
            'id': WS, 'workspaceId': WS, 'displayName': 'Other', 'type': 'SemanticModel'})) as rest:
        with pytest.raises(PowerBIAdapterError): await rest.verify_resource(WS, MODEL, 'SemanticModel')
