"""Current-principal catalog. REST coverage and IQ accessibility are independent."""
from datetime import datetime, timezone
import asyncio
import logging
from time import monotonic
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_catalog import SharedModelSeed
from backend.app.config.cloud_test_policy import CloudTestPolicy
from backend.app.core.async_runtime import bounded_gather_ordered
from backend.app.harness.errors import ToolExecutionError, ToolTimeoutError
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext, ToolGateway, ToolSpec
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.powerbi.fabric_iq_normalization import guid
from backend.app.schemas.data_contracts import UserContext


async def _metadata_step(stage, operation):
    """Low-cardinality timings only; never emit inputs or provider errors."""
    started, outcome = monotonic(), "failed"
    try:
        result = await operation
        outcome = "completed"
        return result
    finally:
        logging.getLogger(__name__).info("cloud_catalog stage=%s outcome=%s duration_ms=%d",
            stage, outcome, int((monotonic() - started) * 1000))


class CloudModelOption(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    workspace_display_name: str = Field(min_length=1, max_length=200)
    source: Literal["fabric_iq"] = "fabric_iq"
    accessibility: Literal["available"] = "available"
    model_config = ConfigDict(extra="forbid", frozen=True)


class CloudModelCatalog(BaseModel):
    status: Literal["ready", "partial", "empty", "forbidden", "error"]
    product_mode: bool = False
    persistence_enabled: bool = False
    runtime_mode: Literal["real"] = "real"
    items: list[CloudModelOption] = Field(default_factory=list)
    workspace_scope_complete: bool = False
    authorization_scope_complete: bool = True
    unverified_count: int = Field(default=0, ge=0)
    individual_share_coverage: Literal["configured_seeds_only", "not_applicable_test_scope"] = "configured_seeds_only"
    coverage_scope: Literal["workspace_membership_and_configured_seeds", "approved_test_resources"] = "workspace_membership_and_configured_seeds"
    inaccessible_count: int = 0
    error_type: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Candidate(BaseModel):
    workspace_id: str
    model_id: str
    workspace_display_name: str
    model_config = ConfigDict(extra="forbid", frozen=True)


class _AuthorizationDeferred(Exception):
    def __init__(self, code): self.code = code


def _display(value):
    if not isinstance(value, str): raise fail("CONTRACT_DRIFT")
    value = "".join(c for c in value if c.isprintable()).strip()[:200]
    if not value: raise fail("CONTRACT_DRIFT")
    return value


def _unique(rows, *, workspace_id=None, item_type=None):
    unique = {}
    for row in rows:
        if not isinstance(row, dict): raise fail("CONTRACT_DRIFT")
        key = guid(row.get("id"))
        if workspace_id and guid(row.get("workspaceId")) != workspace_id: raise fail("CONTRACT_DRIFT")
        if item_type and row.get("type") != item_type: raise fail("CONTRACT_DRIFT")
        _display(row.get("displayName"))
        if key in unique and unique[key] != row: raise fail("CONTRACT_DRIFT")
        unique[key] = row
    return unique


class CloudCatalogService:
    def __init__(self, auth, session_id, principal, rest, adapter, *, shared_seeds=(), deadline=None):
        self._auth, self._sid, self._principal = auth, session_id, principal
        self._rest, self._seeds = rest, tuple(shared_seeds)
        self._test_policy = CloudTestPolicy(auth.settings)
        self._deadline = deadline if deadline is not None else monotonic() + auth.settings.request_timeout_seconds
        self._gateway = ToolGateway()
        self.validate()
        rest.assert_session_binding(auth,session_id,principal)
        adapter.assert_session_binding(auth,session_id,principal)

        async def authorize(candidate):
            self.validate()
            self._test_policy.model(candidate.workspace_id, candidate.model_id)
            ref = await _metadata_step("authorize_model",
                adapter.bind_catalog_model(candidate.workspace_id, candidate.model_id))
            self.validate()
            self._test_policy.model(candidate.workspace_id, candidate.model_id)
            return CloudModelOption(key=ref.server_model_key, display_name=_display(ref.display_name),
                workspace_display_name=candidate.workspace_display_name)

        self._gateway.register(ToolSpec(name="authorize_cloud_catalog_model", input_model=_Candidate,
            output_model=CloudModelOption, handler=authorize, max_retries=0, timeout_seconds=60,
            read_only=True, allowed_intents=[IntentType.DATA_QUESTION], supported_modes=[RuntimeDataMode.REAL]))

    def validate(self):
        if self._auth.require_session(self._sid).principal != self._principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    async def discover(self):
        self.validate()
        if self._test_policy.enabled:
            # Missing configuration and hostile seeds fail before any request.
            self._test_policy.scope
            for seed in self._seeds: self._test_policy.model(seed.workspace_id, seed.model_id)
        candidates, items, inaccessible, complete, error_type = {}, [], 0, True, None
        top_failure = None
        try:
            workspaces = _unique(await _metadata_step("list_workspaces", self._rest.list_workspaces()))
            self.validate()
        except PowerBIAdapterError as error:
            self.validate()
            workspaces, complete, top_failure, error_type = {}, False, error.error_type, error.error_type
        for workspace_id, workspace in workspaces.items():
            self._test_policy.workspace(workspace_id)
            name = _display(workspace["displayName"])
            try:
                models = _unique(await _metadata_step("list_models", self._rest.list_models(workspace_id)),
                    workspace_id=workspace_id, item_type="SemanticModel")
                self.validate()
                for model_id in models:
                    self._test_policy.model(workspace_id, model_id)
                    candidates[(workspace_id,model_id)] = _Candidate(workspace_id=workspace_id,
                        model_id=model_id, workspace_display_name=name)
            except PowerBIAdapterError:
                self.validate()
                complete = False
            try:
                # Reports are control-plane metadata only, never query authority.
                reports = _unique(await _metadata_step("list_reports", self._rest.list_reports(workspace_id)),
                    workspace_id=workspace_id, item_type="Report")
                self.validate()
                for report_id in reports: self._test_policy.report(workspace_id, report_id)
            except PowerBIAdapterError:
                self.validate()
                complete = False
        for seed in self._seeds:
            workspace_id, model_id = str(seed.workspace_id), str(seed.model_id)
            candidates.setdefault((workspace_id,model_id), _Candidate(workspace_id=workspace_id,
                model_id=model_id, workspace_display_name=_display(seed.workspace_display_name)))
        # Explicit deployment seeds receive bounded validation priority, never access authority.
        candidates = {**{(str(seed.workspace_id), str(seed.model_id)):
            candidates[(str(seed.workspace_id), str(seed.model_id))] for seed in self._seeds}, **candidates}
        if len(candidates) > 500: raise fail("CONTRACT_DRIFT")
        context = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,
            intent=IntentType.DATA_QUESTION, user=UserContext(allowed_tools=["authorize_cloud_catalog_model"]))
        finished, halt_code = {}, None
        async def authorize_one(indexed):
            nonlocal halt_code
            if halt_code is not None: raise _AuthorizationDeferred(halt_code)
            index, candidate = indexed
            try:
                item = await self._gateway.execute("authorize_cloud_catalog_model",context,candidate)
                self.validate()
                finished[index] = item
                return item
            except (ToolExecutionError, ToolTimeoutError) as error:
                self.validate()
                cause = error.__context__
                if isinstance(cause, AuthFailure) and cause.code != 'AUTH_FORBIDDEN': raise cause
                code = getattr(cause, "error_type",
                    "QUERY_TIMEOUT" if isinstance(error, ToolTimeoutError) else "UPSTREAM_UNAVAILABLE")
                if isinstance(cause, AuthFailure): code = 'RESOURCE_NOT_ACCESSIBLE'
                if code not in {"RESOURCE_NOT_ACCESSIBLE", "MODEL_RESOLUTION_FAILED", "SCHEMA_UNAVAILABLE"}:
                    # Unknown access is not a denial. Stop this batch and drain
                    # siblings rather than amplify an upstream throttle/failure.
                    halt_code = halt_code or code
                    raise _AuthorizationDeferred(halt_code) from None
                finished[index] = None
                return None
        authorization_complete = True
        # Leave a small portion of the same request budget for cancellation/response cleanup.
        reserve = min(2, self._auth.settings.request_timeout_seconds * 0.05)
        try:
            async with asyncio.timeout(max(0, self._deadline - monotonic() - reserve)):
                await bounded_gather_ordered(tuple(enumerate(candidates.values())), authorize_one, max_concurrency=3)
        except TimeoutError:
            # Only our own deadline is converted to scoped metadata PARTIAL.
            # Native Auth failures and caller cancellation continue to reject the whole result.
            authorization_complete, error_type = False, "QUERY_TIMEOUT"
        except _AuthorizationDeferred as deferred:
            authorization_complete, error_type = False, deferred.code
        items = [finished[index] for index in sorted(finished) if finished[index] is not None]
        inaccessible = sum(item is None for item in finished.values())
        inaccessible += getattr(self._rest, 'inaccessible_count', 0)
        complete = complete and getattr(self._rest, 'test_scope_complete', True)
        self.validate()
        # No authority proves coverage of unconfigured individual shares.
        # Successful workspace enumeration with zero rows is still PARTIAL.
        status = "partial"
        if (top_failure or not authorization_complete) and not items:
            status = "forbidden" if top_failure == "RESOURCE_NOT_ACCESSIBLE" else "error"
        return CloudModelCatalog(status=status, items=items, workspace_scope_complete=complete,
            coverage_scope='approved_test_resources' if self._test_policy.enabled else 'workspace_membership_and_configured_seeds',
            individual_share_coverage='not_applicable_test_scope' if self._test_policy.enabled else 'configured_seeds_only',
            authorization_scope_complete=authorization_complete, unverified_count=len(candidates)-len(finished),
            inaccessible_count=inaccessible, error_type=error_type)
