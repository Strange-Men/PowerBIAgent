"""Compose existing M5 services with M6.3 ownership; no alternate factual chain."""
import json
import logging
from dataclasses import dataclass
from time import monotonic

from backend.app.application.deepseek_turn_service import LLMTurnService
from backend.app.auth.models import AuthFailure
from backend.app.config.settings import LLMMode,PowerBIMode
from backend.app.harness.models import HarnessConfig
from backend.app.memory.models import RuntimeDataMode
from backend.app.report.executive import ExecutiveSalesReportRenderer
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.registry import build_report_dispatcher
from backend.app.application.cloud_product_runtime import require_cloud_business_data, require_native_workspace
from backend.app.application.cloud_operation import cloud_operation, cloud_stage


class _SelectionLease:
    """Repository validation projection; native Auth remains identity authority."""
    def __init__(self, auth, workspace, sid, principal, selection):
        self._auth, self._workspace = auth, workspace
        self._sid, self._principal, self._selection = sid, principal, selection
        self._policy_snapshot = workspace.policy_snapshot()

    def require_session(self, sid):
        if sid != self._sid: raise AuthFailure("AUTH_FORBIDDEN", 403)
        record = self._auth.require_session(sid)
        if record.principal != self._principal: raise AuthFailure("AUTH_FORBIDDEN", 403)
        if self._workspace.policy_snapshot() != self._policy_snapshot:
            raise AuthFailure('AUTH_FORBIDDEN',403)
        current = self._workspace.status(sid, self._principal)
        if (current.generation, current.selected_model_key, current.conversation_id) != (
                self._selection.generation, self._selection.selected_model_key, self._selection.conversation_id):
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        return record

    async def revalidate_resource(self):
        """Microsoft access is re-proven at a long-running durable commit."""
        self.require_session(self._sid)
        if not self._auth.settings.fabric_test_mode and not self._workspace._synthetic_product:
            await self._workspace.select(self._sid, self._principal,
                self._selection.selected_model_key, expected_generation=self._selection.generation)
        self.require_session(self._sid)


class _ResourceLease(_SelectionLease):
    """Reuse the adapter's current access witness at each storage boundary."""
    def __init__(self,*args,adapter,binding):
        super().__init__(*args)
        self._adapter,self._binding=adapter,binding

    def require_session(self,sid):
        record=super().require_session(sid)
        self._workspace.require_persistence(sid,self._principal,binding=self._binding)
        self._adapter.assert_session_binding(self._auth,sid,self._principal)
        if self._adapter.bound_resource_identity(self._binding.model_key)!=(
                str(self._binding.workspace_id),str(self._binding.model_id)):
            raise AuthFailure('AUTH_FORBIDDEN',403)
        return record

    async def revalidate_resource(self):
        self.require_session(self._sid)
        if not self._auth.settings.fabric_test_mode and not self._workspace._synthetic_product:
            await self._workspace.revalidate_binding(self._sid, self._principal, self._binding,
                expected_generation=self._selection.generation)
        self.require_session(self._sid)


class _MetadataResourceLease(_ResourceLease):
    """Resource metadata mutations prove current access, not schema identity.

    Rename/archive/delete change ownership-scoped metadata.  The current
    Microsoft resource access, the durable owner binding and the persistence
    capability are still proven, but no semantic schema is restored and no
    schema fingerprint is recomputed.
    """

    async def revalidate_resource(self):
        self.require_session(self._sid)
        if not self._auth.settings.fabric_test_mode and not self._workspace._synthetic_product:
            await self._workspace.authorize_persisted_summary(
                self._sid, self._principal, self._binding)
        self.require_session(self._sid)


