"""M6.2 synthetic contracts: no login, network, identifiers or business data."""
import copy
from contextlib import asynccontextmanager
from uuid import UUID

import pytest

from backend.app.auth.models import AuthFailure, PrincipalContext
from backend.app.auth.service import AuthService
from backend.app.config.settings import Settings
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.powerbi.fabric_iq import FabricIQAdapterFactory
from backend.app.powerbi.fabric_iq_contract import capability_fingerprint
from backend.app.schemas.data_contracts import ColumnMembersRequest, DAXRequest

TENANT, CLIENT, MODEL, WORKSPACE = (str(UUID(int=i)) for i in (1, 2, 10, 11))
URL = f"https://app.powerbi.com/groups/{WORKSPACE}/datasets/{MODEL}/details"


def settings(**changes):
    return Settings(_env_file=None, identity_mode="ENTRA_BFF", entra_tenant_id=TENANT,
                    entra_client_id=CLIENT, entra_client_secret="NOT_A_REAL_SECRET_AUTH",
                    auth_cookie_secure=False, **changes)


class Identity:
    token_error = None
    def destroy(self, context): pass
    def delegated_token(self, context, principal, scopes):
        if self.token_error:
            raise self.token_error
        return "SYNTHETIC_DELEGATED_TOKEN"


def principal(n=3):
    return PrincipalContext(tenant_id=TENANT, principal_id=str(UUID(int=n)), subject=f"sub-{n}",
        issuer=f"https://login.microsoftonline.com/{TENANT}/v2.0", display_name="Synthetic",
        preferred_username=None, session_epoch=n, authorization_epoch=n)


def tools():
    def t(name, props, required):
        return {"name": name, "inputSchema": {"type": "object", "properties": props, "required": required}}
    string = {"type": "string"}
    array = {"type": "array", "items": string}
    return [t("ResolveFabricItem", {"fabricItemId": string}, ["fabricItemId"]),
        t("GetSemanticModelSchema", {"artifactId": string, "queries": array}, ["artifactId"]),
        t("ExecuteQuery", {"artifactId": string, "daxQueries": array,
            "maxRows": {"type": ["integer", "null"]}}, ["artifactId", "daxQueries"])]


def schema():
    return {"semanticModel": {"ArtifactId": MODEL, "Name": "Synthetic model"},
        "schema": {"Tables": [{"Name": "Facts", "Columns": [{"Name": "Category", "Type": "String"}],
            "Measures": [{"Name": "Count", "Type": "Int64"}]}],
            "ActiveRelationships": [{"PK": "Dim[Key]", "FK": "Facts[Key]", "UnidirectionalFilter": "Dim -> Facts"}]}}


def result(rows=None, **changes):
    root = {"semanticModel": {"ArtifactId": MODEL}, "executionResult": {"tables": [
        {"columns": [{"name": "[probe]", "type": "Int64"}], "rows": rows if rows is not None else [[1]]}]}}
    root.update(changes)
    return root


class Transport:
    def __init__(self):
        self.inventory = tools()
        self.schema = schema()
        self.query = result()
        self.calls = []
        self.closes = 0
    @asynccontextmanager
    async def connection(self):
        capability_fingerprint(self.inventory)
        try:
            yield self
        finally:
            self.closes += 1
    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "ResolveFabricItem":
            return {"fabricItemId": MODEL, "workspaceId": WORKSPACE, "itemType": "SemanticModel"}
        return copy.deepcopy(self.schema if name == "GetSemanticModelSchema" else self.query)
    async def aclose(self): self.closes += 1


@pytest.fixture
def harness():
    auth = AuthService(settings(powerbi_mode="fabric_iq"), Identity())
    session = auth.sessions.create(principal(), object(), 3600)
    transport = Transport()
    factory = FabricIQAdapterFactory(auth.settings, auth, bootstrap_urls={"fixture": URL},
                                    transport_factory=lambda *args: transport)
    return auth, session, transport, factory.create(session.session_id, session.principal)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403, 404])
async def test_m63_permission_failure_invalidates_cached_binding(harness, code):
    auth, session, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = {"Error": {"HttpStatusCode": code}}
    with pytest.raises((PowerBIAdapterError, AuthFailure)):
        await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
            dax='EVALUATE ROW("probe",1)'))
    assert adapter.binding_count == 0
    assert adapter._schemas == {}
    with pytest.raises(AuthFailure):
        auth.require_session(session.session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["schema", "query", "members"])
