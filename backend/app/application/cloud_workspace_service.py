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
from backend.app.harness.errors import ToolExecutionError
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext, ToolGateway
from backend.app.harness.tool_registry import SchemaInput, TOOL_NAME_SCHEMA, register_schema_tool
from backend.app.intent.models import IntentType
from backend.app.memory.models import RuntimeDataMode
from backend.app.powerbi.cloud_catalog_transport import FabricCatalogTransport
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


@dataclass
class _SessionWorkspace:
    principal: object
    adapter: object
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    keys: set = field(default_factory=set)
    selected: str | None = None
    conversation_id: str | None = None
    generation: int = 0


class CloudWorkspaceService:
    def __init__(self, auth, adapter_factory, *, shared_seeds=(),
                 rest_factory=FabricCatalogTransport, synthetic_product=False):
        self._auth, self._factory = auth, adapter_factory
        self._seeds, self._rest_factory = tuple(shared_seeds), rest_factory
        self._contexts = {}
        self._closed = False
        # Explicit offline host composition; never inferred from adapter flags.
        self._synthetic_product = synthetic_product is True
        self._product_policy = CloudTestPolicy(auth.settings)

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

    async def select(self, sid, principal, key, *, expected_generation=None):
        current = self._context(sid, principal)
        async with self._metadata_operation(current):
            self._validate(sid, principal)
            if key not in current.keys: raise AuthFailure("AUTH_FORBIDDEN", 403)
            if expected_generation is not None and expected_generation != current.generation:
                raise CloudSelectionConflict()
            gateway = ToolGateway()
            register_schema_tool(gateway, current.adapter, HarnessConfig.from_settings(self._auth.settings))
            context = ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,
                intent=IntentType.DATA_QUESTION, user=UserContext(
                    allowed_tools=[TOOL_NAME_SCHEMA], allowed_semantic_models=[key]))
            try:
                schema = await gateway.execute(TOOL_NAME_SCHEMA, context, SchemaInput(semantic_model_key=key))
                self._validate(sid, principal)
                if schema.key != key: raise fail("CONTRACT_DRIFT")
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
            return self._product_policy.capability(binding.workspace_id, binding.model_id, name)
        if current.selected is None or current.selected not in current.keys:
            return False
        ws, model = current.adapter.bound_resource_identity(current.selected)
        return self._product_policy.capability(ws, model, name)

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

    def data_mode(self,sid,principal):
        return RuntimeDataMode.MOCK if self._context(sid,principal).adapter.is_mock else RuntimeDataMode.REAL

    async def bound_projection(self, sid, principal):
        from backend.app.persistence.cloud_bindings import CloudConversationBinding
        from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
        current = self._context(sid, principal)
        async with self._metadata_operation(current):
            self._validate(sid, principal)
            if current.selected not in current.keys: raise AuthFailure('AUTH_FORBIDDEN',403)
            gateway = ToolGateway()
            register_schema_tool(gateway,current.adapter,HarnessConfig.from_settings(self._auth.settings))
            schema = await gateway.execute(TOOL_NAME_SCHEMA,ToolExecutionContext(runtime_mode=RuntimeDataMode.REAL,
                intent=IntentType.DATA_QUESTION,user=UserContext(allowed_tools=[TOOL_NAME_SCHEMA],
                    allowed_semantic_models=[current.selected])),SchemaInput(semantic_model_key=current.selected))
            self._validate(sid,principal)
            if schema.key!=current.selected: raise fail('CONTRACT_DRIFT')
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
            return self.status(sid,principal)

    async def new_chat(self,sid,principal,expected_generation):
        current=self._context(sid,principal)
        async with self._metadata_operation(current):
            self._validate(sid,principal)
            if expected_generation!=current.generation: raise CloudSelectionConflict()
            if current.selected not in current.keys: raise AuthFailure('AUTH_FORBIDDEN',403)
            current.generation+=1
            current.conversation_id=str(uuid4())
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
