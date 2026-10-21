"""Single deployment policy; Microsoft access and operator consent are independent.

Only CloudWorkspaceService may supply binding_verified after checking native
session/principal and an exact server-owned adapter binding. This flag is never
accepted by an HTTP DTO. Opening owner storage permits no resource response.
"""
from backend.app.config.cloud_test_policy import CloudTestPolicy


class CloudProductAuthorizationPolicy:
    def __init__(self, settings):
        self._settings = settings
        self._test = CloudTestPolicy(settings)

    def capability(self, workspace_id, model_id, name, *, binding_verified=False):
        if name not in {'query_execution', 'external_llm_disclosure', 'business_persistence'}:
            return False
        if binding_verified is not True:
            return False
        if self._test.enabled:
            return self._test.capability(workspace_id, model_id, name)
        if name == 'query_execution':
            return True
        return getattr(self._settings, 'allow_' + name, False) is True

    def storage_enabled(self):
        if self._test.enabled:
            return self._test.storage_enabled()
        return getattr(self._settings, 'allow_business_persistence', False) is True

    def snapshot(self):
        if self._test.enabled:
            return ('test', self._test.snapshot())
        return ('product',
            getattr(self._settings, 'allow_external_llm_disclosure', False),
            getattr(self._settings, 'allow_business_persistence', False))
