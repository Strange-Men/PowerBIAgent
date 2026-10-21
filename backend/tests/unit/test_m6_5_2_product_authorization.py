"""Product policy never derives deployment consent from Microsoft access."""
from types import SimpleNamespace

import pytest

from backend.tests.unit.test_cloud_product_capabilities import approval
from backend.tests.unit.test_fabric_iq_adapter import settings, WORKSPACE, MODEL


def policy(**changes):
    from backend.app.config.cloud_product_policy import CloudProductAuthorizationPolicy
    return CloudProductAuthorizationPolicy(settings(powerbi_mode='fabric_iq', **changes))


def test_normal_mode_requires_exact_server_verified_binding():
    product = policy(allow_external_llm_disclosure=True, allow_business_persistence=True)
    for name in ('query_execution', 'external_llm_disclosure', 'business_persistence'):
        assert not product.capability(WORKSPACE, MODEL, name)
        assert product.capability(WORKSPACE, MODEL, name, binding_verified=True)
    assert not product.capability(WORKSPACE, MODEL, 'unknown', binding_verified=True)


def test_microsoft_access_does_not_grant_disclosure_or_retention():
    product = policy()
    assert product.capability(WORKSPACE, MODEL, 'query_execution', binding_verified=True)
    assert not product.capability(WORKSPACE, MODEL, 'external_llm_disclosure', binding_verified=True)
    assert not product.capability(WORKSPACE, MODEL, 'business_persistence', binding_verified=True)
    assert not product.storage_enabled()


@pytest.mark.parametrize('name', ['external_llm_disclosure', 'business_persistence'])
def test_normal_deployment_grants_are_independent(name):
    product = policy(**{'allow_' + name: True})
    other = 'business_persistence' if name == 'external_llm_disclosure' else 'external_llm_disclosure'
    assert product.capability(WORKSPACE, MODEL, name, binding_verified=True)
    assert not product.capability(WORKSPACE, MODEL, other, binding_verified=True)


def test_test_mode_preserves_allowlist_and_three_operator_grants():
    product = policy(fabric_test_mode=True, allow_external_llm_disclosure=True, allow_business_persistence=True)
    assert not product.storage_enabled()
    for name in ('query_execution', 'external_llm_disclosure', 'business_persistence'):
        assert not product.capability(WORKSPACE, MODEL, name, binding_verified=True)
    product._settings.fabric_test_allowlist = approval(query_execution=True)
    assert product.capability(WORKSPACE, MODEL, 'query_execution', binding_verified=True)
    assert not product.capability(WORKSPACE, MODEL, 'business_persistence', binding_verified=True)


def test_policy_revoke_changes_inflight_snapshot():
    product = policy(allow_external_llm_disclosure=True)
    previous = product.snapshot()
    product._settings.allow_external_llm_disclosure = False
    assert product.snapshot() != previous
    assert not product.capability(WORKSPACE, MODEL, 'external_llm_disclosure', binding_verified=True)


def test_missing_or_non_boolean_configuration_never_grants_product_access():
    from backend.app.config.cloud_product_policy import CloudProductAuthorizationPolicy
    product = CloudProductAuthorizationPolicy(SimpleNamespace(fabric_test_mode=False,
        allow_external_llm_disclosure='true', allow_business_persistence=1))
    assert not product.capability(WORKSPACE, MODEL, 'external_llm_disclosure', binding_verified=True)
    assert not product.storage_enabled()


def test_product_authorization_epoch_does_not_depend_on_test_allowlist():
    product = policy(allow_external_llm_disclosure=True, allow_business_persistence=True)
    before = product.snapshot()
    product._settings.fabric_test_allowlist = approval(query_execution=False)
    assert product.snapshot() == before
    assert product.capability(WORKSPACE, MODEL, 'query_execution', binding_verified=True)
    assert product.capability(WORKSPACE, MODEL, 'external_llm_disclosure', binding_verified=True)
