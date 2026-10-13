"""M6.4 scoped catalog, coverage and per-model authorization contracts."""
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.application.cloud_catalog_service import CloudCatalogService, SharedModelSeed
from backend.app.auth.models import AuthFailure
from backend.app.powerbi.fabric_iq_contract import fail
from backend.tests.unit.test_cloud_catalog_transport import context  # noqa: F401

WS, MODEL = (str(UUID(int=i)) for i in (11,10))


class REST:
    def assert_session_binding(self, *args): pass
    workspaces = [{"id":WS,"displayName":"Synthetic Workspace"}]
    models = [{"id":MODEL,"workspaceId":WS,"displayName":"Synthetic Model","type":"SemanticModel"}]
    reports = [{"id":str(UUID(int=15)),"workspaceId":WS,"displayName":"Synthetic Report","type":"Report"}]
    error = None
    report_error = None
    async def list_workspaces(self):
        if self.error: raise self.error
        return self.workspaces
    async def list_models(self, ws): return self.models
    async def list_reports(self, ws):
        if self.report_error: raise self.report_error
        return self.reports


class Adapter:
    def assert_session_binding(self, *args): pass
    def __init__(self): self.calls = []; self.error = None
    async def bind_catalog_model(self, ws, model):
        self.calls.append((ws,model))
        if self.error: raise self.error
        return SimpleNamespace(server_model_key="fabric_iq:synthetic-opaque", display_name="Schema Model")


def service(context, rest=None, adapter=None, **kwargs):
    auth, session, _ = context
    return CloudCatalogService(auth, session.session_id, session.principal,
        rest or REST(), adapter or Adapter(), **kwargs)


@pytest.mark.asyncio
async def test_catalog_stage_timings_never_log_identity_or_provider_details(context, caplog):
    import logging
    namespace = "backend.app.application.cloud_catalog_service"
    caplog.set_level(logging.INFO, logger=namespace)
    await service(context).discover()
    failed = Adapter()
    failed.error = RuntimeError("PRIVATE_PROVIDER_DETAIL")
    await service(context, adapter=failed).discover()
    messages = [record.getMessage() for record in caplog.records if record.name == namespace]
    assert len(messages) == 8
    assert any("stage=authorize_model outcome=failed" in message for message in messages)
    combined = "\n".join(messages)
    assert all(value not in combined for value in (WS, MODEL, "Synthetic Workspace", "Schema Model",
                                                   "PRIVATE_PROVIDER_DETAIL", "fabric_iq:synthetic-opaque"))


@pytest.mark.asyncio
async def test_independent_model_authorizations_overlap_with_hard_bound(context):
    import asyncio
    rest = REST()
    rest.models = [{"id":str(UUID(int=100+i)),"workspaceId":WS,"displayName":"Synthetic Model",
                    "type":"SemanticModel"} for i in range(7)]
    class ConcurrentAdapter(Adapter):
        active = peak = 0
        async def bind_catalog_model(self, ws, model):
            self.calls.append((ws, model))
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.01)
                return SimpleNamespace(server_model_key="opaque-"+str(rest.models.index(next(
                    item for item in rest.models if item["id"] == model))), display_name="Synthetic Model")
            finally: self.active -= 1
    adapter = ConcurrentAdapter()
    catalog = await service(context, rest=rest, adapter=adapter).discover()
    assert 2 <= adapter.peak <= 3
    assert adapter.active == 0 and len(adapter.calls) == len(catalog.items) == 7
    assert len({item.key for item in catalog.items}) == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidate", ["logout", "cancel"])
