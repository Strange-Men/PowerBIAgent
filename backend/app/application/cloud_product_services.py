"""Compose existing M5 services with M6.3 ownership; no alternate factual chain."""
from dataclasses import dataclass

from backend.app.application.deepseek_turn_service import LLMTurnService
from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_test_policy import CloudTestPolicy
from backend.app.harness.models import HarnessConfig
from backend.app.memory.models import RuntimeDataMode
from backend.app.report.executive import ExecutiveSalesReportRenderer
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.registry import build_report_dispatcher


class _SelectionLease:
    """Repository validation projection; native Auth remains identity authority."""
    def __init__(self, auth, workspace, sid, principal, selection):
        self._auth, self._workspace = auth, workspace
        self._sid, self._principal, self._selection = sid, principal, selection

    def require_session(self, sid):
        if sid != self._sid: raise AuthFailure("AUTH_FORBIDDEN", 403)
        record = self._auth.require_session(sid)
        if record.principal != self._principal: raise AuthFailure("AUTH_FORBIDDEN", 403)
        current = self._workspace.status(sid, self._principal)
        if (current.generation, current.selected_model_key, current.conversation_id) != (
                self._selection.generation, self._selection.selected_model_key, self._selection.conversation_id):
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        return record


@dataclass(frozen=True)
class PreparedCloudProduct:
    turn_service: LLMTurnService
    repositories: object
    conversation_id: str
    semantic_model_key: str
    _lease: _SelectionLease

    async def execute(self, message, *, request_id, llm_profile_key=None, report_template_key=None):
        lease = self._lease
        lease.require_session(lease._sid)
        lease._workspace.require_execution(lease._sid, lease._principal)
        result = await self.turn_service.execute(message,
            conversation_id=self.conversation_id, request_id=request_id,
            semantic_model_key=self.semantic_model_key, llm_profile_key=llm_profile_key,
            report_template_key=report_template_key)
        lease.require_session(lease._sid)
        return result


class CloudProductServiceFactory:
    """Storage must be explicitly supplied; no default DB opening or migration."""
    def __init__(self, auth, workspace, repository_factory, llm_registry, display_llm_registry):
        self._auth, self._workspace, self._repositories = auth, workspace, repository_factory
        self._llm, self._display = llm_registry, display_llm_registry
        self._test_policy = CloudTestPolicy(auth.settings)

    def _validate_identity(self, sid, principal):
        if self._auth.require_session(sid).principal != principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    async def _read_owned(self, sid, principal, operation):
        # Legacy snapshots lack a durable exact test-resource authorization
        # projection. Owner identity alone cannot authorize replay of BI facts.
        if self._test_policy.enabled: raise AuthFailure('AUTH_FORBIDDEN', 403)
        # Past resources are owner-scoped; viewing does not select a model or
        # restore business Memory. Storage is still explicitly supplied.
        self._validate_identity(sid, principal)
        repositories = await self._repositories.for_session(self._auth, sid, principal)
        self._validate_identity(sid, principal)
        result = await operation(repositories)
        self._validate_identity(sid, principal)
        return result

    async def list_history(self, sid, principal, *, limit, cursor=None):
        return await self._read_owned(sid, principal, lambda repos:
            repos.history_service.list_recent(RuntimeDataMode.REAL, limit=limit, cursor=cursor))

    async def read_history(self, sid, principal, conversation_id, *, limit, cursor=None):
        return await self._read_owned(sid, principal, lambda repos:
            repos.history_service.get_history(RuntimeDataMode.REAL, conversation_id, limit=limit, cursor=cursor))

    async def read_report(self, sid, principal, report_id):
        # Existing managed repository authorizes metadata before resolving files.
        # View and download consume the same checked artifact/HTML pair.
        return await self._read_owned(sid, principal, lambda repos: repos.reports.read_html(report_id))

    async def prepare(self, sid, principal):
        # No real schema/facts reach the generic external Provider or storage
        # while test disclosure and recovery contracts are unproven.
        if self._test_policy.enabled: raise AuthFailure('AUTH_FORBIDDEN', 403)
        current = self._workspace.status(sid, principal)
        if current.selected_model_key is None: raise AuthFailure("AUTH_FORBIDDEN", 403)
        await self._workspace.select(sid, principal, current.selected_model_key,
                                     expected_generation=current.generation)
        adapter, selection = self._workspace.selected_context(sid, principal)
        adapter.assert_session_binding(self._auth, sid, principal)
        lease = _SelectionLease(self._auth, self._workspace, sid, principal, selection)
        repositories = await self._repositories.for_session(lease, sid, principal)
        lease.require_session(sid)
        settings = self._auth.settings
        turn = LLMTurnService(memory_repo=repositories.memory, snapshot_store=repositories.snapshots,
            llm_provider=None, llm_registry=self._llm, display_llm_registry=self._display,
            powerbi_adapter=adapter, report_renderer=build_report_dispatcher(
                SalesReportRenderer(), ExecutiveSalesReportRenderer()),
            report_repository=repositories.reports, settings=settings,
            config=HarnessConfig.from_settings(settings))
        return PreparedCloudProduct(turn, repositories, selection.conversation_id,
                                    selection.selected_model_key, lease)