@pytest.mark.parametrize("copied", [False, True])
async def test_m63_foreign_model_key_denied_before_mcp(harness, operation, copied):
    auth, _, transport, a = harness
    ref = await a.resolve_bootstrap("fixture")
    session_b = auth.sessions.create(principal(4), object(), 3600)
    b = FabricIQAdapterFactory(auth.settings, auth, transport_factory=lambda *args: transport).create(
        session_b.session_id, session_b.principal)
    if copied:
        b._bindings[ref.server_model_key] = ref
        b._schemas[ref.server_model_key] = a._schemas[ref.server_model_key]
    before = len(transport.calls)
    with pytest.raises(PowerBIAdapterError, match="^RESOURCE_NOT_ACCESSIBLE$"):
        if operation == "schema": await b.get_semantic_model_schema(ref.server_model_key)
        elif operation == "query": await b.execute_dax(DAXRequest(
            semantic_model_key=ref.server_model_key, dax='EVALUATE ROW("probe",1)'))
        else: await b.get_column_members(ColumnMembersRequest(
            semantic_model_key=ref.server_model_key, table_name="Facts", field_name="Category", limit=2))
    assert len(transport.calls) == before
    assert auth.require_session(session_b.session_id).principal == session_b.principal


@pytest.mark.asyncio
async def test_m63_same_model_different_authorized_schema_result_and_members(harness):
    auth, _, transport_a, a = harness
    transport_a.schema["schema"]["Tables"][0]["Columns"].append({"Name": "RestrictedColumn", "Type": "String"})
    ref_a = await a.resolve_bootstrap("fixture")
    session_b = auth.sessions.create(principal(4), object(), 3600)
    transport_b = Transport()
    b = FabricIQAdapterFactory(auth.settings, auth, bootstrap_urls={"fixture": URL},
        transport_factory=lambda *args: transport_b).create(session_b.session_id, session_b.principal)
    ref_b = await b.resolve_bootstrap("fixture")
    assert "RestrictedColumn" in [c.name for c in a._schemas[ref_a.server_model_key].tables[0].columns]
    assert "RestrictedColumn" not in [c.name for c in b._schemas[ref_b.server_model_key].tables[0].columns]
    transport_a.query = result([[1]])
    transport_b.query = result([[2]])
    dax = 'EVALUATE ROW("probe",1)'
    assert (await a.execute_dax(DAXRequest(semantic_model_key=ref_a.server_model_key, dax=dax))).rows == [[1]]
    assert (await b.execute_dax(DAXRequest(semantic_model_key=ref_b.server_model_key, dax=dax))).rows == [[2]]
    for adapter, ref, transport, value in ((a, ref_a, transport_a, "A"), (b, ref_b, transport_b, "B")):
        transport.query = result([[value]])
        transport.query["executionResult"]["tables"][0]["columns"] = [{"name": "[__member]", "type": "String"}]
        members = await adapter.get_column_members(ColumnMembersRequest(
            semantic_model_key=ref.server_model_key, table_name="Facts", field_name="Category", limit=2))
        assert members.values == [value]
    with pytest.raises(PowerBIAdapterError):
        await b.get_column_members(ColumnMembersRequest(semantic_model_key=ref_b.server_model_key,
            table_name="Facts", field_name="RestrictedColumn", limit=2))
    # B's negative member lookup must not poison A's independently allowed schema.
    assert a._schemas[ref_a.server_model_key].tables[0].columns[-1].name == "RestrictedColumn"


@pytest.mark.asyncio
async def test_m63_stale_epoch_ref_rejected_before_mcp(harness):
    from dataclasses import replace
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    adapter._bindings[ref.server_model_key] = replace(ref, authorization_epoch=ref.authorization_epoch - 1)
    before = len(transport.calls)
    with pytest.raises(PowerBIAdapterError):
        await adapter.get_semantic_model_schema(ref.server_model_key)
    assert len(transport.calls) == before


@pytest.mark.asyncio
async def test_schema_before_bind_unknown_metadata_and_lifecycle(harness):
    auth, session, transport, adapter = harness
    assert adapter.provider_name == "fabric_iq" and not adapter.is_mock
    assert await adapter.health_check()
    ref = await adapter.resolve_bootstrap("fixture")
    assert [c[0] for c in transport.calls] == ["ResolveFabricItem", "GetSemanticModelSchema"]
    assert MODEL not in ref.server_model_key and WORKSPACE not in ref.server_model_key
    assert ref.principal_id == session.principal.principal_id
    normalized = await adapter.get_semantic_model_schema(ref.server_model_key)
    assert normalized.metadata_source == "fabric_iq"
    assert normalized.tables[0].is_hidden is None
    assert normalized.tables[0].columns[0].is_hidden is None
    assert normalized.tables[0].measures[0].expression is None
    assert normalized.relationships == []
    assert normalized.provider_metadata["active_relationships"][0]["PK"] == "Dim[Key]"
    await adapter.aclose()
    assert adapter.binding_count == 0
    with pytest.raises(PowerBIAdapterError):
        await adapter.get_semantic_model_schema(ref.server_model_key)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["mismatch", "malformed", "denied", "missing-tool"])