async def test_parallel_authorization_failure_drains_all_siblings(context, invalidate):
    import asyncio
    auth, session, _ = context
    rest = REST()
    rest.models = [{"id":str(UUID(int=100+i)),"workspaceId":WS,"displayName":"Synthetic Model",
                    "type":"SemanticModel"} for i in range(7)]
    started = asyncio.Event()
    release = asyncio.Event()
    class WaitingAdapter(Adapter):
        active = 0
        async def bind_catalog_model(self, ws, model):
            self.calls.append((ws, model))
            self.active += 1
            if self.active == 3: started.set()
            try:
                await release.wait()
                if model == rest.models[0]["id"]:
                    auth.logout(session.session_id, None)
                    raise AuthFailure("AUTH_FORBIDDEN",403)
                await asyncio.Event().wait()
            finally: self.active -= 1
    adapter = WaitingAdapter()
    task = asyncio.create_task(service(context, rest=rest, adapter=adapter).discover())
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        if invalidate == "logout":
            release.set()
            with pytest.raises(AuthFailure): await asyncio.wait_for(task, timeout=1)
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
        assert adapter.active == 0 and len(adapter.calls) == 3
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_budget_returns_only_verified_models_and_declares_unverified_remainder(context):
    import asyncio
    auth, _, _ = context
    auth.settings = auth.settings.model_copy(update={"request_timeout_seconds":0.15})
    rest = REST()
    rest.models = [{"id":str(UUID(int=100+i)),"workspaceId":WS,"displayName":"Synthetic Model",
                    "type":"SemanticModel"} for i in range(7)]
    class SlowAdapter(Adapter):
        active = 0
        async def bind_catalog_model(self, ws, model):
            self.active += 1
            try:
                await asyncio.sleep(0.001 if model == rest.models[0]["id"] else 2)
                return SimpleNamespace(server_model_key="verified-only", display_name="Synthetic Model")
            finally: self.active -= 1
    adapter = SlowAdapter()
    catalog = await asyncio.wait_for(service(context, rest=rest, adapter=adapter).discover(), timeout=0.5)
    assert [item.key for item in catalog.items] == ["verified-only"]
    assert catalog.status == "partial" and catalog.error_type == "QUERY_TIMEOUT"
    assert catalog.workspace_scope_complete and not catalog.authorization_scope_complete
    assert catalog.unverified_count == 6 and catalog.inaccessible_count == 0
    assert adapter.active == 0


@pytest.mark.asyncio
async def test_rate_limit_stops_authorization_fanout_without_claiming_access_denied(context):
    import asyncio
    rest = REST()
    rest.models = [{"id":str(UUID(int=100+i)),"workspaceId":WS,"displayName":"Synthetic Model",
                    "type":"SemanticModel"} for i in range(12)]
    class ThrottledAdapter(Adapter):
        active = 0
        async def bind_catalog_model(self, ws, model):
            self.calls.append((ws, model))
            self.active += 1
            try:
                if model == rest.models[0]['id']:
                    return SimpleNamespace(server_model_key='verified-only', display_name='Synthetic Model')
                await asyncio.sleep(0.01)
                raise fail('RATE_LIMITED')
            finally: self.active -= 1
    adapter = ThrottledAdapter()
    result = await service(context, rest=rest, adapter=adapter).discover()
    assert [item.key for item in result.items] == ['verified-only']
    assert result.status == 'partial' and result.error_type == 'RATE_LIMITED'
    assert not result.authorization_scope_complete and result.unverified_count == 11
    assert result.inaccessible_count == 0
    assert len(adapter.calls) <= 4 and adapter.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['QUERY_TIMEOUT', 'UPSTREAM_UNAVAILABLE', 'CONTRACT_DRIFT'])
async def test_failed_validation_is_unverified_not_proven_inaccessible(context, code):
    adapter = Adapter(); adapter.error = fail(code)
    result = await service(context, adapter=adapter).discover()
    assert result.status == 'error' and result.items == []
    assert not result.authorization_scope_complete and result.unverified_count == 1
    assert result.inaccessible_count == 0 and result.error_type == code


@pytest.mark.asyncio
async def test_each_model_authorized_keys_safe_and_coverage_honest(context):
    adapter = Adapter()
    catalog = await service(context, adapter=adapter).discover()
    assert adapter.calls == [(WS,MODEL)]
    assert catalog.status == "partial" and catalog.workspace_scope_complete
    assert catalog.individual_share_coverage == "configured_seeds_only"
    assert len(catalog.items) == 1
    item = catalog.items[0]
    assert item.key.startswith("fabric_iq:") and item.workspace_display_name == "Synthetic Workspace"
    assert item.accessibility == "available"
    serialized = catalog.model_dump_json()
    for sensitive in [WS,MODEL,context[1].session_id,context[1].principal.principal_id,"https://"]:
        assert sensitive not in serialized


