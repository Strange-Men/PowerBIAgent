"""Request-scoped read-only cloud provider; no Catalog or product enablement."""
from dataclasses import dataclass
from contextlib import asynccontextmanager
from secrets import token_urlsafe
from types import MappingProxyType
from urllib.parse import urlsplit

from backend.app.auth.models import AuthFailure
from backend.app.config.settings import IdentityMode, PowerBIMode
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.powerbi.fabric_iq_normalization import (
    error_code, guid, normalize_query, normalize_schema, unpack,
)
from backend.app.powerbi.fabric_iq_transport import FabricIQTransport
from backend.app.powerbi.models import PowerBICompatibilityProbe
from backend.app.schemas.data_contracts import (
    ColumnMembersResult, DAXRequest, PowerBIError,
)


@dataclass(frozen=True, repr=False)
class CloudSemanticModelRef:
    server_model_key: str
    tenant_id: str
    principal_id: str
    workspace_id: str
    semantic_model_id: str
    display_name: str
    session_epoch: int
    authorization_epoch: int
    resolution_evidence: str = "ResolveFabricItem+GetSemanticModelSchema"
    provider: str = "fabric_iq"


def _bootstrap_identity(url):
    """Server config only; supported browser URLs, never arbitrary links."""
    import re
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc not in {"app.powerbi.com", "app.fabric.microsoft.com"}
            or parsed.query or parsed.fragment or parsed.username):
        raise fail("MODEL_RESOLUTION_FAILED")
    matched = re.fullmatch(r"/groups/([0-9a-fA-F-]{36})/(?:datasets|semanticmodels)/([0-9a-fA-F-]{36})(?:/details)?", parsed.path)
    if not matched: raise fail("MODEL_RESOLUTION_FAILED")
    return guid(matched[1]), guid(matched[2])


class FabricIQAdapterFactory:
    def __init__(self, settings, auth, *, bootstrap_urls=None, transport_factory=FabricIQTransport):
        if settings.identity_mode != IdentityMode.ENTRA_BFF or settings.powerbi_mode != PowerBIMode.FABRIC_IQ:
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        self._settings, self._auth = settings, auth
        self._bootstrap = MappingProxyType(dict(bootstrap_urls or {}))
        self._transport_factory = transport_factory
        for url in self._bootstrap.values(): _bootstrap_identity(url)

    def create(self, session_id, principal):
        if self._auth.require_session(session_id).principal != principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        return FabricIQPowerBIAdapter(self._auth, session_id, principal, self._bootstrap,
            self._transport_factory(self._settings, self._auth, session_id, principal))