class _NativeCloudTurnService(LLMTurnService):
    """Enforce Cloud policy even for direct server-side embedding.

    A generic bounded LLM prompt/Trace is not enterprise disclosure consent.
    Reuse the current closed workspace gate before any Core/provider activity.
    No new setting, provider or client capability can bypass that gate.
    """
    def __init__(self, *, lease, **kwargs):
        super().__init__(**kwargs)
        self._cloud_lease = lease

    async def execute(self, *args, **kwargs):
        lease = self._cloud_lease
        lease.require_session(lease._sid)
        lease._workspace.require_execution(lease._sid, lease._principal)
        require_cloud_business_data(lease._workspace,lease._sid,lease._principal)
        from backend.app.application.cloud_literal_context import literal_scope
        with literal_scope():
            result = await super().execute(*args, **kwargs)
        lease.require_session(lease._sid)
        return result

    async def _do_conversation(self, **kwargs):
        result = await super()._do_conversation(**kwargs)
        from backend.app.application.cloud_literal_context import capture_frame
        capture_frame(kwargs['message'], result.get('_semantic_frame'))
        return result


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
        require_cloud_business_data(lease._workspace,lease._sid,lease._principal)
        result = await self.turn_service.execute(message,
            conversation_id=self.conversation_id, request_id=request_id,
            semantic_model_key=self.semantic_model_key, llm_profile_key=llm_profile_key,
            report_template_key=report_template_key)
        lease.require_session(lease._sid)
        return result


