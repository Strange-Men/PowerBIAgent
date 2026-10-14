"""Operator-owned M6 Real-test scope. Never a product/principal authorization grant."""
from uuid import UUID
from urllib.parse import urlsplit
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    models: tuple[TestModelApproval, ...] = Field(min_length=1, max_length=100)
    reports: tuple[TestReportApproval, ...] = Field(default=(), max_length=100)
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
        # IQ artifact-only calls must resolve to exactly one approved workspace.
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

    def workspace(self, workspace_id):
        if not self.enabled: return
        approved = next((w for w in self.scope.workspaces if str(w.workspace_id) == str(workspace_id)), None)
        if approved is None: raise fail('RESOURCE_NOT_ACCESSIBLE')
        return approved

    def model(self, workspace_id, model_id):
        if not self.enabled: return
        workspace = self.workspace(workspace_id)
        approved = next((m for m in workspace.models if str(m.model_id) == str(model_id)), None)
        if approved is None or (not approved.synthetic_only and not self.scope.company_account_owner_approved):
            raise fail('RESOURCE_NOT_ACCESSIBLE')

    def report(self, workspace_id, report_id):
        if not self.enabled: return
        workspace = self.workspace(workspace_id)
        approved = next((r for r in workspace.reports if str(r.report_id) == str(report_id)), None)
        if approved is None or (not approved.synthetic_only and not self.scope.company_account_owner_approved):
            raise fail('RESOURCE_NOT_ACCESSIBLE')
        self.model(workspace_id, approved.model_id)

    def _artifact_workspace(self, artifact_id, collection, field):
        workspace = next((w for w in self.scope.workspaces
            if any(str(getattr(item, field)) == str(artifact_id) for item in getattr(w, collection))), None)
        if workspace is None: raise fail('RESOURCE_NOT_ACCESSIBLE')
        return workspace.workspace_id

    def rest_path(self, path):
        if not self.enabled: return
        matched = re.fullmatch(r'/workspaces/([0-9a-f-]{36})(?:/(semanticModels|reports)/([0-9a-f-]{36}))?', path)
        if not matched: raise fail('RESOURCE_NOT_ACCESSIBLE')
        if matched[2] == 'semanticModels': self.model(matched[1], matched[3])
        elif matched[2] == 'reports': self.report(matched[1], matched[3])
        else: self.workspace(matched[1])

    def iq_call(self, name, arguments):
        if not self.enabled: return
        if name == 'ResolveFabricItem':
            parsed = urlsplit(arguments.get('fabricItemId', ''))
            matched = re.fullmatch(r'/groups/([0-9a-f-]{36})/(datasets|semanticmodels|reports)/([0-9a-f-]{36})(?:/details)?', parsed.path)
            if (parsed.scheme != 'https' or parsed.netloc not in {'app.powerbi.com','app.fabric.microsoft.com'}
                    or parsed.query or parsed.fragment or not matched):
                raise fail('RESOURCE_NOT_ACCESSIBLE')
            if matched[2] == 'reports': self.report(matched[1], matched[3])
            else: self.model(matched[1], matched[3])
        elif name in {'GetSemanticModelSchema','ValueSearch','ExecuteQuery'}:
            artifact = arguments.get('artifactId')
            self.model(self._artifact_workspace(artifact, 'models', 'model_id'), artifact)
        elif name == 'GetReportMetadata':
            artifact = arguments.get('artifactId')
            self.report(self._artifact_workspace(artifact, 'reports', 'report_id'), artifact)
        else:
            # Name discovery cannot be scoped by the known workspace contract.
            raise fail('RESOURCE_NOT_ACCESSIBLE')