async def test_resolution_never_binds_unproven_resource(harness, case):
    _, _, transport, adapter = harness
    if case == "mismatch": transport.schema["semanticModel"]["ArtifactId"] = str(UUID(int=99))
    if case == "malformed": transport.schema["schema"]["Tables"] = "broken"
    if case == "denied": transport.schema = {"Error": {"HttpStatusCode": 403}}
    if case == "missing-tool": transport.inventory.pop()
    with pytest.raises(PowerBIAdapterError):
        await adapter.resolve_bootstrap("fixture")
    assert adapter.binding_count == 0


@pytest.mark.asyncio
async def test_expired_wrong_session_and_foreign_key_refuse_before_mcp(harness):
    auth, session, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    other = auth.sessions.create(principal(4), object(), 3600)
    second = FabricIQAdapterFactory(auth.settings, auth, transport_factory=lambda *a: transport).create(
        other.session_id, other.principal)
    before = len(transport.calls)
    with pytest.raises(PowerBIAdapterError):
        await second.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key, dax='EVALUATE ROW("probe",1)'))
    with pytest.raises(AuthFailure):
        FabricIQAdapterFactory(auth.settings, auth).create(session.session_id, other.principal)
    session.expires_at = 0
    with pytest.raises(AuthFailure): await adapter.health_check()
    assert len(transport.calls) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [[[1]], [[None]], [[1], [2]]])
async def test_query_preserves_shape_and_defaults_unknown_completeness(harness, rows):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = result(rows)
    actual = await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
        dax='EVALUATE ROW("probe",1)', max_rows=20))
    assert actual.columns == ["[probe]"] and actual.rows == rows
    assert actual.row_count == len(rows) and actual.source_mode == "real" and actual.truncated
    assert transport.calls[-1][1]["maxRows"] == 20


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["wrong-model", "width", "duplicate", "empty-columns", "missing",
    "multi-table", "count", "error", "text-error", "isError", "nested-error", "conflicting"])
async def test_malformed_and_error_queries_fail_closed(harness, case):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    q = result()
    table = q["executionResult"]["tables"][0]
    if case == "wrong-model": q["semanticModel"]["ArtifactId"] = str(UUID(int=99))
    if case == "width": table["rows"] = [[1, 2]]
    if case == "duplicate": table["columns"] *= 2; table["rows"] = [[1, 2]]
    if case == "empty-columns": table["columns"] = []
    if case == "missing": q.pop("executionResult")
    if case == "multi-table": q["executionResult"]["tables"] *= 2
    if case == "count": table["rowCount"] = 2
    if case == "error": q = {"Error": {"HttpStatusCode": 400, "Message": "SENSITIVE"}}
    if case == "text-error": q = {"content": [{"type": "text", "text": "DAX query failure SENSITIVE"}]}
    if case == "isError": q = {"isError": True, "content": []}
    if case == "nested-error": table["error"] = {"message": "SENSITIVE"}
    if case == "conflicting": q.update(truncated=False); q["executionResult"]["truncated"] = True
    transport.query = q
    with pytest.raises(PowerBIAdapterError) as e:
        await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key, dax="EVALUATE bad"))
    assert "SENSITIVE" not in str(e.value)


@pytest.mark.asyncio
async def test_csv_full_resource_not_inline_preview_and_malformed_denied(harness):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    q = result()
    transport.query = {"content": [{"type": "text", "text": __import__('json').dumps(q)},
        {"type": "resource", "resource": {"uri": "data:synthetic", "mimeType": "text/csv",
                                              "text": "[probe]\r\n1\r\n2\r\n"}}]}
    actual = await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key, dax="EVALUATE bad"))
    assert actual.rows == [[1], [2]] and actual.truncated
    transport.query["content"][1]["resource"]["text"] = '[probe]\n"unclosed'
    with pytest.raises(PowerBIAdapterError):
        await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key, dax="EVALUATE bad"))