class FabricIQPowerBIAdapter(PowerBIAdapter):
    def __init__(self, auth, session_id, principal, bootstrap, transport):
        self._auth, self._sid, self._principal = auth, session_id, principal
        self._bootstrap, self._transport = bootstrap, transport
        self._bindings, self._schemas = {}, {}
        self._closed = False

    @property
    def provider_name(self): return "fabric_iq"

    @property
    def is_mock(self): return False

    @property
    def binding_count(self): return len(self._bindings)

    @property
    def capability_evidence(self): return getattr(self._transport, "capability_evidence", None)

    @property
    def wire_evidence(self): return dict(getattr(self._transport, "wire_evidence", {}))

    def _validate(self):
        if self._closed: raise fail("UPSTREAM_UNAVAILABLE")
        try:
            if self._auth.require_session(self._sid).principal != self._principal:
                raise AuthFailure("AUTH_FORBIDDEN", 403)
        except AuthFailure:
            self._bindings.clear()
            self._schemas.clear()
            raise

    @asynccontextmanager
    async def _connection(self):
        from backend.app.powerbi.base import PowerBIAdapterError
        try:
            async with self._transport.connection() as connection:
                yield connection
        except (AuthFailure, PowerBIAdapterError) as error:
            code = error.code if isinstance(error, AuthFailure) else error.error_type
            if code in {"AUTH_REQUIRED", "AUTH_EXPIRED", "AUTH_FORBIDDEN", "RESOURCE_NOT_ACCESSIBLE"}:
                self._bindings.clear()
                self._schemas.clear()
                # Conservative revocation policy: fresh Microsoft login and
                # schema-before-bind required for every old model reference.
                self._auth.logout(self._sid, None)
            raise

    def _binding(self, key):
        self._validate()
        ref = self._bindings.get(key)
        p = self._principal
        if not ref or (ref.tenant_id, ref.principal_id, ref.session_epoch, ref.authorization_epoch) != (
                p.tenant_id, p.principal_id, p.session_epoch, p.authorization_epoch):
            raise fail("RESOURCE_NOT_ACCESSIBLE")
        return ref

    async def health_check(self):
        self._validate()
        async with self._connection(): pass
        self._validate()
        return True

    async def resolve_bootstrap(self, bootstrap_name):
        self._validate()
        url = self._bootstrap.get(bootstrap_name)
        if url is None: raise fail("MODEL_RESOLUTION_FAILED")
        expected_workspace, expected_model = _bootstrap_identity(url)
        async with self._connection() as connection:
            resolved, resource = unpack(await connection.call("ResolveFabricItem", {"fabricItemId": url}), "MODEL_RESOLUTION_FAILED")
            if (resource is not None or resolved.get("itemType") != "SemanticModel"
                    or guid(resolved.get("fabricItemId")) != expected_model
                    or guid(resolved.get("workspaceId")) != expected_workspace):
                raise fail("MODEL_RESOLUTION_FAILED")
            raw = await connection.call("GetSemanticModelSchema", {"artifactId": expected_model})
            key = "fabric_iq:" + token_urlsafe(32)
            schema = normalize_schema(raw, expected_model, key, self._principal.authorization_epoch)
        self._validate()
        p = self._principal
        ref = CloudSemanticModelRef(key, p.tenant_id, p.principal_id, expected_workspace, expected_model,
            schema.name, p.session_epoch, p.authorization_epoch)
        self._bindings[key], self._schemas[key] = ref, schema
        return ref

    async def get_semantic_model_schema(self, semantic_model_key):
        ref = self._binding(semantic_model_key)
        async with self._connection() as connection:
            raw = await connection.call("GetSemanticModelSchema", {"artifactId": ref.semantic_model_id})
            schema = normalize_schema(raw, ref.semantic_model_id, semantic_model_key, ref.authorization_epoch)
        self._validate()
        self._schemas[semantic_model_key] = schema
        return schema.model_copy(deep=True)

    async def execute_dax(self, request):
        if not isinstance(request, DAXRequest) or request.is_mock: raise fail("QUERY_REJECTED")
        ref = self._binding(request.semantic_model_key)
        import asyncio
        try:
            async with asyncio.timeout(request.timeout_seconds):
                async with self._connection() as connection:
                    raw = await connection.call("ExecuteQuery", {"artifactId": ref.semantic_model_id,
                        "daxQueries": [request.dax], "maxRows": request.max_rows})
                    result = normalize_query(raw, ref.semantic_model_id, request)
        except TimeoutError:
            raise fail("QUERY_TIMEOUT") from None
        self._validate()
        return result

    async def normalize_result(self, raw):
        # Explicit request/ref context avoids mutable global 'last query' state.
        if not isinstance(raw, tuple) or len(raw) != 2 or not isinstance(raw[1], DAXRequest):
            raise fail("CONTRACT_DRIFT")
        response, request = raw
        ref = self._binding(request.semantic_model_key)
        return normalize_query(response, ref.semantic_model_id, request)

    async def normalize_error(self, raw):
        from backend.app.powerbi.base import PowerBIAdapterError
        code = raw.error_type if isinstance(raw, PowerBIAdapterError) else error_code(raw)
        from backend.app.schemas.failure_contracts import PublicFailureCode
        if code not in {v.value for v in PublicFailureCode}: code = "UPSTREAM_UNAVAILABLE"
        known = fail(code)
        return PowerBIError(type=known.error_type, message=str(known), retryable=known.retryable)

    async def get_column_members(self, request):
        self._binding(request.semantic_model_key)
        schema = self._schemas[request.semantic_model_key]
        matches = [c for t in schema.tables if t.name == request.table_name
                   for c in t.columns if c.name == request.field_name]
        if len(matches) != 1: raise fail("SCHEMA_UNAVAILABLE")
        table = request.table_name.replace("'", "''")
        column = request.field_name.replace("]", "]]")
        reference = f"'{table}'[{column}]"
        # Deduplicate the grounded column before projecting its fixed alias.
        # Never reverse-map Fabric's friendly labels (which may be ambiguous).
        dax = (f'EVALUATE TOPN({request.limit + 1}, SELECTCOLUMNS(DISTINCT({reference}), '
               f'"__member", {reference}), [__member], ASC) ORDER BY [__member] ASC')
        result = await self.execute_dax(DAXRequest(semantic_model_key=request.semantic_model_key,
            dax=dax, max_rows=request.limit + 1))
        if result.columns not in (["__member"], ["[__member]"]):
            raise fail("CONTRACT_DRIFT")
        return ColumnMembersResult(semantic_model_key=request.semantic_model_key,
            table_name=request.table_name, field_name=request.field_name,
            values=[r[0] for r in result.rows[:request.limit]],
            truncated=result.truncated or len(result.rows) > request.limit, source_mode="real")

    async def probe_compatibility(self, semantic_model_key):
        await self.health_check()
        await self.get_semantic_model_schema(semantic_model_key)
        result = await self.execute_dax(DAXRequest(semantic_model_key=semantic_model_key,
            dax='EVALUATE ROW("__pbiagent_probe", 1)', max_rows=2))
        verified = result.columns in (["__pbiagent_probe"], ["[__pbiagent_probe]"]) and result.rows == [[1]]
        if not verified: raise fail("CONTRACT_DRIFT")
        return PowerBICompatibilityProbe(semantic_model_key=semantic_model_key,
            server_started=True, protocol_negotiated=True, required_tools_available=True,
            instance_matched=True, connected=True, schema_read=True, dax_execute=True,
            row_data_verified=True, compatible=True)

    async def aclose(self):
        self._closed = True
        self._bindings.clear()
        self._schemas.clear()
        await self._transport.aclose()