class CloudProductServiceFactory:
    """Storage must be explicitly supplied; no default DB opening or migration."""
    def __init__(self, auth, workspace, repository_factory, llm_registry, display_llm_registry,
                 *, synthetic_turn_factory=None):
        self._auth, self._workspace, self._repositories = auth, workspace, repository_factory
        self._llm, self._display = llm_registry, display_llm_registry
        # Trusted host injection only; never a setting or client execution flag.
        # The native branch cannot use a synthetic runtime or gain readiness.
        self._synthetic_turn_factory = synthetic_turn_factory

    def _validate_identity(self, sid, principal):
        if self._auth.require_session(sid).principal != principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    async def _read_owned(self, sid, principal, operation, *, restores_selection=False):
        # Owner storage access does not grant replay: each result below must
        # prove its durable exact binding and current target capability.
        require_native_workspace(self._workspace)
        self._workspace.require_persistence(sid,principal)
        # Past resources are owner-scoped; viewing does not select a model or
        # restore business Memory. Storage is still explicitly supplied.
        self._validate_identity(sid, principal)
        lease = _SelectionLease(self._auth,self._workspace,sid,principal,self._workspace.status(sid,principal))
        repositories = await self._repositories.for_session(self._auth if restores_selection else lease, sid, principal)
        self._validate_identity(sid, principal)
        result = await operation(repositories)
        self._validate_identity(sid, principal)
        if self._workspace.policy_snapshot() != lease._policy_snapshot:
            raise AuthFailure('AUTH_FORBIDDEN',403)
        if not restores_selection: lease.require_session(sid)
        return result

    async def list_history(self, sid, principal, *, limit, cursor=None, status='active', query=None):
        async def read(repos):
            access_proofs=set()
            mode=self._mode(sid,principal)
            if query is not None:
                page=await repos.history_service.search(mode,query=query,limit=limit,cursor=cursor)
            elif status=='archived':
                page=await repos.history_service.list_archived(mode,limit=limit,cursor=cursor)
            else:
                page=await repos.history_service.list_recent(mode,limit=limit,cursor=cursor)
            for item in page.items: await self._authorize(repos,sid,principal,item.conversation_id,
                access_proofs=access_proofs,metadata_only=True)
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

    async def _presentation_read(self,sid,principal,request_id,*,expected_generation=None,report_id=None,locale='zh-CN'):
        """Revalidate access; a new login restores metadata, never reexecutes facts."""
        from backend.app.application.cloud_workspace_service import CloudSelectionConflict
        from backend.app.presentation.projection import project_snapshot,render_snapshot_report
        from backend.app.presentation.localization import JsonDisplayLocalizationRegistry
        from backend.app.report.resources import ReportNotFoundError
        async def read(repos):
            current=self._workspace._context(sid,principal)
            adapter,selection=current.adapter,self._workspace.status(sid,principal)
            if expected_generation is not None and selection.generation!=expected_generation:
                raise CloudSelectionConflict()
            artifact=None
            effective_id=request_id
            if report_id is not None:
                artifact=await repos.report_metadata.get(report_id)
                if artifact is None: raise ReportNotFoundError('report_not_found')
                effective_id=artifact.request_id
            snapshot=await repos.snapshots.get(effective_id,self._mode(sid,principal))
            if snapshot is None: raise ReportNotFoundError('resource_not_found')
            binding=await repos.cloud_bindings.get(snapshot.conversation_id)
            if binding is None:
                raise AuthFailure('AUTH_FORBIDDEN',403)
            await self._workspace._verify_exact_resource(sid, principal,
                str(binding.workspace_id), str(binding.model_id))
            try:
                adapter.bound_resource_identity(binding.model_key)
            except AuthFailure:
                raise
            except Exception as error:
                from backend.app.powerbi.fabric_iq import FabricIQPowerBIAdapter
                from backend.app.powerbi.base import PowerBIAdapterError
                # Only a native new-login adapter with no historical key may
                # reacquire metadata. Permission failures are never recovery.
                if not (isinstance(adapter, FabricIQPowerBIAdapter)
                        and isinstance(error, PowerBIAdapterError)
                        and error.error_type == 'RESOURCE_NOT_ACCESSIBLE'):
                    raise
                await self._workspace.revalidate_binding(sid,principal,binding)
            lease=_ResourceLease(self._auth,self._workspace,sid,principal,selection,adapter=adapter,binding=binding)
            lease.require_session(sid)
            recipe=snapshot.presentation_recipe
            key=recipe.report_spec.semantic_model_key if recipe and recipe.report_spec else recipe.plan.semantic_model_key if recipe else None
            if key is not None and key!=binding.model_key: raise AuthFailure('AUTH_FORBIDDEN',403)
            if snapshot.source_mode!=binding.source_mode: raise AuthFailure('AUTH_FORBIDDEN',403)
            if recipe is not None:
                source=recipe.report_spec if recipe.report_spec is not None else recipe.result
                fingerprint=recipe.report_spec.schema_fingerprint if recipe.report_spec is not None else recipe.schema_fingerprint
                if source.source_mode!=binding.source_mode or fingerprint!=binding.schema_fingerprint:
                    raise AuthFailure('AUTH_FORBIDDEN',403)
            if artifact is not None:
                _,_=await repos.reports.read_html(report_id)
                renderer=build_report_dispatcher(SalesReportRenderer(),ExecutiveSalesReportRenderer())
                output=await render_snapshot_report(snapshot,artifact,locale,renderer)
            else:
                registry=JsonDisplayLocalizationRegistry(self._auth.settings.presentation_localization_registry_path)
                output=await project_snapshot(snapshot,locale,registry=registry)
            lease.require_session(sid)
            await self._workspace._verify_exact_resource(sid, principal,
                str(binding.workspace_id), str(binding.model_id))
            lease.require_session(sid)
            return output
        return await self._read_owned(sid,principal,read)

    async def project_presentation(self,sid,principal,request_id,locale,expected_generation):
        return await self._presentation_read(sid,principal,request_id,locale=locale,expected_generation=expected_generation)

    async def localized_report(self,sid,principal,report_id,locale):
        return await self._presentation_read(sid,principal,None,report_id=report_id,locale=locale)

    def _mode(self,sid,principal):
        return self._workspace.data_mode(sid,principal)

    async def _authorize(self,repos,sid,principal,conversation_id,*,access_proofs=None,metadata_only=False):
        binding=await repos.cloud_bindings.get(conversation_id)
        if binding is None: raise AuthFailure('AUTH_FORBIDDEN',403)
        # Owned binding/grant checks still run for every row. Only a fresh
        # access proof from this same HTTP operation can cover the same exact
        # model and schema. No state survives this list request.
        proof=(binding.workspace_id,binding.model_id,binding.schema_fingerprint,binding.source_mode)
        if metadata_only and not self._auth.settings.fabric_test_mode and not self._workspace._synthetic_product:
            if access_proofs is None or proof not in access_proofs:
                await self._workspace.authorize_persisted_summary(sid,principal,binding)
            self._workspace.require_persistence(sid,principal)
            self._validate_identity(sid,principal)
            if access_proofs is not None: access_proofs.add(proof)
            return binding
        if access_proofs is None or proof not in access_proofs:
            await self._workspace.revalidate_binding(sid,principal,binding)
        self._validate_identity(sid,principal)
        self._workspace.require_persistence(sid,principal,binding=binding)
        if access_proofs is not None: access_proofs.add(proof)
        return binding

    async def restore(self,sid,principal,conversation_id,expected_generation):
        async def restore(repos):
            binding=await repos.cloud_bindings.get(conversation_id)
            if binding is None: raise AuthFailure('AUTH_FORBIDDEN',403)
            # Prove the owner history root exists before restoring selection.
            await repos.history_service.get_history(self._mode(sid,principal),conversation_id,limit=1)
            result = await self._workspace.revalidate_binding(sid,principal,binding,select=True,
                expected_generation=expected_generation)
            self._workspace.require_persistence(sid,principal,binding=binding)
            return result
        return await self._read_owned(sid,principal,restore,restores_selection=True)

    async def list_reports(self,sid,principal,*,limit,cursor=None,status='active'):
        async def read(repos):
            access_proofs=set()
            page=await repos.history_service.list_managed_reports(self._mode(sid,principal),status=status,limit=limit,cursor=cursor)
            for item in page.items:
                binding=await self._authorize(repos,sid,principal,item.conversation_id,
                    access_proofs=access_proofs,metadata_only=True)
                artifact=await repos.report_metadata.get(item.report_id)
                if artifact is None or (artifact.semantic_model_key,artifact.schema_fingerprint,artifact.source_mode)!=(
                        binding.model_key,binding.schema_fingerprint,binding.source_mode):
                    raise AuthFailure('AUTH_FORBIDDEN',403)
            return page
        return await self._read_owned(sid,principal,read)

    async def mutate_resource(self,sid,principal,kind,resource_id,action,*,expected_generation,title=None):
        """Explicit Resource API only; reuse the original durable lifecycle.

        Preparation uses auth-only repositories to prove the target. Writes
        use a fresh selection lease, so a prior chat cannot commit after a
        destructive operation invalidates its generation.
        """
        from backend.app.application.cloud_workspace_service import CloudSelectionConflict
        from backend.app.report.resources import ReportNotFoundError
        if kind not in {'history','reports'} or action not in {'rename','archive','unarchive','delete'}:
            raise AuthFailure('AUTH_FORBIDDEN',403)
        async def mutate(repos):
            timing = {'kind': kind, 'action': action, 'schema_restore': False}
            started = monotonic()
            if self._workspace.status(sid,principal).generation!=expected_generation:
                raise CloudSelectionConflict()
            artifact=None
            conversation_id=resource_id
            if kind=='reports':
                artifact=await (repos.report_metadata.get_for_delete(resource_id) if action=='delete'
                    else repos.report_metadata.get(resource_id))
                if artifact is None: raise ReportNotFoundError('report_not_found')
                conversation_id=artifact.conversation_id
            # FIX5: metadata mutations prove current Microsoft resource access
            # and persistence capability.  Semantic schema identity is not part
            # of a rename/archive/delete decision and is never restored here.
            binding=await self._authorize(repos,sid,principal,conversation_id,metadata_only=True)
            timing['authorization_ms'] = round((monotonic()-started)*1000, 2)
            if artifact is not None and (artifact.semantic_model_key,artifact.schema_fingerprint,artifact.source_mode)!=(
                    binding.model_key,binding.schema_fingerprint,binding.source_mode):
                raise AuthFailure('AUTH_FORBIDDEN',403)
            current=self._workspace.status(sid,principal)
            if current.generation!=expected_generation: raise CloudSelectionConflict()
            if kind=='history' and action in {'archive','delete'} and current.conversation_id==resource_id:
                current=await self._workspace.new_chat(sid,principal,expected_generation)
            adapter=self._workspace._context(sid,principal).adapter
            lease=_MetadataResourceLease(self._auth,self._workspace,sid,principal,current,adapter=adapter,binding=binding)
            writable=await self._repositories.for_session(lease,sid,principal)
            lease.require_session(sid)
            timing['preparation_ms'] = round((monotonic()-started)*1000, 2)
            service=writable.history_service if kind=='history' else writable.reports
            method='restore' if action=='unarchive' else action
            if kind=='history':
                args=(self._mode(sid,principal),resource_id)
            else:
                args=(resource_id,)
                if action in {'archive','unarchive'}: args+=(self._mode(sid,principal).value,)
            if action=='rename': args+=(title,)
            mutation_started = monotonic()
            result=await getattr(service,method)(*args)
            if kind=='history' and action=='delete': await writable.cloud_bindings.delete(resource_id)
            timing['persistence_ms'] = round((monotonic()-mutation_started)*1000, 2)
            lease.require_session(sid)
            # Current access, not history ownership, authorizes the response.
            response_started = monotonic()
            if action!='delete': await self._authorize(writable,sid,principal,conversation_id,metadata_only=True)
            lease.require_session(sid)
            status = self._workspace.status(sid,principal)
            timing['response_refresh_ms'] = round((monotonic()-response_started)*1000, 2)
            timing['total_ms'] = round((monotonic()-started)*1000, 2)
            # Local development trace only: operation names and durations,
            # never titles, members, rows, prompts or credentials.
            logging.getLogger('powerbiagent.cloud').info(
                'cloud_mutation_timing %s',
                json.dumps(timing, separators=(',', ':')),
            )
            return {'resource':result,'workspace_status':status}
        return await self._read_owned(sid,principal,mutate,restores_selection=True)

    @cloud_operation
    @cloud_stage('persistence','persistence')
    async def prepare(self, sid, principal):
        # The three independent operator grants precede Core and storage.
        require_native_workspace(self._workspace)
        self._workspace.require_execution(sid,principal)
        require_cloud_business_data(self._workspace,sid,principal)
        current = self._workspace.status(sid, principal)
        if current.selected_model_key is None: raise AuthFailure("AUTH_FORBIDDEN", 403)
        await self._workspace.select(sid, principal, current.selected_model_key,
                                     expected_generation=current.generation)
        adapter, selection = self._workspace.selected_context(sid, principal)
        adapter.assert_session_binding(self._auth, sid, principal)
        require_cloud_business_data(self._workspace,sid,principal)
        lease = _SelectionLease(self._auth, self._workspace, sid, principal, selection)
        repositories = await self._repositories.for_session(lease, sid, principal)
        lease.require_session(sid)
        binding=await self._workspace.bound_projection(sid,principal)
        lease.require_session(sid)
        await repositories.cloud_bindings.save(binding)
        lease.require_session(sid)
        settings = self._auth.settings
        if adapter.is_mock:
            if self._synthetic_turn_factory is not None:
                turn = self._synthetic_turn_factory(adapter=adapter, repositories=repositories,
                    settings=settings)
                return PreparedCloudProduct(turn, repositories, selection.conversation_id,
                                            selection.selected_model_key, lease)
            from backend.app.application.mock_turn_service import MockTurnService
            from backend.app.llm.mock import MockLLMProvider
            from backend.app.report.mock import MockReportRenderer
            turn=MockTurnService(memory_repo=repositories.memory,snapshot_store=repositories.snapshots,
                powerbi_adapter=adapter,llm_provider=MockLLMProvider(),report_renderer=build_report_dispatcher(
                    MockReportRenderer(),ExecutiveSalesReportRenderer()),report_repository=repositories.reports,
                config=HarnessConfig.from_settings(settings).model_copy(update={
                    'llm_mode':LLMMode.MOCK,'powerbi_mode':PowerBIMode.MOCK}))
        else:
            turn = _NativeCloudTurnService(lease=lease,
            memory_repo=repositories.memory, snapshot_store=repositories.snapshots,
            llm_provider=None, llm_registry=self._llm, display_llm_registry=self._display,
            powerbi_adapter=adapter, report_renderer=build_report_dispatcher(
                SalesReportRenderer(), ExecutiveSalesReportRenderer()),
            report_repository=repositories.reports, settings=settings,
            config=HarnessConfig.from_settings(settings))
        return PreparedCloudProduct(turn, repositories, selection.conversation_id,
                                    selection.selected_model_key, lease)

    @cloud_operation
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