@pytest.mark.asyncio
async def test_unverified_complete_flag_cannot_grant_completeness(harness):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = result(truncated=False)
    for limit, truncated in [(1, True), (10, True)]:
        actual = await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
            dax='EVALUATE ROW("probe",1)', max_rows=limit))
        assert actual.truncated is truncated


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["__member", "[__member]"])
async def test_bounded_members_only_validated_column(harness, alias):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    before = len(transport.calls)
    with pytest.raises(PowerBIAdapterError):
        await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name="Facts", field_name="Injected"))
    assert len(transport.calls) == before
    transport.query = result([["alpha"], ["beta"]])
    transport.query["executionResult"]["tables"][0]["columns"] = [{"name": alias, "type": "String"}]
    actual = await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
        table_name="Facts", field_name="Category", limit=1))
    assert actual.values == ["alpha"] and actual.truncated
    assert "TOPN(2" in transport.calls[-1][1]["daxQueries"][0]
    assert "DISTINCT('Facts'[Category])" in transport.calls[-1][1]["daxQueries"][0]


@pytest.mark.parametrize("case", ["missing", "type", "required", "array-item", "new-required"])
def test_required_capability_drift(case):
    inventory = tools()
    entry = inventory[-1]["inputSchema"]
    if case == "missing": inventory.pop()
    if case == "type": entry["properties"]["artifactId"] = {"type": "integer"}
    if case == "required": entry["required"].remove("artifactId")
    if case == "array-item": entry["properties"]["daxQueries"]["items"] = {"type": "integer"}
    if case == "new-required": entry["required"].append("newMandatory")
    with pytest.raises(PowerBIAdapterError, match="CONTRACT_DRIFT"):
        capability_fingerprint(inventory)


def test_additive_capabilities_do_not_change_required_fingerprint():
    inventory = tools()
    baseline = capability_fingerprint(inventory)
    inventory.append({"name": "FutureTool", "inputSchema": {}})
    inventory[0]["inputSchema"]["properties"]["future"] = {"type": "string"}
    assert capability_fingerprint(inventory) == baseline


@pytest.mark.parametrize("endpoint", ["http://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq",
    "https://evil.invalid/v1/mcp/fabriciq", "https://fabriciq.svc.cloud.microsoft.evil.invalid/v1/mcp/fabriciq",
    "https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq?token=x",
    "https://fabriciq.svc.cloud.microsoft:443/v1/mcp/fabriciq",
    "https://user@fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq",
    "https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq/",
    "https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq#fragment"])
def test_endpoint_exfiltration_rejected(endpoint):
    with pytest.raises(ValueError): settings(fabric_iq_endpoint=endpoint)


def test_cloud_requires_bff_and_selector_is_fixed():
    with pytest.raises(ValueError): Settings(_env_file=None, powerbi_mode="fabric_iq")
    with pytest.raises(ValueError): settings(fabric_iq_variant="unverified")


@pytest.mark.asyncio
async def test_grouped_rows_preserved_and_no_provider_query_retry(harness):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = result([["alpha", 1], ["beta", None]])
    transport.query["executionResult"]["tables"][0]["columns"] = [
        {"name": "Facts[Category]", "type": "String"}, {"name": "[probe]", "type": "Int64"}]
    actual = await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key,
        dax="EVALUATE SUMMARIZECOLUMNS('Facts'[Category],\"probe\",[Count])", max_rows=10))
    assert actual.rows == [["alpha", 1], ["beta", None]]
    before = len(transport.calls)
    transport.query = {"Error": {"HttpStatusCode": 429}}
    with pytest.raises(PowerBIAdapterError, match="RATE_LIMITED"):
        await adapter.execute_dax(DAXRequest(semantic_model_key=ref.server_model_key, dax="EVALUATE bad"))
    assert len(transport.calls) == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [123, {}, [], True])
async def test_schema_pydantic_errors_do_not_leak_payload(harness, value):
    _, _, transport, adapter = harness
    transport.schema["schema"]["Tables"][0]["Measures"][0]["Type"] = value
    with pytest.raises(PowerBIAdapterError, match="CONTRACT_DRIFT"):
        await adapter.resolve_bootstrap("fixture")
    assert adapter.binding_count == 0


@pytest.mark.parametrize("code", ["RESOURCE_NOT_ACCESSIBLE", "MODEL_RESOLUTION_FAILED", "SCHEMA_UNAVAILABLE",
    "QUERY_REJECTED", "QUERY_TIMEOUT", "RATE_LIMITED", "UPSTREAM_UNAVAILABLE", "CONTRACT_DRIFT"])
def test_cloud_uses_single_public_failure_mapper(code):
    from backend.app.application.failure_contract import map_public_failure
    value = map_public_failure(terminal_state="failed", stage="tool_execution", error_type=code)
    assert value.code.value == code
    assert value.retryable is (code in {"QUERY_TIMEOUT", "RATE_LIMITED", "UPSTREAM_UNAVAILABLE"})


