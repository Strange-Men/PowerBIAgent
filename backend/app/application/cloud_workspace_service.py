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
    execution_ready: Literal[False] = False
    blockers: tuple[Literal["numeric_contract", "query_completeness"], ...] = (
        "numeric_contract", "query_completeness")
    model_config = ConfigDict(extra="forbid", frozen=True)


class CloudSelectionConflict(ValueError):
    def __init__(self): super().__init__("cloud_selection_changed")


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
                 rest_factory=FabricCatalogTransport):
        self._auth, self._factory = auth, adapter_factory
        self._seeds, self._rest_factory = tuple(shared_seeds), rest_factory
        self._contexts = {}
        self._closed = False

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
                self._clear_selection(current)
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
        return CloudWorkspaceStatus(selected_model_key=current.selected,
            conversation_id=current.conversation_id, generation=current.generation)

    def require_execution(self, sid, principal):
        self._validate(sid, principal)
        # No deploy flag, client readiness claim or test hook can open this gate.
        raise AuthFailure("AUTH_FORBIDDEN", 403)

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
            result = await ReportTemplateCompatibilityService(current.adapter, self._auth.settings).discover(current.selected)
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