@pytest.mark.asyncio
async def test_empty_membership_is_partial_when_shared_coverage_unknown(context):
    rest = REST(); rest.workspaces = []
    result = await service(context,rest).discover()
    assert result.items == [] and result.status == "partial" and result.workspace_scope_complete


@pytest.mark.asyncio
async def test_shared_seeds_dedup_and_reauthorization(context):
    rest, adapter = REST(), Adapter()
    seed = SharedModelSeed(workspace_id=WS, model_id=MODEL, workspace_display_name="Seed workspace")
    catalog = await service(context,rest,adapter, shared_seeds=(seed,seed)).discover()
    assert len(catalog.items) == len(adapter.calls) == 1
    rest.workspaces = []
    adapter.calls.clear()
    catalog = await service(context,rest,adapter,shared_seeds=(seed,)).discover()
    assert adapter.calls == [(WS,MODEL)] and catalog.items[0].workspace_display_name == "Seed workspace"


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status", [("RESOURCE_NOT_ACCESSIBLE","forbidden"), ("UPSTREAM_UNAVAILABLE","error"),
    ("RATE_LIMITED","error"), ("CONTRACT_DRIFT","error")])
async def test_top_level_failure_cannot_claim_empty(context,code,status):
    rest = REST(); rest.error = fail(code)
    catalog = await service(context,rest).discover()
    assert catalog.status == status and not catalog.workspace_scope_complete
    assert catalog.items == [] and catalog.error_type == code


@pytest.mark.asyncio
async def test_report_partial_failure_keeps_authorized_models(context):
    rest = REST(); rest.report_error = fail("RATE_LIMITED")
    result = await service(context,rest).discover()
    assert result.status == "partial" and len(result.items) == 1
    assert not result.workspace_scope_complete


@pytest.mark.asyncio
async def test_inaccessible_candidate_is_never_returned(context):
    adapter = Adapter(); adapter.error = fail("SCHEMA_UNAVAILABLE")
    result = await service(context,adapter=adapter).discover()
    assert result.items == [] and result.status == "partial"
    assert result.inaccessible_count == 1


@pytest.mark.asyncio
async def test_conflicting_duplicate_or_wrong_workspace_cannot_authorize(context):
    rest, adapter = REST(), Adapter()
    rest.models = REST.models + [REST.models[0] | {"displayName":"Conflicting"}]
    result = await service(context,rest,adapter).discover()
    assert result.items == [] and not result.workspace_scope_complete and not adapter.calls
    rest.models = [REST.models[0] | {"workspaceId":str(UUID(int=99))}]
    result = await service(context,rest,adapter).discover()
    assert result.items == [] and not result.workspace_scope_complete and not adapter.calls


@pytest.mark.asyncio
async def test_logout_during_model_authorization_discards_all(context):
    auth, session, _ = context
    class Late(Adapter):
        async def bind_catalog_model(self, ws, model):
            auth.logout(session.session_id,None)
            return await super().bind_catalog_model(ws,model)
    with pytest.raises(AuthFailure): await service(context,adapter=Late()).discover()


@pytest.mark.asyncio
async def test_safe_display_names_are_bounded_and_controls_removed(context):
    rest = REST(); rest.workspaces = [{"id":WS,"displayName":"Safe\x00\n" + "x"*250}]
    result = await service(context,rest).discover()
    name = result.items[0].workspace_display_name
    assert len(name) == 200 and all(c.isprintable() for c in name)


@pytest.mark.asyncio
async def test_schema_identity_not_client_catalog_name_is_used(context):
    result = await service(context).discover()
    assert result.items[0].display_name == "Schema Model"


@pytest.mark.asyncio
async def test_cross_session_service_cannot_be_reused(context):
    auth, session, _ = context
    current = service(context)
    auth.logout(session.session_id,None)
    with pytest.raises(AuthFailure): await current.discover()
