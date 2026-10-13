"""Operator-owned M6 Real-test scope. Never a product/principal authorization grant."""
from uuid import UUID
from urllib.parse import urlsplit
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.powerbi.fabric_iq_contract import fail


class TestModelApproval(BaseModel):
    model_id: UUID
    synthetic_only: bool = False
    model_config = ConfigDict(extra='forbid', frozen=True)


class TestReportApproval(BaseModel):
    report_id: UUID
    model_id: UUID
    synthetic_only: bool = False
    model_config = ConfigDict(extra='forbid', frozen=True)


class CloudTestAllowlist(BaseModel):
    workspace_id: UUID
    models: tuple[TestModelApproval, ...] = Field(min_length=1, max_length=100)
    reports: tuple[TestReportApproval, ...] = Field(default=(), max_length=100)
    company_account_owner_approved: bool = False
    model_config = ConfigDict(extra='forbid', frozen=True)

    @model_validator(mode='after')
    def unique_resources(self):
        models = {m.model_id for m in self.models}
        if (len(models) != len(self.models) or len({r.report_id for r in self.reports}) != len(self.reports)
                or any(r.model_id not in models for r in self.reports)):
            raise ValueError('test resource configuration must be unique and model-bound')
        return self


class CloudTestPolicy:
    def __init__(self, settings):
        self._settings = settings

    @property
    def enabled(self): return getattr(self._settings, 'fabric_test_mode', False)

    @property
    def scope(self):
        scope = getattr(self._settings, 'fabric_test_allowlist', None)
        if scope is None: raise fail('RESOURCE_NOT_ACCESSIBLE')
        return scope

    def workspace(self, workspace_id):
        if self.enabled and str(self.scope.workspace_id) != str(workspace_id):
            raise fail('RESOURCE_NOT_ACCESSIBLE')

    def model(self, workspace_id, model_id):
        if not self.enabled: return
        self.workspace(workspace_id)
        approved = next((m for m in self.scope.models if str(m.model_id) == str(model_id)), None)
        if approved is None or (not approved.synthetic_only and not self.scope.company_account_owner_approved):
            raise fail('RESOURCE_NOT_ACCESSIBLE')

    def report(self, workspace_id, report_id):
        if not self.enabled: return
        self.workspace(workspace_id)
        approved = next((r for r in self.scope.reports if str(r.report_id) == str(report_id)), None)
        if approved is None or (not approved.synthetic_only and not self.scope.company_account_owner_approved):
            raise fail('RESOURCE_NOT_ACCESSIBLE')
        self.model(workspace_id, approved.model_id)

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
            self.model(self.scope.workspace_id, arguments.get('artifactId'))
        elif name == 'GetReportMetadata':
            self.report(self.scope.workspace_id, arguments.get('artifactId'))
        else:
            # Name discovery cannot be scoped by the known workspace contract.
            raise fail('RESOURCE_NOT_ACCESSIBLE')
