"""A report entry can only select its metadata-proven exact semantic model."""
import json
from uuid import UUID

import pytest

from backend.app.powerbi.base import PowerBIAdapterError
from backend.tests.unit.test_fabric_iq_adapter import harness, WORKSPACE, MODEL  # noqa: F401

REPORT = str(UUID(int=99))


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [None, 'report_identity', 'model_identity', 'workspace_missing', 'metadata_missing'])
async def test_report_model_mapping_uses_trusted_metadata_only(harness, bad):
    _, _, transport, adapter = harness
    original = transport.call
    async def call(name, args):
        if name == 'ResolveFabricItem' and '/reports/' in args['fabricItemId']:
            transport.calls.append((name, args))
            return {'fabricItemId': str(UUID(int=999)) if bad == 'report_identity' else REPORT,
                    'workspaceId': WORKSPACE, 'itemType': 'Report'}
        if name == 'GetReportMetadata':
            transport.calls.append((name, args))
            assert args == {'reportObjectId': REPORT}
            if bad == 'metadata_missing': return {'SemanticModel': {}}
            return {'SemanticModel': {'Id': MODEL}, 'ReportMetadata': {'Id': REPORT}}
        if name == 'ResolveFabricItem' and args['fabricItemId'] == MODEL:
            return {'fabricItemId': str(UUID(int=999)) if bad == 'model_identity' else MODEL,
                    'workspaceId': None if bad == 'workspace_missing' else WORKSPACE,
                    'itemType':'SemanticModel'}
        return await original(name, args)
    transport.call = call
    transport.validate_report_metadata_capability = lambda: None
    if bad:
        with pytest.raises(PowerBIAdapterError): await adapter.bind_catalog_report(WORKSPACE, REPORT)
        assert adapter.binding_count == 0
    else:
        ref = await adapter.bind_catalog_report(WORKSPACE, REPORT)
        assert ref.semantic_model_id == MODEL and ref.workspace_id == WORKSPACE
        assert adapter.binding_count == 1
    assert not any(name == 'ExecuteQuery' for name, _ in transport.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [None, 'citation', 'report', 'model', 'workspace', 'mirror', 'error'])
async def test_native_report_envelope_resolves_exact_model_workspace(harness, bad):
    _, _, transport, adapter = harness
    original = transport.call
    async def call(name, args):
        if name == 'ResolveFabricItem' and '/reports/' in args['fabricItemId']:
            return {'fabricItemId': REPORT, 'workspaceId': WORKSPACE, 'itemType': 'Report'}
        if name == 'GetReportMetadata':
            body = {'SemanticModel': {'Id': MODEL}, 'ReportMetadata': {'Id':
                str(UUID(int=999)) if bad == 'report' else REPORT}}
            raw = {'content': [{'type': 'text', 'text': json.dumps(body)}],
                'structuredContent': {'artifact_citation': {'ArtifactId':
                    str(UUID(int=999)) if bad == 'citation' else REPORT}}}
            if bad == 'mirror': raw['content'].append({'type':'text','text':'{}'})
            if bad == 'error': raw['isError'] = True
            return raw
        if name == 'ResolveFabricItem' and args['fabricItemId'] == MODEL:
            transport.calls.append((name, args))
            return {'fabricItemId': str(UUID(int=999)) if bad == 'model' else MODEL,
                'workspaceId': None if bad == 'workspace' else WORKSPACE, 'itemType':'SemanticModel'}
        return await original(name, args)
    transport.call = call
    transport.validate_report_metadata_capability = lambda: None
    if bad:
        with pytest.raises(PowerBIAdapterError): await adapter.bind_catalog_report(WORKSPACE, REPORT)
        assert adapter.binding_count == 0
    else:
        ref = await adapter.bind_catalog_report(WORKSPACE, REPORT)
        assert (ref.workspace_id, ref.semantic_model_id) == (WORKSPACE, MODEL)
        assert ('ResolveFabricItem', {'fabricItemId': MODEL}) in transport.calls
    assert not any(name == 'ExecuteQuery' for name, _ in transport.calls)


@pytest.mark.asyncio
async def test_report_model_workspace_is_resolved_independently(harness):
    _, _, transport, adapter = harness
    other_workspace = str(UUID(int=77))
    original = transport.call
    async def call(name, args):
        if name == 'ResolveFabricItem':
            is_report = '/reports/' in args['fabricItemId']
            return {'fabricItemId': REPORT if is_report else MODEL,
                'workspaceId': WORKSPACE if is_report else other_workspace,
                'itemType':'Report' if is_report else 'SemanticModel'}
        if name == 'GetReportMetadata':
            return {'SemanticModel':{'Id':MODEL},'ReportMetadata':{'Id':REPORT}}
        return await original(name,args)
    transport.call = call
    transport.validate_report_metadata_capability = lambda: None
    ref = await adapter.bind_catalog_report(WORKSPACE, REPORT)
    assert (ref.workspace_id,ref.semantic_model_id)==(other_workspace,MODEL)
