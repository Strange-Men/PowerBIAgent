"""Operator grants are independent, resource-bound and default denied."""
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_test_policy import CloudTestAllowlist, CloudTestPolicy
from backend.tests.unit.test_fabric_iq_adapter import harness, MODEL, WORKSPACE  # noqa: F401
from backend.tests.unit.test_cloud_workspace_service import workspace

CAPABILITIES = ('query_execution', 'external_llm_disclosure', 'business_persistence')


def approval(**grants):
    return CloudTestAllowlist(workspaces=[{'workspace_id': WORKSPACE,
        'models': [{'model_id': MODEL, 'synthetic_only': True}], **grants}])


def test_native_grants_default_denied_even_with_owner_approval():
    scope = approval().model_copy(update={'company_account_owner_approved': True})
    policy = CloudTestPolicy(SimpleNamespace(fabric_test_mode=True, fabric_test_allowlist=scope))
    for capability in CAPABILITIES:
        assert not policy.capability(WORKSPACE, MODEL, capability)


@pytest.mark.parametrize('capability', CAPABILITIES)
def test_each_grant_is_independent_and_workspace_bound(capability):
    scope = approval(**{capability: True})
    policy = CloudTestPolicy(SimpleNamespace(fabric_test_mode=True, fabric_test_allowlist=scope))
    for check in CAPABILITIES:
        assert policy.capability(WORKSPACE, MODEL, check) == (check == capability)
    assert not policy.capability(str(UUID(int=999)), MODEL, capability)
    assert policy.capability(WORKSPACE, str(UUID(int=999)), capability)
    policy._settings.fabric_test_mode = False
    assert not policy.capability(WORKSPACE, MODEL, capability)


@pytest.mark.parametrize('capability', CAPABILITIES)
@pytest.mark.parametrize('value', [1, 0, 'true', 'false', None])
def test_operator_grants_require_actual_boolean(capability, value):
    with pytest.raises(ValidationError):
        approval(**{capability: value})


@pytest.mark.asyncio
async def test_native_capabilities_work_only_after_exact_selection_and_revoke_inflight(harness):
    from backend.app.application.cloud_product_services import _SelectionLease
    auth, session, _, _ = harness
    auth.settings.fabric_test_mode = True
    auth.settings.fabric_test_allowlist = approval(**{cap: True for cap in CAPABILITIES})
    service = workspace(harness)
    try:
        with pytest.raises(AuthFailure): service.require_execution(session.session_id, session.principal)
        catalog = await service.catalog(session.session_id, session.principal)
        selected = await service.select(session.session_id, session.principal, catalog.items[0].key)
        assert selected.execution_ready
        for check in (service.require_execution, service.require_disclosure, service.require_persistence):
            check(session.session_id, session.principal)
        lease = _SelectionLease(auth, service, session.session_id, session.principal, selected)
        lease.require_session(session.session_id)
        auth.settings.fabric_test_allowlist = approval()
        with pytest.raises(AuthFailure): lease.require_session(session.session_id)
        assert not service.status(session.session_id, session.principal).execution_ready
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_adapter_mock_flag_does_not_grant_product_authority(harness):
    from backend.app.application.cloud_workspace_service import CloudWorkspaceService
    from backend.tests.api.test_cloud_product_api import SyntheticAdapter
    auth, session, _, _ = harness
    service = CloudWorkspaceService(auth, SimpleNamespace(create_product=lambda sid, p: SyntheticAdapter(auth, sid, p)))
    try:
        for check in (service.require_execution, service.require_disclosure, service.require_persistence):
            with pytest.raises(AuthFailure): check(session.session_id, session.principal)
        assert not service.status(session.session_id, session.principal).execution_ready
    finally:
        await service.aclose()