@pytest.mark.asyncio
async def test_logout_during_schema_response_creates_zero_binding(harness):
    auth, session, transport, adapter = harness
    original = transport.call
    async def call(name, args):
        value = await original(name, args)
        if name == "GetSemanticModelSchema": auth.logout(session.session_id, None)
        return value
    transport.call = call
    with pytest.raises(AuthFailure): await adapter.resolve_bootstrap("fixture")
    assert adapter.binding_count == 0


@pytest.mark.parametrize("kind", ["schema", "query"])
def test_runtime_citation_is_supplemental_not_a_payload_mirror(kind):
    import json
    from backend.app.powerbi.fabric_iq_normalization import normalize_query, normalize_schema
    body = schema() if kind == "schema" else result()
    citation = copy.deepcopy(body["semanticModel"])
    raw = {"content": [{"type": "text", "text": json.dumps(body)}],
           "structuredContent": {"artifact_citation": citation}, "isError": False}
    actual = (normalize_schema(raw, MODEL, "synthetic", 1) if kind == "schema" else
              normalize_query(raw, MODEL, DAXRequest(semantic_model_key="synthetic", dax="EVALUATE ROW(\"probe\",1)")))
    assert actual.key == "synthetic" if kind == "schema" else actual.rows == [[1]]


@pytest.mark.parametrize("citation", [{"ArtifactId": str(UUID(int=999))},
    {"ArtifactId": MODEL, "Name": "conflicting"}, {}, {"ArtifactId": MODEL, "error": "private upstream"}])
def test_runtime_citation_conflict_or_missing_identity_fails_closed(citation):
    import json
    from backend.app.powerbi.fabric_iq_normalization import normalize_schema
    raw = {"content": [{"type": "text", "text": json.dumps(schema())}],
           "structuredContent": {"artifact_citation": citation}}
    with pytest.raises(PowerBIAdapterError): normalize_schema(raw, MODEL, "synthetic", 1)


def test_runtime_citation_alone_never_authorizes_schema():
    from backend.app.powerbi.fabric_iq_normalization import normalize_schema
    with pytest.raises(PowerBIAdapterError):
        normalize_schema({"content": [], "structuredContent": {"artifact_citation": schema()["semanticModel"]}},
                         MODEL, "synthetic", 1)


def test_citation_cosmetic_links_do_not_grant_or_change_resource_authority():
    import json
    from backend.app.powerbi.fabric_iq_normalization import normalize_query
    body = result()
    body["semanticModel"].update({"IconUrl": "old-icon", "Description": "old-description"})
    citation = {"ArtifactId": MODEL, "IconUrl": "new-icon", "Description": "new-description"}
    raw = {"content": [{"type": "text", "text": json.dumps(body)}],
           "structuredContent": {"artifact_citation": citation}}
    assert normalize_query(raw, MODEL, DAXRequest(semantic_model_key="synthetic", dax="EVALUATE ROW(\"probe\",1)")).rows == [[1]]


def test_valid_rows_do_not_hide_unverified_additional_text():
    import json
    from backend.app.powerbi.fabric_iq_normalization import normalize_query
    raw = {"content": [{"type": "text", "text": json.dumps(result())},
                       {"type": "text", "text": "Unverified upstream query guidance or failure"}], "isError": False}
    with pytest.raises(PowerBIAdapterError, match="QUERY_REJECTED"):
        normalize_query(raw, MODEL, DAXRequest(semantic_model_key="synthetic", dax="EVALUATE ROW(\"probe\",1)"))


@pytest.mark.asyncio
async def test_members_reject_a_different_returned_column(harness):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = result([["alpha"]])
    transport.query["executionResult"]["tables"][0]["columns"] = [{"name": "Facts[Other]", "type": "String"}]
    with pytest.raises(PowerBIAdapterError, match="CONTRACT_DRIFT"):
        await adapter.get_column_members(ColumnMembersRequest(semantic_model_key=ref.server_model_key,
            table_name="Facts", field_name="Category", limit=5))


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["__pbiagent_probe", "[__pbiagent_probe]"])
async def test_compatibility_probe_checks_its_explicit_alias_and_value(harness, alias):
    _, _, transport, adapter = harness
    ref = await adapter.resolve_bootstrap("fixture")
    transport.query = result([[1]])
    transport.query["executionResult"]["tables"][0]["columns"] = [{"name": alias, "type": "Int64"}]
    assert (await adapter.probe_compatibility(ref.server_model_key)).compatible
