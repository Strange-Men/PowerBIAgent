"""Compose existing M5 services with M6.3 ownership; no alternate factual chain."""
from dataclasses import dataclass

from backend.app.application.deepseek_turn_service import LLMTurnService
from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_test_policy import CloudTestPolicy
from backend.app.config.settings import LLMMode,PowerBIMode
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

    async def _read_owned(self, sid, principal, operation, *, restores_selection=False):
        # Legacy snapshots lack a durable exact test-resource authorization
        # projection. Owner identity alone cannot authorize replay of BI facts.
        if self._test_policy.enabled: raise AuthFailure('AUTH_FORBIDDEN', 403)
        self._workspace.require_business_access(sid,principal)
        # Past resources are owner-scoped; viewing does not select a model or
        # restore business Memory. Storage is still explicitly supplied.
        self._validate_identity(sid, principal)
        lease = _SelectionLease(self._auth,self._workspace,sid,principal,self._workspace.status(sid,principal))
        repositories = await self._repositories.for_session(self._auth if restores_selection else lease, sid, principal)
        self._validate_identity(sid, principal)
        result = await operation(repositories)
        self._validate_identity(sid, principal)
        if not restores_selection: lease.require_session(sid)
        return result

    async def list_history(self, sid, principal, *, limit, cursor=None):
        async def read(repos):
            page=await repos.history_service.list_recent(self._mode(sid,principal),limit=limit,cursor=cursor)
            for item in page.items: await self._authorize(repos,sid,principal,item.conversation_id)
            return page
        return await self._read_owned(sid,principal,read)

    async def read_history(self, sid, principal, conversation_id, *, limit, cursor=None):
        async def read(repos):
            binding=await self._authorize(repos,sid,principal,conversation_id)
            page=await repos.history_service.get_history(self._mode(sid,principal),conversation_id,limit=limit,cursor=cursor)
            for item in page.items:
                if item.memory and item.memory.semantic_model_key not in (None,binding.model_key):
                    raise AuthFailure('AUTH_FORBIDDEN',403)
                if item.report and item.report.availability_status!='deleted':
                    artifact=await repos.report_metadata.get(item.report.report_id)
                    if artifact is None or (artifact.conversation_id,artifact.semantic_model_key,artifact.schema_fingerprint,artifact.source_mode)!=(
                            conversation_id,binding.model_key,binding.schema_fingerprint,binding.source_mode):
                        raise AuthFailure('AUTH_FORBIDDEN',403)
            return page
        return await self._read_owned(sid,principal,read)

    async def read_report(self, sid, principal, report_id):
        # Existing managed repository authorizes metadata before resolving files.
        # View and download consume the same checked artifact/HTML pair.
        async def read(repos):
            artifact=await repos.report_metadata.get(report_id)
            from backend.app.report.resources import ReportNotFoundError
            if artifact is None: raise ReportNotFoundError('report_not_found')
            binding=await self._authorize(repos,sid,principal,artifact.conversation_id)
            if (artifact.semantic_model_key,artifact.schema_fingerprint,artifact.source_mode)!=(
                binding.model_key,binding.schema_fingerprint,binding.source_mode):
                raise AuthFailure('AUTH_FORBIDDEN',403)
            return await repos.reports.read_html(report_id)
        return await self._read_owned(sid,principal,read)

    def _mode(self,sid,principal):
        return self._workspace.data_mode(sid,principal)

    async def _authorize(self,repos,sid,principal,conversation_id):
        binding=await repos.cloud_bindings.get(conversation_id)
        if binding is None: raise AuthFailure('AUTH_FORBIDDEN',403)
        await self._workspace.revalidate_binding(sid,principal,binding)
        self._validate_identity(sid,principal)
        return binding

    async def restore(self,sid,principal,conversation_id,expected_generation):
        async def restore(repos):
            binding=await repos.cloud_bindings.get(conversation_id)
            if binding is None: raise AuthFailure('AUTH_FORBIDDEN',403)
            # Prove the owner history root exists before restoring selection.
            await repos.history_service.get_history(self._mode(sid,principal),conversation_id,limit=1)
            return await self._workspace.revalidate_binding(sid,principal,binding,select=True,
                expected_generation=expected_generation)
        return await self._read_owned(sid,principal,restore,restores_selection=True)

    async def list_reports(self,sid,principal,*,limit,cursor=None):
        async def read(repos):
            page=await repos.history_service.list_managed_reports(self._mode(sid,principal),status='active',limit=limit,cursor=cursor)
            for item in page.items:
                binding=await self._authorize(repos,sid,principal,item.conversation_id)
                artifact=await repos.report_metadata.get(item.report_id)
                if artifact is None or (artifact.semantic_model_key,artifact.schema_fingerprint,artifact.source_mode)!=(
                        binding.model_key,binding.schema_fingerprint,binding.source_mode):
                    raise AuthFailure('AUTH_FORBIDDEN',403)
            return page
        return await self._read_owned(sid,principal,read)

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
        binding=await self._workspace.bound_projection(sid,principal)
        lease.require_session(sid)
        await repositories.cloud_bindings.save(binding)
        lease.require_session(sid)
        settings = self._auth.settings
        if adapter.is_mock:
            from backend.app.application.mock_turn_service import MockTurnService
            from backend.app.llm.mock import MockLLMProvider
            from backend.app.report.mock import MockReportRenderer
            turn=MockTurnService(memory_repo=repositories.memory,snapshot_store=repositories.snapshots,
                powerbi_adapter=adapter,llm_provider=MockLLMProvider(),report_renderer=build_report_dispatcher(
                    MockReportRenderer(),ExecutiveSalesReportRenderer()),report_repository=repositories.reports,
                config=HarnessConfig.from_settings(settings).model_copy(update={
                    'llm_mode':LLMMode.MOCK,'powerbi_mode':PowerBIMode.MOCK}))
        else:
            turn = LLMTurnService(memory_repo=repositories.memory, snapshot_store=repositories.snapshots,
            llm_provider=None, llm_registry=self._llm, display_llm_registry=self._display,
            powerbi_adapter=adapter, report_renderer=build_report_dispatcher(
                SalesReportRenderer(), ExecutiveSalesReportRenderer()),
            report_repository=repositories.reports, settings=settings,
            config=HarnessConfig.from_settings(settings))
        return PreparedCloudProduct(turn, repositories, selection.conversation_id,
                                    selection.selected_model_key, lease)

    async def chat(self,sid,principal,message,*,expected_generation,request_id,llm_profile_key=None,report_template_key=None):
        self._workspace.require_execution(sid,principal)
        current=self._workspace.status(sid,principal)
        if current.generation!=expected_generation:
            from backend.app.application.cloud_workspace_service import CloudSelectionConflict
            raise CloudSelectionConflict()
        if report_template_key is not None:
            templates=await self._workspace.templates(sid,principal)
            if not any(item.template_key==report_template_key and item.selectable for item in templates.items):
                raise AuthFailure('AUTH_FORBIDDEN',403)
        prepared=await self.prepare(sid,principal)
        if prepared._lease._selection.generation!=expected_generation:
            from backend.app.application.cloud_workspace_service import CloudSelectionConflict
            raise CloudSelectionConflict()
        return await prepared.execute(message,request_id=request_id,llm_profile_key=llm_profile_key,
                                      report_template_key=report_template_key)
