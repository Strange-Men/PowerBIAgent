"""M6.5.2 FIX6: new-report locale labels and bounded resource batch mutation."""
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.application.cloud_product_services import CloudProductServiceFactory
from backend.app.application.cloud_workspace_service import CloudWorkspaceService
from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import Base, ReportPresentationModel
from backend.app.persistence.repositories.report_artifact import (
    SQLiteReportArtifactRepository,
)
from backend.app.powerbi.base import PowerBIAdapterError
from backend.app.presentation.locale import presentation_locale
from backend.app.report.resources import LocalReportRepository, ReportSpec
from backend.tests.api.test_cloud_product_api import cloud_product


def _report_spec(title: str) -> ReportSpec:
    return ReportSpec(
        title=title,
        template_key="sales_report",
        summary="stored",
        source_mode="mock",
        contract_version="1.0",
        semantic_model_key="mock_sales_model",
        schema_fingerprint="a" * 64,
        verified_fact_set_ids=["fact-1"],
        query_result_ids=["query-1"],
    )


@pytest_asyncio.fixture
async def report_metadata_env(tmp_path):
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(tmp_path / "fix6.db"),
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await configure_engine(engine)
    session_factory = create_session_factory(engine)
    metadata = SQLiteReportArtifactRepository(session_factory)
    yield SimpleNamespace(
        session_factory=session_factory,
        metadata=metadata,
        repository=LocalReportRepository(tmp_path / "reports", metadata),
    )
    await dispose_engine(engine)


async def _display_title(
    session_factory: async_sessionmaker[AsyncSession], report_id: str
) -> str:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(ReportPresentationModel).where(
                    ReportPresentationModel.report_id == report_id
                )
            )
        ).scalar_one()
        return row.display_title


@pytest.mark.asyncio
async def test_new_report_display_title_uses_request_locale(report_metadata_env) -> None:
    env = report_metadata_env
    with presentation_locale("en-US"):
        executive = await env.repository.store(
            _report_spec("销售经营分析报告"), "<!DOCTYPE html><html></html>"
        )
        simple = await env.repository.store(
            _report_spec("销售分析报表"), "<!DOCTYPE html><html></html>"
        )
    assert await _display_title(env.session_factory, executive.report_id) == (
        "Sales Performance Analysis Report"
    )
    assert await _display_title(env.session_factory, simple.report_id) == (
        "Sales Analysis Report"
    )

    with presentation_locale("zh-CN"):
        chinese = await env.repository.store(
            _report_spec("销售分析报表"), "<!DOCTYPE html><html></html>"
        )
    assert await _display_title(env.session_factory, chinese.report_id) == "销售分析报表"


@pytest.mark.asyncio
async def test_manual_rename_and_historical_rows_are_never_relabelled(
    report_metadata_env,
) -> None:
    env = report_metadata_env
    with presentation_locale("zh-CN"):
        historical = await env.repository.store(
            _report_spec("销售分析报表"), "<!DOCTYPE html><html></html>"
        )
    # Reading/listing under another locale must not rewrite stored metadata.
    with presentation_locale("en-US"):
        await env.metadata.get(historical.report_id)
    assert await _display_title(env.session_factory, historical.report_id) == "销售分析报表"

    await env.metadata.rename(historical.report_id, "My verified report")
    with presentation_locale("en-US"):
        await env.metadata.get(historical.report_id)
    assert await _display_title(env.session_factory, historical.report_id) == "My verified report"


@pytest.mark.asyncio
async def test_report_identity_and_facts_survive_title_localization(
    report_metadata_env,
) -> None:
    env = report_metadata_env
    spec = _report_spec("销售分析报表")
    with presentation_locale("en-US"):
        artifact = await env.repository.store(spec, "<!DOCTYPE html><html></html>")
    stored = await env.metadata.get(artifact.report_id)
    assert stored.report_id == artifact.report_id
    assert stored.template_key == spec.template_key
    assert stored.semantic_model_key == spec.semantic_model_key
    assert stored.schema_fingerprint == spec.schema_fingerprint
    assert stored.verified_fact_set_ids == spec.verified_fact_set_ids
    assert stored.query_result_ids == spec.query_result_ids
    assert spec.title == "销售分析报表"  # canonical ReportSpec is not rewritten


