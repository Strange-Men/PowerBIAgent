"""Operator-owned M6 Real-test scope. Never a product/principal authorization grant."""
from uuid import UUID
from urllib.parse import urlsplit
import re

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.powerbi.base import PowerBIAdapterError


class MissingCloudTestScope(PowerBIAdapterError):
    denial_reason = 'test_scope_missing'

    def __init__(self):
        super().__init__('RESOURCE_NOT_ACCESSIBLE', provider='fabric_iq',
                         error_type='RESOURCE_NOT_ACCESSIBLE', retryable=False)


class TestModelApproval(BaseModel):
    model_id: UUID
    synthetic_only: bool = False
    model_config = ConfigDict(extra='forbid', frozen=True)


class TestReportApproval(BaseModel):
    report_id: UUID
    model_id: UUID
    synthetic_only: bool = False
    model_config = ConfigDict(extra='forbid', frozen=True)


class TestWorkspaceApproval(BaseModel):
    workspace_id: UUID
    # Legacy operator metadata remains readable, never resource authority.
    models: tuple[TestModelApproval, ...] = Field(default=(), max_length=100)
    reports: tuple[TestReportApproval, ...] = Field(default=(), max_length=100)
    query_execution: StrictBool = False
    external_llm_disclosure: StrictBool = False
    business_persistence: StrictBool = False
    model_config = ConfigDict(extra='forbid', frozen=True)

    @model_validator(mode='after')
    def unique_resources(self):
        models = {m.model_id for m in self.models}
        if (len(models) != len(self.models) or len({r.report_id for r in self.reports}) != len(self.reports)
                or any(r.model_id not in models for r in self.reports)):
            raise ValueError('test resource configuration must be unique and model-bound')
        return self


class CloudTestAllowlist(BaseModel):
    workspaces: tuple[TestWorkspaceApproval, ...] = Field(min_length=1, max_length=100)
    company_account_owner_approved: bool = False
    model_config = ConfigDict(extra='forbid', frozen=True)

    @model_validator(mode='before')
    @classmethod
    def legacy_single_workspace(cls, value):
        # Existing repo-external operator configuration remains readable.
        if isinstance(value, dict) and 'workspace_id' in value and 'workspaces' not in value:
            value = dict(value)
            workspace = {key:value.pop(key) for key in ('workspace_id','models','reports') if key in value}
            value['workspaces'] = [workspace]
        return value

    @model_validator(mode='after')
    def unique_workspaces(self):
        if len({w.workspace_id for w in self.workspaces}) != len(self.workspaces):
            raise ValueError('test workspaces must be unique')
        # Reject contradictory legacy metadata; IQ authority uses connection
        # context and current-principal Resolve/Schema, never these lists.
        models = [m.model_id for w in self.workspaces for m in w.models]
        reports = [r.report_id for w in self.workspaces for r in w.reports]
        if len(set(models)) != len(models) or len(set(reports)) != len(reports):
            raise ValueError('test artifact identity must be unambiguous')
        return self


class CloudTestPolicy:
    def __init__(self, settings):
        self._settings = settings

    @property
    def enabled(self): return getattr(self._settings, 'fabric_test_mode', False)

    @property
    def scope(self):
        scope = getattr(self._settings, 'fabric_test_allowlist', None)
        if scope is None: raise MissingCloudTestScope()
        return scope

    def capability(self, workspace_id, model_id, name):
        if name not in {'query_execution', 'external_llm_disclosure', 'business_persistence'}:
            return False
        scope = getattr(self._settings, 'fabric_test_allowlist', None)
        if not self.enabled or scope is None:
            return False
        workspace = next((w for w in scope.workspaces if str(w.workspace_id) == str(workspace_id)), None)
        return bool(workspace is not None and getattr(workspace, name) is True)

    def storage_enabled(self):
        # Opening the owner repository grants no resource response: every row
        # still requires its exact binding, current access and target grant.
        scope = getattr(self._settings, 'fabric_test_allowlist', None)
        return bool(self.enabled and scope is not None and any(
            w.business_persistence for w in scope.workspaces))

    def snapshot(self):
        return self.enabled, getattr(self._settings, 'fabric_test_allowlist', None)

    def workspace(self, workspace_id):
        if not self.enabled: return
        approved = next((w for w in self.scope.workspaces if str(w.workspace_id) == str(workspace_id)), None)
        if approved is None: raise fail('RESOURCE_NOT_ACCESSIBLE')
        return approved

    def model(self, workspace_id, model_id):
        if not self.enabled: return
        self.workspace(workspace_id)
        self._artifact_id(model_id)

    def report(self, workspace_id, report_id):
        if not self.enabled: return
        self.workspace(workspace_id)
        self._artifact_id(report_id)

    @staticmethod
    def _artifact_id(value):
        try:
            if not isinstance(value, str) or str(UUID(value)) != value:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise fail('RESOURCE_NOT_ACCESSIBLE') from None

    def rest_path(self, path):
        if not self.enabled: return
        matched = re.fullmatch(r'/workspaces/([0-9a-f-]{36})(?:/(semanticModels|reports)(?:/([0-9a-f-]{36}))?)?', path)
        if not matched: raise fail('RESOURCE_NOT_ACCESSIBLE')
        if matched[2] == 'semanticModels' and matched[3]: self.model(matched[1], matched[3])
        elif matched[2] == 'reports' and matched[3]: self.report(matched[1], matched[3])
        else: self.workspace(matched[1])

    def iq_call(self, name, arguments, *, resource=None):
        if not self.enabled: return
        if not isinstance(resource, tuple) or len(resource) != 2:
            raise fail('RESOURCE_NOT_ACCESSIBLE')
        workspace_id, artifact_id = resource
        self.model(workspace_id, artifact_id)
        if name == 'ResolveFabricItem':
            parsed = urlsplit(arguments.get('fabricItemId', ''))
            matched = re.fullmatch(r'/groups/([0-9a-f-]{36})/(datasets|semanticmodels|reports)/([0-9a-f-]{36})(?:/details)?', parsed.path)
            if (parsed.scheme != 'https' or parsed.netloc not in {'app.powerbi.com','app.fabric.microsoft.com'}
                    or parsed.query or parsed.fragment or not matched
                    or (matched[1], matched[3]) != resource):
                raise fail('RESOURCE_NOT_ACCESSIBLE')
            if matched[2] == 'reports': self.report(matched[1], matched[3])
            else: self.model(matched[1], matched[3])
        elif name in {'GetSemanticModelSchema','ValueSearch','ExecuteQuery'}:
            if arguments.get('artifactId') != artifact_id: raise fail('RESOURCE_NOT_ACCESSIBLE')
        elif name == 'GetReportMetadata':
            if arguments.get('artifactId') != artifact_id: raise fail('RESOURCE_NOT_ACCESSIBLE')
            self.report(workspace_id, artifact_id)
        else:
            # Name discovery cannot be scoped by the known workspace contract.
            raise fail('RESOURCE_NOT_ACCESSIBLE')
