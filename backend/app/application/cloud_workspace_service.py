"""Session-bound Cloud control plane. Business execution remains fact-gated."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4
from time import monotonic

from pydantic import BaseModel, ConfigDict

from backend.app.application.cloud_catalog_service import CloudCatalogService
from backend.app.auth.models import AuthFailure
from backend.app.config.cloud_test_policy import CloudTestPolicy
from backend.app.config.cloud_product_policy import CloudProductAuthorizationPolicy
from backend.app.application.cloud_catalog_pages import CurrentPrincipalCatalog
from backend.app.harness.errors import ToolExecutionError
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext, ToolGateway
from backend.app.harness.tool_registry import SchemaInput, TOOL_NAME_SCHEMA, register_schema_tool
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.cloud_catalog_transport import FabricCatalogTransport
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.schemas.data_contracts import UserContext


class CloudWorkspaceStatus(BaseModel):
    selected_model_key: str | None = None
    conversation_id: str | None = None
    generation: int = 0
    execution_ready: bool = False
    blockers: tuple[Literal["numeric_contract", "query_completeness", "operator_approval"], ...] = (
        "numeric_contract", "query_completeness")
    model_config = ConfigDict(extra="forbid", frozen=True)


class CloudSelectionConflict(ValueError):
    def __init__(self): super().__init__("cloud_selection_changed")


class _BindingKey(BaseModel):
    model_key: str
    model_config=ConfigDict(extra='forbid',frozen=True)


@dataclass(frozen=True)
class _ResourceAuthorization:
    tenant_id: str
    principal_id: str
    workspace_id: str
    model_id: str
    semantic_model_key: str
    schema_fingerprint: str
    source_mode: str
    generation: int
    authorization_epoch: int
    evidence: str = 'current-principal exact resource + IQ schema'


@dataclass
class _SessionWorkspace:
    principal: object
    adapter: object
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    keys: set = field(default_factory=set)
    selected: str | None = None
    conversation_id: str | None = None
    generation: int = 0
    catalog_pages: CurrentPrincipalCatalog = field(default_factory=CurrentPrincipalCatalog)
    schema_fingerprint: str | None = None
    selected_display_name: str | None = None
    authorization: _ResourceAuthorization | None = None


class CloudWorkspaceService:
    def __init__(self, auth, adapter_factory, *, shared_seeds=(),
                 rest_factory=FabricCatalogTransport, synthetic_product=False):
        self._auth, self._factory = auth, adapter_factory
        self._seeds, self._rest_factory = tuple(shared_seeds), rest_factory
        self._contexts = {}
        self._closed = False
        # Explicit offline host composition; never inferred from adapter flags.
        self._synthetic_product = synthetic_product is True
        self._product_policy = CloudProductAuthorizationPolicy(auth.settings)

    @property
    def context_count(self): return len(self._contexts)

    def _validate(self, sid, principal):
        if self._closed or self._auth.require_session(sid).principal != principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    def _context(self, sid, principal):
        self._validate(sid, principal)
        current = self._contexts.get(sid)
        if current is None:
            if len(self._contexts) >= self._auth.settings.auth_store_capacity:
                raise fail("UPSTREAM_UNAVAILABLE")
            current = _SessionWorkspace(principal, self._factory.create_product(sid, principal))
            self._contexts[sid] = current
        if current.principal != principal: raise AuthFailure("AUTH_FORBIDDEN", 403)
        return current

    @staticmethod
    def _clear_selection(current):
        current.selected = current.conversation_id = None
        current.schema_fingerprint = current.selected_display_name = None
        current.authorization = None
        current.generation += 1

    @asynccontextmanager
    async def _metadata_operation(self, current):
        # The request budget includes waiting for another metadata operation.
        # A queued timeout owns no selection state and must not clear its peer.
        deadline = monotonic() + self._auth.settings.request_timeout_seconds
        try:
            async with asyncio.timeout(self._auth.settings.request_timeout_seconds):
                async with current.lock:
                    yield deadline
        except TimeoutError:
            raise fail("QUERY_TIMEOUT") from None

    async def catalog(self, sid, principal):
        await self.prune()
        current = self._context(sid, principal)
        if not self._auth.settings.fabric_test_mode and not self._synthetic_product:
            from backend.app.application.cloud_catalog_service import CloudModelCatalog, CloudModelOption
            # Bootstrap performs no REST enumeration, IQ Resolve or Schema.
            items = [CloudModelOption(key=current.selected, display_name=current.selected_display_name,
                workspace_display_name='Microsoft Fabric')] if current.selected and current.selected_display_name else []
            return CloudModelCatalog(status='partial', items=items, product_mode=True,
                persistence_enabled=self._product_policy.storage_enabled())
        async with self._metadata_operation(current) as deadline:
            self._validate(sid, principal)
            try:
                async with asyncio.timeout(self._auth.settings.request_timeout_seconds):
                    async with self._rest_factory(self._auth, sid, principal) as rest:
                        catalog = await CloudCatalogService(self._auth, sid, principal, rest,
                            current.adapter, shared_seeds=self._seeds, deadline=deadline).discover()
                self._validate(sid, principal)
            except TimeoutError:
                current.keys.clear()
                self._clear_selection(current)
                raise fail("QUERY_TIMEOUT") from None
            except BaseException:
                current.keys.clear()
                self._clear_selection(current)
                raise
            current.keys = {item.key for item in catalog.items}
            if current.selected and current.selected not in current.keys:
                self._clear_selection(current)
            return catalog

    async def browse(self, sid, principal, *, workspace_key=None, kind='SemanticModel', query='', cursor=None):
        current = self._context(sid, principal)
        if self._auth.settings.fabric_test_mode: raise AuthFailure('AUTH_FORBIDDEN', 403)
        async with self._metadata_operation(current):
            self._validate(sid, principal)
            async with self._rest_factory(self._auth, sid, principal) as rest:
                if workspace_key is None:
                    page = await current.catalog_pages.workspaces(rest, query=query, cursor=cursor)
                else:
                    ws = current.catalog_pages.workspace(workspace_key)
                    await rest.verify_resource(ws)
                    page = await current.catalog_pages.resources(rest, workspace_key, kind=kind, query=query, cursor=cursor)
            self._validate(sid, principal)
            return page

    async def _verify_exact_resource(self, sid, principal, ws, model):
        if self._auth.settings.fabric_test_mode or self._synthetic_product: return
        try:
            async with self._rest_factory(self._auth, sid, principal) as rest:
                await rest.verify_resource(ws)
                await rest.verify_resource(ws, model, 'SemanticModel')
            self._validate(sid, principal)
        except BaseException:
            current = self._contexts.get(sid)
            proof = current.authorization if current else None
            if proof and (proof.workspace_id, proof.model_id) == (ws, model):
                current.keys.discard(proof.semantic_model_key)
                self._clear_selection(current)
            raise

    async def select(self, sid, principal, key, *, expected_generation=None):
        current = self._context(sid, principal)
        async with self._metadata_operation(current):
            self._validate(sid, principal)
            candidate = None
            if key not in current.keys:
                if self._auth.settings.fabric_test_mode or self._synthetic_product:
                    raise AuthFailure('AUTH_FORBIDDEN', 403)
                candidate = current.catalog_pages.candidate(key)
            if expected_generation is not None and expected_generation != current.generation:
                raise CloudSelectionConflict()
            if key not in current.keys:
                async with self._rest_factory(self._auth, sid, principal) as rest:
                    await rest.verify_resource(candidate.workspace_id)
                    await rest.verify_resource(candidate.workspace_id, candidate.item_id, candidate.kind)
                self._validate(sid, principal)
                from backend.app.harness.runtime.tool_gateway import ToolSpec
                async def bind(_):
                    method = current.adapter.bind_catalog_model if candidate.kind == 'SemanticModel' else current.adapter.bind_catalog_report
                    ref = await method(candidate.workspace_id, candidate.item_id)
                    return _BindingKey(model_key=ref.server_model_key)
                gateway = ToolGateway()
                gateway.register(ToolSpec(name='bind_selected_cloud_resource', input_model=_BindingKey,
                    output_model=_BindingKey, handler=bind, max_retries=0, read_only=True,
                    allowed_intents=[IntentType.DATA_QUESTION], supported_modes=[RuntimeDataMode.REAL]))
                result = await gateway.execute('bind_selected_cloud_resource', ToolExecutionContext(
                    runtime_mode=RuntimeDataMode.REAL, intent=IntentType.DATA_QUESTION,
                    user=UserContext(allowed_tools=['bind_selected_cloud_resource'])), _BindingKey(model_key=key))
                self._validate(sid, principal)
                key = result.model_key
                current.keys.add(key)
            ws, model = current.adapter.bound_resource_identity(key)
            await self._verify_exact_resource(sid, principal, ws, model)
            gateway = ToolGateway()
            register_schema_tool(gateway, current.adapter, HarnessConfig.from_settings(self._auth.settings))
            context = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,
                intent=IntentType.DATA_QUESTION, user=UserContext(
                    allowed_tools=[TOOL_NAME_SCHEMA], allowed_semantic_models=[key]))
            try:
                schema = await gateway.execute(TOOL_NAME_SCHEMA, context, SchemaInput(semantic_model_key=key))
                self._validate(sid, principal)
                if schema.key != key: raise fail("CONTRACT_DRIFT")
                from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
                fingerprint = compute_schema_fingerprint(schema)
                if not self._synthetic_product and current.selected == key and current.schema_fingerprint not in (None, fingerprint):
                    raise fail('CONTRACT_DRIFT')
            except BaseException as error:
                current.keys.discard(key)
                if current.selected == key: self._clear_selection(current)
                if isinstance(error, ToolExecutionError) and isinstance(error.__context__, AuthFailure):
                    raise error.__context__
                raise
            if current.selected != key:
                self._clear_selection(current)
                current.selected = key
                current.conversation_id = str(uuid4())
            current.schema_fingerprint = fingerprint
            current.selected_display_name = schema.name
            current.authorization = _ResourceAuthorization(principal.tenant_id, principal.principal_id,
                ws, model, key, fingerprint, 'mock' if current.adapter.is_mock else 'real',
                current.generation, principal.authorization_epoch)
            return self.status(sid, principal)

    def status(self, sid, principal):
        current = self._context(sid, principal)
        ready = self._capability(current, 'query_execution')
        return CloudWorkspaceStatus(selected_model_key=current.selected,
            conversation_id=current.conversation_id, generation=current.generation,
            execution_ready=ready, blockers=() if ready else ('operator_approval',))

    def _capability(self, current, name, *, binding=None):
        if self._synthetic_product and current.adapter.is_mock:
            return True
        if binding is not None:
            if self._auth.settings.fabric_test_mode:
                return self._product_policy.capability(binding.workspace_id, binding.model_id, name, binding_verified=True)
            key = getattr(binding, 'model_key', current.selected)
            try:
                identity = current.adapter.bound_resource_identity(key)
            except Exception:
                return False
            verified = identity == (str(binding.workspace_id), str(binding.model_id))
            return self._product_policy.capability(binding.workspace_id, binding.model_id, name, binding_verified=verified)
        if current.selected is None or current.selected not in current.keys:
            return False
        try:
            ws, model = current.adapter.bound_resource_identity(current.selected)
        except (AuthFailure, PowerBIAdapterError):
            current.keys.discard(current.selected)
            self._clear_selection(current)
            return False
        proof = current.authorization
        verified = proof is not None and (
            proof.tenant_id, proof.principal_id, proof.workspace_id, proof.model_id,
            proof.semantic_model_key, proof.schema_fingerprint, proof.generation, proof.authorization_epoch
        ) == (current.principal.tenant_id, current.principal.principal_id, ws, model,
            current.selected, current.schema_fingerprint, current.generation, current.principal.authorization_epoch)
        return self._product_policy.capability(ws, model, name,
            binding_verified=verified)

    def policy_snapshot(self):
        return self._product_policy.snapshot()

    def require_execution(self, sid, principal):
        self._validate(sid, principal)
        if not self._capability(self._context(sid, principal), 'query_execution'):
            raise AuthFailure("AUTH_FORBIDDEN", 403, denial_reason='cloud_execution_blocked')

    def require_resource_access(self, sid, principal, key):
        current = self._context(sid, principal)
        if key not in current.keys: raise fail('RESOURCE_NOT_ACCESSIBLE')
        # Binding validates current identity and operator test scope separately
        # from Microsoft's Resolve/Schema proof acquired by the service.
        current.adapter.bound_resource_identity(key)

    def require_disclosure(self, sid, principal):
        self._validate(sid, principal)
        if not self._capability(self._context(sid, principal), 'external_llm_disclosure'):
            raise AuthFailure('AUTH_FORBIDDEN',403,denial_reason='cloud_disclosure_blocked')

    def require_persistence(self, sid, principal, *, binding=None):
        self._validate(sid, principal)
        current = self._context(sid, principal)
        granted = (self._capability(current, 'business_persistence', binding=binding) if binding is not None
            else (self._synthetic_product and current.adapter.is_mock) or self._product_policy.storage_enabled())
        if not granted:
            raise AuthFailure('AUTH_FORBIDDEN',403,denial_reason='cloud_persistence_blocked')

    async def authorize_persisted_summary(self, sid, principal, binding):
        """Owner-scoped list metadata is not executable Memory restoration.

        Fresh REST access authorizes a historical summary without eagerly
        resolving/schema-loading every model in the user's history at login.
        Restore, execution and full factual reads still require native schema.
        """
        self.require_persistence(sid, principal)
        if binding.source_mode != self.data_mode(sid, principal).value:
            raise AuthFailure('AUTH_FORBIDDEN', 403)
        await self._verify_exact_resource(sid, principal, str(binding.workspace_id), str(binding.model_id))
        self._validate(sid, principal)
        if not self._product_policy.capability(str(binding.workspace_id), str(binding.model_id),
                'business_persistence', binding_verified=True):
            raise AuthFailure('AUTH_FORBIDDEN', 403, denial_reason='cloud_persistence_blocked')

    def data_mode(self,sid,principal):
        return RuntimeDataMode.MOCK if self._context(sid,principal).adapter.is_mock else RuntimeDataMode.REAL

    async def bound_projection(self, sid, principal):
        from backend.app.persistence.cloud_bindings import CloudConversationBinding
        from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
        current = self._context(sid, principal)
        async with self._metadata_operation(current):
            self._validate(sid, principal)
            if current.selected not in current.keys: raise AuthFailure('AUTH_FORBIDDEN',403)
            ws, model = current.adapter.bound_resource_identity(current.selected)
            await self._verify_exact_resource(sid, principal, ws, model)
            gateway = ToolGateway()
            register_schema_tool(gateway,current.adapter,HarnessConfig.from_settings(self._auth.settings))
            schema = await gateway.execute(TOOL_NAME_SCHEMA,ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,
                intent=IntentType.DATA_QUESTION,user=UserContext(allowed_tools=[TOOL_NAME_SCHEMA],
                    allowed_semantic_models=[current.selected])),SchemaInput(semantic_model_key=current.selected))
            self._validate(sid,principal)
            if schema.key!=current.selected: raise fail('CONTRACT_DRIFT')
            if not self._synthetic_product and compute_schema_fingerprint(schema) != current.schema_fingerprint:
                current.keys.discard(current.selected)
                self._clear_selection(current)
                raise fail('CONTRACT_DRIFT')
            ws, model = current.adapter.bound_resource_identity(current.selected)
            return CloudConversationBinding(conversation_id=current.conversation_id,model_key=current.selected,
                workspace_id=ws,model_id=model,schema_fingerprint=compute_schema_fingerprint(schema),
                source_mode='mock' if current.adapter.is_mock else 'real')

    async def revalidate_binding(self, sid, principal, binding, *, select=False, expected_generation=None):
        from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
        from backend.app.powerbi.fabric_iq import FabricIQPowerBIAdapter
        from backend.app.schemas.data_contracts import SemanticModelSchema
        current = self._context(sid,principal)
        async with self._metadata_operation(current):
            self._validate(sid,principal)
            if expected_generation is not None and current.generation!=expected_generation:
                raise CloudSelectionConflict()
            if binding.source_mode != ('mock' if current.adapter.is_mock else 'real'):
                raise AuthFailure('AUTH_FORBIDDEN',403)
            await self._verify_exact_resource(sid, principal, str(binding.workspace_id), str(binding.model_id))
            # Wrap provider Resolve+Schema in the same metadata ToolGateway.
            native_iq=isinstance(current.adapter, FabricIQPowerBIAdapter)
            async def restore(_):
                if native_iq:
                    return await current.adapter.restore_bound_schema(
                        str(binding.workspace_id), str(binding.model_id), binding.model_key)
                ref = await current.adapter.restore_bound_model(str(binding.workspace_id),str(binding.model_id),binding.model_key)
                return _BindingKey(model_key=ref.server_model_key)
            from backend.app.harness.runtime.tool_gateway import ToolSpec
            gateway=ToolGateway()
            gateway.register(ToolSpec(name='restore_cloud_binding',input_model=_BindingKey,
                output_model=SemanticModelSchema if native_iq else _BindingKey,
                handler=restore,read_only=True,max_retries=0,allowed_intents=[IntentType.DATA_QUESTION],
                supported_modes=[RuntimeDataMode.REAL]))
            context=ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,intent=IntentType.DATA_QUESTION,
                user=UserContext(allowed_tools=['restore_cloud_binding',TOOL_NAME_SCHEMA],allowed_semantic_models=[binding.model_key]))
            try:
                restored=await gateway.execute('restore_cloud_binding',context,_BindingKey(model_key=binding.model_key))
                if native_iq:
                    schema=restored
                    key=schema.key
                else:
                    key=restored.model_key
                    register_schema_tool(gateway,current.adapter,HarnessConfig.from_settings(self._auth.settings))
                    schema=await gateway.execute(TOOL_NAME_SCHEMA,context,SchemaInput(semantic_model_key=key))
                self._validate(sid,principal)
                if key!=binding.model_key or schema.key!=key or compute_schema_fingerprint(schema)!=binding.schema_fingerprint:
                    raise AuthFailure('AUTH_FORBIDDEN',403)
            except BaseException:
                current.keys.discard(binding.model_key)
                if current.selected == binding.model_key: self._clear_selection(current)
                raise
            if select:
                current.keys.add(key)
                self._clear_selection(current)
                current.selected,current.conversation_id=key,binding.conversation_id
                current.schema_fingerprint = binding.schema_fingerprint
                current.selected_display_name = schema.name
                current.authorization = _ResourceAuthorization(principal.tenant_id, principal.principal_id,
                    str(binding.workspace_id), str(binding.model_id), key, binding.schema_fingerprint,
                    binding.source_mode, current.generation, principal.authorization_epoch)
            return self.status(sid,principal)

    async def new_chat(self,sid,principal,expected_generation):
        current=self._context(sid,principal)
        async with self._metadata_operation(current):
            self._validate(sid,principal)
            if expected_generation!=current.generation: raise CloudSelectionConflict()
            if current.selected not in current.keys: raise AuthFailure('AUTH_FORBIDDEN',403)
            current.generation+=1
            current.conversation_id=str(uuid4())
            if current.authorization is not None:
                from dataclasses import replace
                current.authorization = replace(current.authorization, generation=current.generation)
            return self.status(sid,principal)

    def selected_context(self, sid, principal):
        """Server composition only; a client key cannot construct this projection."""
        current = self._context(sid, principal)
        if current.selected is None or current.selected not in current.keys:
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        return current.adapter, self.status(sid, principal)

    async def templates(self, sid, principal):
        from backend.app.application.report_template_compatibility_service import ReportTemplateCompatibilityService
        from backend.app.report.registry import ReportTemplateCatalogResponse
        current = self._context(sid, principal)
        async with self._metadata_operation(current):
            self._validate(sid, principal)
            if current.selected is None:
                return ReportTemplateCatalogResponse(items=[], reason_code="no_eligible_report_template")
            settings = self._auth.settings
            if current.adapter.is_mock:
                from backend.app.config.settings import PowerBIMode, LLMMode
                settings = settings.model_copy(update={'powerbi_mode':PowerBIMode.MOCK,'llm_mode':LLMMode.MOCK})
            result = await ReportTemplateCompatibilityService(current.adapter, settings).discover(current.selected)
            self._validate(sid, principal)
            return result

    async def prune(self):
        for sid, current in list(self._contexts.items()):
            try: self._validate(sid, current.principal)
            except AuthFailure:
                self._contexts.pop(sid, None)
                current.keys.clear()
                self._clear_selection(current)
                await current.adapter.aclose()

    async def aclose(self):
        self._closed = True
        await self.prune()
