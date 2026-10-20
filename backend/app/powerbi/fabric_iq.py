"""Request-scoped read-only cloud provider; no Catalog or product enablement."""
from dataclasses import dataclass
from contextlib import asynccontextmanager
from secrets import token_urlsafe
from types import MappingProxyType
from urllib.parse import urlsplit

from backend.app.auth.models import AuthFailure
from backend.app.config.settings import IdentityMode, PowerBIMode
from backend.app.config.cloud_test_policy import CloudTestPolicy
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.fabric_iq_contract import fail
from backend.app.powerbi.fabric_iq_normalization import (
    IQInlineEnvelope, error_code, guid, normalize_query, normalize_schema, unpack,
    normalize_value_search,
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
        return self._create(session_id, principal, product_queries=False)

    def create_product(self, session_id, principal):
        """Product execution requires proven completeness before Core consumes rows."""
        return self._create(session_id, principal, product_queries=True)

    def _create(self, session_id, principal, *, product_queries):
        if self._auth.require_session(session_id).principal != principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)
        return FabricIQPowerBIAdapter(self._auth, session_id, principal, self._bootstrap,
            self._transport_factory(self._settings, self._auth, session_id, principal),
            product_queries=product_queries)


class FabricIQPowerBIAdapter(PowerBIAdapter):
    def __init__(self, auth, session_id, principal, bootstrap, transport, *, product_queries=False):
        self._auth, self._sid, self._principal = auth, session_id, principal
        self._bootstrap, self._transport = bootstrap, transport
        self._bindings, self._schemas = {}, {}
        self._closed = False
        self._product_queries = product_queries
        self._test_policy = CloudTestPolicy(auth.settings)

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

    def assert_session_binding(self, auth, session_id, principal):
        self._validate()
        if self._auth is not auth or self._sid != session_id or self._principal != principal:
            raise AuthFailure("AUTH_FORBIDDEN", 403)

    @asynccontextmanager
    async def _connection(self, *, key=None, resource=None):
        from backend.app.powerbi.base import PowerBIAdapterError
        if key is not None:
            ref = self._binding(key)
            resource = (ref.workspace_id, ref.semantic_model_id)
        try:
            async with self._transport.connection(resource=resource) as connection:
                yield connection
        except (AuthFailure, PowerBIAdapterError) as error:
            code = error.code if isinstance(error, AuthFailure) else error.error_type
            if code in {"AUTH_REQUIRED", "AUTH_EXPIRED"}:
                self._bindings.clear()
                self._schemas.clear()
                self._auth.logout(self._sid, None)
            elif code in {'AUTH_FORBIDDEN','RESOURCE_NOT_ACCESSIBLE','SCHEMA_UNAVAILABLE','MODEL_RESOLUTION_FAILED'}:
                affected = [key] if key is not None else [k for k, ref in self._bindings.items()
                    if resource == (ref.workspace_id, ref.semantic_model_id)]
                for affected_key in affected:
                    self._bindings.pop(affected_key, None)
                    self._schemas.pop(affected_key, None)
            raise

    def _binding(self, key):
        self._validate()
        ref = self._bindings.get(key)
        p = self._principal
        if not ref or (ref.tenant_id, ref.principal_id, ref.session_epoch, ref.authorization_epoch) != (
                p.tenant_id, p.principal_id, p.session_epoch, p.authorization_epoch):
            raise fail("RESOURCE_NOT_ACCESSIBLE")
        try:
            self._test_policy.model(ref.workspace_id, ref.semantic_model_id)
        except Exception:
            self._bindings.pop(key, None)
            self._schemas.pop(key, None)
            raise
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
        return await self._resolve_authorized_url(url)

    async def bind_catalog_model(self, workspace_id, model_id):
        """Server-owned REST candidate; Resolve+Schema must still prove access."""
        self._validate()
        workspace_id, model_id = guid(workspace_id), guid(model_id)
        url = f"https://app.powerbi.com/groups/{workspace_id}/datasets/{model_id}/details"
        return await self._resolve_authorized_url(url, reuse=True)

    def bound_resource_identity(self, key):
        ref = self._binding(key)
        return ref.workspace_id, ref.semantic_model_id

    async def restore_bound_model(self, workspace_id, model_id, key):
        """Server-owned persisted projection only; still Resolve+Schema proof."""
        self._validate()
        workspace_id, model_id = guid(workspace_id), guid(model_id)
        if not isinstance(key,str) or not key.startswith('fabric_iq:') or len(key)>128:
            raise fail('RESOURCE_NOT_ACCESSIBLE')
        old = self._bindings.get(key)
        if old and (old.workspace_id,old.semantic_model_id)!=(workspace_id,model_id):
            raise fail('RESOURCE_NOT_ACCESSIBLE')
        return await self._resolve_authorized_url(
            f'https://app.powerbi.com/groups/{workspace_id}/datasets/{model_id}/details', restored_key=key)

    async def restore_bound_schema(self, workspace_id, model_id, key):
        """Return the typed schema proven by this exact fresh Resolve+Schema.

        This is a single metadata operation, never a cross-request access cache.
        Ordinary get_semantic_model_schema and query execution stay unchanged.
        """
        ref = await self.restore_bound_model(workspace_id, model_id, key)
        bound = self._binding(key)
        schema = self._schemas.get(key)
        if (bound is not ref or schema is None or schema.key != key
                or schema.metadata_source != 'fabric_iq'
                or schema.session_generation != ref.authorization_epoch):
            raise fail('CONTRACT_DRIFT')
        return schema.model_copy(deep=True)

    async def _resolve_authorized_url(self, url, *, reuse=False, restored_key=None):
        self._validate()
        expected_workspace, expected_model = _bootstrap_identity(url)
        self._test_policy.model(expected_workspace, expected_model)
        async with self._connection(resource=(expected_workspace, expected_model)) as connection:
            resolved, resource = unpack(await connection.call("ResolveFabricItem", {"fabricItemId": url}), "MODEL_RESOLUTION_FAILED")
            if (resource is not None or resolved.get("itemType") != "SemanticModel"
                    or guid(resolved.get("fabricItemId")) != expected_model
                    or guid(resolved.get("workspaceId")) != expected_workspace):
                raise fail("MODEL_RESOLUTION_FAILED")
            self._validate()
            self._test_policy.model(expected_workspace, expected_model)
            raw = await connection.call("GetSemanticModelSchema", {"artifactId": expected_model})
            old = next((ref for ref in self._bindings.values()
                if ref.workspace_id == expected_workspace and ref.semantic_model_id == expected_model), None) if reuse else None
            key = restored_key or (old.server_model_key if old else "fabric_iq:" + token_urlsafe(32))
            schema = normalize_schema(raw, expected_model, key, self._principal.authorization_epoch)
        self._validate()
        self._test_policy.model(expected_workspace, expected_model)
        p = self._principal
        ref = CloudSemanticModelRef(key, p.tenant_id, p.principal_id, expected_workspace, expected_model,
            schema.name, p.session_epoch, p.authorization_epoch)
        self._bindings[key], self._schemas[key] = ref, schema
        return ref

    async def get_semantic_model_schema(self, semantic_model_key):
        ref = self._binding(semantic_model_key)
        async with self._connection(key=semantic_model_key) as connection:
            raw = await connection.call("GetSemanticModelSchema", {"artifactId": ref.semantic_model_id})
            schema = normalize_schema(raw, ref.semantic_model_id, semantic_model_key, ref.authorization_epoch)
        self._validate()
        self._binding(semantic_model_key)
        self._schemas[semantic_model_key] = schema
        return schema.model_copy(deep=True)

    async def execute_dax(self, request):
        return await self._execute_query(request)

    async def _execute_query(self, request, *, projected_columns=None):
        # projected_columns is supplied only by the two server-owned fixed
        # diagnostic/member projections below, never by a public DAX request.
        if not isinstance(request, DAXRequest) or request.is_mock: raise fail("QUERY_REJECTED")
        ref = self._binding(request.semantic_model_key)
        schema = self._schemas.get(request.semantic_model_key)
        if schema is None or schema.key != ref.server_model_key or schema.session_generation != ref.authorization_epoch:
            raise fail("CONTRACT_DRIFT")
        envelope = IQInlineEnvelope.for_request(request)
        import asyncio
        try:
            async with asyncio.timeout(request.timeout_seconds):
                async with self._connection(key=request.semantic_model_key) as connection:
                    raw = await connection.call("ExecuteQuery", {"artifactId": ref.semantic_model_id,
                        "daxQueries": [request.dax], "maxRows": envelope.wire_limit})
                    result = normalize_query(raw, ref.semantic_model_id, request, envelope=envelope,
                        schema=schema if projected_columns is None else None)
                    if projected_columns is not None and tuple(result.columns) not in projected_columns:
                        raise fail("CONTRACT_DRIFT")
        except TimeoutError:
            raise fail("QUERY_TIMEOUT") from None
        self._validate()
        self._binding(request.semantic_model_key)
        if self._schemas.get(request.semantic_model_key) is not schema:
            raise fail("CONTRACT_DRIFT")
        return self._product_result(result)

    def _product_result(self, result):
        # Generic Core can present partial rows with disclosure; the adaptive
        # Sales report does not retain that marker. Cloud product calls must
        # therefore fail before any facts, Memory or report artifact are built.
        if self._product_queries and result.truncated:
            raise fail("CONTRACT_DRIFT")
        return result

    async def normalize_result(self, raw):
        # Explicit request/ref context avoids mutable global 'last query' state.
        if not isinstance(raw, tuple) or len(raw) != 2 or not isinstance(raw[1], DAXRequest):
            raise fail("CONTRACT_DRIFT")
        response, request = raw
        ref = self._binding(request.semantic_model_key)
        return self._product_result(normalize_query(response, ref.semantic_model_id, request,
            schema=self._schemas[request.semantic_model_key]))

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
        from backend.app.application.cloud_literal_context import requested_literals
        from backend.app.powerbi.member_identity import declaration, canonical_literal
        contract = declaration(matches[0])
        if contract and contract['role'] == 'provenance_only':
            raise fail('RESOURCE_NOT_ACCESSIBLE')
        literals = requested_literals(request.table_name, request.field_name,
            input_name=contract['input_name'] if contract else None)
        if literals and contract:
            literals = tuple(dict.fromkeys(canonical_literal(value) for value in literals))
        # Targeted existence proof is allowed for explicit categorical literals
        # only. Date/month/structural requests retain full-snapshot completeness.
        if literals and matches[0].data_type.lower() in {'text', 'string'}:
            return await self._explicit_members(request, schema, literals)
        table = request.table_name.replace("'", "''")
        column = request.field_name.replace("]", "]]")
        reference = f"'{table}'[{column}]"
        # Deduplicate the grounded column before projecting its fixed alias.
        # The alias is owned by this exact projection, not a business label.
        dax = (f'EVALUATE TOPN({request.limit + 1}, SELECTCOLUMNS(DISTINCT({reference}), '
               f'"__member", {reference}), [__member], ASC) ORDER BY [__member] ASC')
        result = await self._execute_query(DAXRequest(semantic_model_key=request.semantic_model_key,
            dax=dax, max_rows=request.limit + 1), projected_columns=(("__member",), ("[__member]",)))
        if result.columns not in (["__member"], ["[__member]"]):
            raise fail("CONTRACT_DRIFT")
        return ColumnMembersResult(semantic_model_key=request.semantic_model_key,
            table_name=request.table_name, field_name=request.field_name,
            values=[r[0] for r in result.rows[:request.limit]],
            truncated=result.truncated or len(result.rows) > request.limit, source_mode="real")

    async def _explicit_members(self, request, schema, literals):
        from backend.app.powerbi.fabric_iq_contract import validate_value_search_capability
        ref = self._binding(request.semantic_model_key)
        values = []
        async with self._connection(key=request.semantic_model_key) as connection:
            validate_value_search_capability(connection._inventory.get('ValueSearch'))
            for literal in literals:
                raw = await connection.call('ValueSearch', {'artifactId': ref.semantic_model_id,
                    'searchTerms': [literal], 'scope': [{'tableName':request.table_name,
                                                       'columnNames':[request.field_name]}]})
                proof = normalize_value_search(raw, ref.semantic_model_id, schema,
                    request.table_name, request.field_name, literal)
                # Do not lend another literal's candidate to Grounding's
                # normalized/alias matching. Every current literal must have
                # its own exact proof before this shared field set is exposed.
                if not proof.values:
                    values = []
                    break
                values.extend(proof.values)
                if len(values) > 12:
                    raise fail('CONTRACT_DRIFT')
        self._validate()
        self._binding(request.semantic_model_key)
        if self._schemas.get(request.semantic_model_key) is not schema:
            raise fail('CONTRACT_DRIFT')
        return ColumnMembersResult(semantic_model_key=request.semantic_model_key,
            table_name=request.table_name,field_name=request.field_name,
            values=values,truncated=True,source_mode='real')

    async def probe_compatibility(self, semantic_model_key):
        await self.health_check()
        await self.get_semantic_model_schema(semantic_model_key)
        result = await self._execute_query(DAXRequest(semantic_model_key=semantic_model_key,
            dax='EVALUATE ROW("__pbiagent_probe", 1)', max_rows=2),
            projected_columns=(("__pbiagent_probe",), ("[__pbiagent_probe]",)))
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