def _seed_report(client, headers, status, request_id, *, locale=None,
                 template="sales_report") -> str:
    body = {
        "message": "生成销售分析报表",
        "request_id": request_id,
        "expected_generation": status["generation"],
        "report_template_key": template,
    }
    if locale is not None:
        body["locale"] = locale
    response = client.post("/api/v1/cloud/chat", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["report"]["report_id"]


def _batch(client, headers, status, kind, action, ids, *, generation=None):
    return client.post(
        "/api/v1/cloud/resources/batch",
        headers=headers,
        json={
            "kind": kind,
            "action": action,
            "resource_ids": ids,
            "expected_generation": status["generation"] if generation is None else generation,
        },
    )


def test_new_report_title_follows_locale_and_rename_is_preserved(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    english = _seed_report(c, h, s, "locale-en", locale="en-US",
                           template="sales_executive_report")
    items = c.get("/api/v1/cloud/reports").json()["items"]
    assert next(item for item in items if item["report_id"] == english)["display_title"] == (
        "Sales Performance Analysis Report"
    )

    chinese = _seed_report(c, h, s, "locale-zh", locale="zh-CN",
                           template="sales_executive_report")
    items = c.get("/api/v1/cloud/reports").json()["items"]
    by_id = {item["report_id"]: item["display_title"] for item in items}
    assert by_id[chinese] == "销售经营分析报告"
    # A labelled report is not migrated when another request selects a locale.
    assert by_id[english] == "Sales Performance Analysis Report"

    rename = c.post(
        f"/api/v1/cloud/reports/{english}/rename",
        headers=h,
        json={"expected_generation": c.get("/api/v1/cloud/status").json()["generation"],
              "title": "Custom quarterly report"},
    )
    assert rename.status_code == 200, rename.text
    _seed_report(c, h, c.get("/api/v1/cloud/status").json(), "locale-en-2", locale="en-US")
    items = c.get("/api/v1/cloud/reports").json()["items"]
    assert next(item for item in items if item["report_id"] == english)["display_title"] == (
        "Custom quarterly report"
    )


def test_batch_report_delete_uses_one_access_proof(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    ids = [_seed_report(c, h, s, f"batch-report-{index}") for index in range(7)]
    response = _batch(c, h, s, "reports", "delete", ids)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded_ids"] == ids
    assert body["failed"] == []
    assert body["batch"]["resource_count"] == 7
    assert body["batch"]["success_count"] == 7
    assert body["batch"]["proof_count"] == 1
    assert c.get("/api/v1/cloud/reports").json()["items"] == []


def test_batch_delete_isolates_one_missing_resource(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    first = _seed_report(c, h, s, "isolate-1")
    second = _seed_report(c, h, s, "isolate-2")
    missing = "rpt_" + "0" * 32
    response = _batch(c, h, s, "reports", "delete", [first, missing, second])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded_ids"] == [first, second]
    assert [item["resource_id"] for item in body["failed"]] == [missing]
    assert body["failed"][0]["code"] == "RESOURCE_NOT_FOUND"
    assert body["batch"]["success_count"] == 2 and body["batch"]["failure_count"] == 1
    assert c.get("/api/v1/cloud/reports").json()["items"] == []


def test_batch_rejects_stale_generation_without_expired_authorization(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    report_id = _seed_report(c, h, s, "stale-report")
    response = _batch(c, h, s, "reports", "delete", [report_id], generation=s["generation"] + 1)
    assert response.status_code == 409
    assert response.json()["detail"] == "cloud_selection_changed"
    assert c.get("/api/v1/cloud/reports").json()["items"][0]["report_id"] == report_id


def test_batch_requires_authenticated_session(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    report_id = _seed_report(c, h, s, "auth-report")
    c.cookies.clear()
    response = _batch(c, h, s, "reports", "delete", [report_id])
    assert response.status_code == 401


def test_batch_delete_retry_is_idempotent_and_does_not_corrupt(cloud_product, monkeypatch) -> None:
    from pathlib import Path

    c, _, h, s, _ = cloud_product
    blocked = _seed_report(c, h, s, "retry-blocked")
    healthy = _seed_report(c, h, s, "retry-healthy")
    original = Path.unlink

    def fail_html(path, *args, **kwargs):
        if path.name == blocked + ".html":
            raise OSError("synthetic batch delete interruption")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "unlink", fail_html)
        response = _batch(c, h, s, "reports", "delete", [blocked, healthy])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded_ids"] == [healthy]
    assert [item["resource_id"] for item in body["failed"]] == [blocked]
    assert body["failed"][0]["code"] == "PERSISTENCE_UNAVAILABLE"
    assert c.get(f"/api/v1/cloud/reports/{healthy}/download").status_code == 404

    current = c.get("/api/v1/cloud/status").json()
    retry = _batch(c, h, current, "reports", "delete", [blocked])
    assert retry.status_code == 200, retry.text
    assert retry.json()["succeeded_ids"] == [blocked]
    assert c.get(f"/api/v1/cloud/reports/{blocked}/download").status_code == 404


def test_batch_archive_and_unarchive_reports(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    ids = [_seed_report(c, h, s, f"archive-report-{index}") for index in range(3)]
    archived = _batch(c, h, s, "reports", "archive", ids)
    assert archived.status_code == 200, archived.text
    assert archived.json()["succeeded_ids"] == ids
    assert c.get("/api/v1/cloud/reports").json()["items"] == []
    assert {item["report_id"] for item in c.get("/api/v1/cloud/reports?status=archived").json()["items"]} == set(ids)

    restored = _batch(c, h, c.get("/api/v1/cloud/status").json(), "reports", "unarchive", ids)
    assert restored.status_code == 200, restored.text
    assert restored.json()["succeeded_ids"] == ids
    active = {item["report_id"] for item in c.get("/api/v1/cloud/reports").json()["items"]}
    assert active == set(ids)


class _BatchFakeAuth:
    def __init__(self):
        self.settings = SimpleNamespace(fabric_test_mode=False)
        self.principal = SimpleNamespace(tenant_id="tenant", principal_id="principal")

    def require_session(self, sid):
        return SimpleNamespace(principal=self.principal)


class _BatchFakeAdapter:
    def assert_session_binding(self, auth, sid, principal):
        return None

    def bound_resource_identity(self, key):
        return ("workspace-1", "model-1")


class _BatchFakeWorkspace(CloudWorkspaceService):
    """Native metadata boundary: no semantic schema may be restored."""

    _synthetic_product = False

    def __init__(self):
        self.summary_calls = 0
        self.revalidate_calls = 0

    def policy_snapshot(self):
        return ("product", True, True)

    def status(self, sid, principal):
        return SimpleNamespace(generation=3, selected_model_key="retail-model",
                               conversation_id="conversation-1")

    def require_persistence(self, sid, principal, *, binding=None):
        return None

    async def authorize_persisted_summary(self, sid, principal, binding):
        self.summary_calls += 1

    async def revalidate_binding(self, *args, **kwargs):
        self.revalidate_calls += 1
        raise AssertionError("semantic schema revalidation is not metadata authority")

    def _context(self, sid, principal):
        return SimpleNamespace(adapter=_BatchFakeAdapter())

    def data_mode(self, sid, principal):
        from backend.app.memory.models import RuntimeDataMode

        return RuntimeDataMode.REAL


def test_native_batch_delete_uses_one_metadata_proof_without_schema() -> None:
    import asyncio

    binding = SimpleNamespace(workspace_id="workspace-1", model_id="model-1",
                              model_key="retail-model", schema_fingerprint="fingerprint",
                              source_mode="real")
    artifact = SimpleNamespace(report_id="rpt_" + "1" * 32,
                               semantic_model_key="retail-model",
                               schema_fingerprint="fingerprint",
                               source_mode="real",
                               conversation_id="conversation-1")

    class Reports:
        calls = []

        async def delete(self, report_id):
            self.calls.append(report_id)
            return SimpleNamespace(report_id=report_id)

    class ReportMetadata:
        @staticmethod
        async def get_for_delete(report_id):
            return artifact

    class CloudBindings:
        @staticmethod
        async def get(conversation_id):
            return binding

        @staticmethod
        async def delete(conversation_id):
            return None

    class Repositories:
        report_metadata = ReportMetadata()
        reports = Reports()
        cloud_bindings = CloudBindings()

    class Factory:
        async def for_session(self, auth, sid, principal):
            return Repositories()

    workspace = _BatchFakeWorkspace()
    auth = _BatchFakeAuth()
    service = CloudProductServiceFactory(auth, workspace, Factory(), None, None)
    result = asyncio.run(service.batch_mutate_resources(
        "session-1", auth.principal, "reports", "delete", [artifact.report_id],
        expected_generation=3))
    assert result["succeeded_ids"] == [artifact.report_id]
    assert result["batch"]["proof_count"] == 1
    assert workspace.summary_calls == 1
    assert workspace.revalidate_calls == 0
    assert Repositories.reports.calls == [artifact.report_id]


def test_native_batch_isolates_resource_access_denial() -> None:
    import asyncio

    from backend.app.memory.models import RuntimeDataMode

    good = SimpleNamespace(workspace_id="workspace-1", model_id="model-1",
                           model_key="retail-model", schema_fingerprint="fingerprint",
                           source_mode="real")
    bad = SimpleNamespace(workspace_id="workspace-bad", model_id="model-1",
                          model_key="retail-model", schema_fingerprint="fingerprint",
                          source_mode="real")
    bindings = {"conversation-ok": good, "conversation-bad": bad}

    class CloudBindings:
        calls = []

        @staticmethod
        async def get(conversation_id):
            return bindings[conversation_id]

        @classmethod
        async def delete(cls, conversation_id):
            cls.calls.append(conversation_id)

    class HistoryService:
        calls = []

        async def delete(self, mode, conversation_id):
            self.calls.append((mode, conversation_id))
            return SimpleNamespace(conversation_id=conversation_id)

    class Repositories:
        cloud_bindings = CloudBindings()
        history_service = HistoryService()
        report_metadata = SimpleNamespace()

    class Factory:
        async def for_session(self, auth, sid, principal):
            return Repositories()

    class Workspace(_BatchFakeWorkspace):
        async def authorize_persisted_summary(self, sid, principal, binding):
            if binding.workspace_id == "workspace-bad":
                raise PowerBIAdapterError(
                    "RESOURCE_NOT_ACCESSIBLE", provider="fabric_iq",
                    error_type="RESOURCE_NOT_ACCESSIBLE")
            self.summary_calls += 1

    workspace = Workspace()
    auth = _BatchFakeAuth()
    service = CloudProductServiceFactory(auth, workspace, Factory(), None, None)
    result = asyncio.run(service.batch_mutate_resources(
        "session-1", auth.principal, "history", "delete",
        ["conversation-bad", "conversation-ok"], expected_generation=3))
    assert result["succeeded_ids"] == ["conversation-ok"]
    assert result["failed"] == [{
        "resource_id": "conversation-bad", "code": "RESOURCE_NOT_ACCESSIBLE",
        "reason": "resource_not_accessible", "recovery": "reselect_model"}]
    assert result["batch"]["proof_count"] == 1
    assert Repositories.history_service.calls == [
        (RuntimeDataMode.REAL, "conversation-ok")]
    assert CloudBindings.calls == ["conversation-ok"]


def _seed_conversation(client, headers, status, request_id) -> dict:
    response = client.post(
        "/api/v1/cloud/chat",
        headers=headers,
        json={
            "message": "查询总销售额",
            "request_id": request_id,
            "expected_generation": status["generation"],
        },
    )
    assert response.status_code == 200, response.text
    return client.get("/api/v1/cloud/status").json()


def test_batch_delete_conversations_updates_current_generation(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    first = _seed_conversation(c, h, s, "conv-first")
    first_id = first["conversation_id"]
    new_chat = c.post(
        "/api/v1/cloud/new-chat", headers=h, json={"expected_generation": first["generation"]}
    ).json()
    second = _seed_conversation(c, h, new_chat, "conv-second")
    second_id = second["conversation_id"]
    response = _batch(
        c, h, second, "history", "delete", [first_id, second_id]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded_ids"] == [first_id, second_id]
    assert body["batch"]["proof_count"] == 1
    assert body["workspace_status"]["generation"] > second["generation"]
    assert body["workspace_status"]["conversation_id"] != second_id
    assert c.get("/api/v1/cloud/history").json()["items"] == []


def test_batch_archive_conversations_is_stable(cloud_product) -> None:
    c, _, h, s, _ = cloud_product
    first = _seed_conversation(c, h, s, "archive-conv-first")
    first_id = first["conversation_id"]
    new_chat = c.post(
        "/api/v1/cloud/new-chat", headers=h, json={"expected_generation": first["generation"]}
    ).json()
    second = _seed_conversation(c, h, new_chat, "archive-conv-second")
    response = _batch(c, h, second, "history", "archive", [first_id, second["conversation_id"]])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded_ids"] == [first_id, second["conversation_id"]]
    assert body["workspace_status"]["generation"] > second["generation"]
    assert c.get("/api/v1/cloud/history").json()["items"] == []
    archived = c.get("/api/v1/cloud/history?status=archived").json()["items"]
    assert {item["conversation_id"] for item in archived} == {
        first_id, second["conversation_id"]}


def test_binding_grouping_shares_one_proof_per_durable_binding() -> None:
    """Two durable bindings mean exactly two access proofs, never per row."""
    principal = SimpleNamespace(tenant_id="t", principal_id="p")
    bindings = {
        "conv-a": SimpleNamespace(workspace_id=UUID(int=1), model_id=UUID(int=2),
                                  model_key="model-a", schema_fingerprint="a" * 64,
                                  source_mode="real"),
        "conv-b": SimpleNamespace(workspace_id=UUID(int=1), model_id=UUID(int=2),
                                  model_key="model-a", schema_fingerprint="b" * 64,
                                  source_mode="real"),
        "conv-c": SimpleNamespace(workspace_id=UUID(int=1), model_id=UUID(int=2),
                                  model_key="model-a", schema_fingerprint="b" * 64,
                                  source_mode="real"),
    }

    class Repos:
        class cloud_bindings:
            @staticmethod
            async def get(conversation_id):
                return bindings[conversation_id]

    class Workspace:
        _synthetic_product = False
        proofs = []

        async def authorize_persisted_summary(self, sid, who, binding):
            self.proofs.append(binding)

        def require_persistence(self, sid, who):
            return True

    workspace = Workspace()
    auth = SimpleNamespace(settings=SimpleNamespace(fabric_test_mode=False),
                           require_session=lambda sid: SimpleNamespace(principal=principal))
    factory = CloudProductServiceFactory(
        auth, workspace, repository_factory=None, llm_registry=None, display_llm_registry=None
    )
    proofs = set()

    import asyncio

    async def read():
        for conversation_id in bindings:
            await factory._authorize(
                Repos(), "sid", principal, conversation_id,
                access_proofs=proofs, metadata_only=True,
            )

    asyncio.run(read())
    assert len(workspace.proofs) == 2
    assert len(proofs) == 2