"""M6.3 server-side ownership acceptance; all identities and data synthetic."""
from uuid import UUID

import pytest
import pytest_asyncio

from backend.app.auth.models import PrincipalContext
from backend.app.config.settings import Settings
from backend.app.memory.models import RuntimeDataMode, StructuredWorkMemory
from backend.app.persistence.database import create_engine, create_session_factory
from backend.app.persistence.models import Base
from backend.app.persistence.ownership import PrincipalScopedRepositoryFactory


def principal(number=1, tenant=10, epoch=1):
    return PrincipalContext(tenant_id=str(UUID(int=tenant)), principal_id=str(UUID(int=number)),
        subject="synthetic", issuer="synthetic", display_name="synthetic", preferred_username=None,
        session_epoch=epoch, authorization_epoch=epoch)


class SyntheticAuth:
    def __init__(self, p):
        self.principal = p

    def require_session(self, sid):
        from types import SimpleNamespace
        from backend.app.auth.models import AuthFailure
        if sid != "synthetic-session":
            raise AuthFailure()
        return SimpleNamespace(principal=self.principal)


@pytest_asyncio.fixture
async def factory(tmp_path):
    engine = create_engine(Settings(_env_file=None, persistence_database_path=str(tmp_path / "owned.db")))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = PrincipalScopedRepositoryFactory(create_session_factory(engine), tmp_path / "reports")
    yield factory
    await engine.dispose()


async def bundle(factory, p=None):
    p = p or principal()
    return await factory.for_session(SyntheticAuth(p), "synthetic-session", p)


@pytest.mark.asyncio
async def test_same_ids_memory_and_history_are_independent(factory):
    a, b = await bundle(factory), await bundle(factory, principal(2))
    mode = RuntimeDataMode.REAL
    for resources in (a, b):
        await resources.memory.create_pending(StructuredWorkMemory(
            request_id="same-request", conversation_id="same-conversation", runtime_mode=mode), mode)
    await a.memory.mark_failed("same-request", mode, "synthetic")
    assert (await b.memory.get_by_request_id("same-request", mode)).failure_reason is None
    await a.history.rename(mode, "same-conversation", "A synthetic title")
    page = await b.history.list_recent(mode, limit=10, after=None)
    assert page.total_count == 1
    assert page.items[0].title != "A synthetic title"


@pytest.mark.asyncio
async def test_foreign_conversation_lifecycle_denied(factory):
    from backend.app.conversation.models import ConversationNotFoundError
    a, b = await bundle(factory), await bundle(factory, principal(2))
    mode = RuntimeDataMode.REAL
    await a.memory.create_pending(StructuredWorkMemory(request_id="a-request", conversation_id="a-conversation"), mode)
    for action in (lambda: b.history.get_history(mode, "a-conversation", limit=10, after=None),
                   lambda: b.history.rename(mode, "a-conversation", "stolen"),
                   lambda: b.history.archive(mode, "a-conversation"),
                   lambda: b.history.restore(mode, "a-conversation"),
                   lambda: b.history.delete(mode, "a-conversation")):
        with pytest.raises(ConversationNotFoundError):
            await action()
    assert await b.memory.get_by_request_id("a-request", mode) is None
    assert await b.memory.mark_failed("a-request", mode) is None
    assert (await b.history.list_recent(mode, limit=10, after=None)).total_count == 0
    assert await a.memory.get_by_request_id("a-request", mode)


def snapshot(request="same-request", conversation="same-conversation", answer="synthetic"):
    from backend.app.memory.result_snapshot import TurnResultSnapshot
    return TurnResultSnapshot(request_id=request, conversation_id=conversation,
        response_type="answer", terminal_state="completed", answer=answer,
        source_mode="real", is_mock=False, request_fingerprint_hash="f" * 64)


@pytest.mark.asyncio
@pytest.mark.parametrize("other", [principal(2), principal(1, tenant=11)])
async def test_snapshot_pending_and_memory_commit_isolation(factory, other):
    from backend.app.memory.models import PendingClarificationContext, MemoryCommitEvidence
    from backend.app.memory.repository import MemoryCommitDeniedError
    a, b = await bundle(factory), await bundle(factory, other)
    mode = RuntimeDataMode.REAL
    pending = await a.memory.create_pending(StructuredWorkMemory(
        request_id="same-request", conversation_id="same-conversation"), mode)
    evidence = MemoryCommitEvidence(intent_valid=True, request_allowed=True, query_plan_valid=True,
        dax_valid=True, tool_execution_succeeded=True, query_result_valid=True, response_valid=True,
        runtime_mode=mode)
    with pytest.raises(MemoryCommitDeniedError):
        await b.memory.commit(pending, evidence.model_copy())
    committed = await a.memory.commit(pending, evidence)
    assert committed.memory_version == 1
    assert await b.memory.get_latest_committed("same-conversation", mode) is None
    assert await b.memory.list_by_conversation("same-conversation", mode) == []
    clarification = PendingClarificationContext(conversation_id="same-conversation",
        semantic_model_key="synthetic-model", schema_fingerprint="a" * 64, last_request_id="same-request")
    await a.memory.save_pending_clarification(clarification, mode)
    assert await b.memory.get_pending_clarification("same-conversation", mode) is None
    assert await b.memory.clear_pending_clarification("same-conversation", mode) is None
    await b.memory.save_pending_clarification(clarification.model_copy(update={"measures": ["B"]}), mode)
    assert (await a.memory.get_pending_clarification("same-conversation", mode)).measures == []
    await a.snapshots.save(snapshot(answer="A synthetic RestrictedColumn"), mode)
    assert not await b.snapshots.exists("same-request", mode)
    assert await b.snapshots.get("same-request", mode) is None
    await b.snapshots.save(snapshot(answer="B synthetic public"), mode)
    assert (await a.snapshots.get("same-request", mode)).answer == "A synthetic RestrictedColumn"
    assert (await b.snapshots.get("same-request", mode)).answer == "B synthetic public"


@pytest.mark.asyncio
async def test_idempotency_shared_within_owner_and_independent_between_owners(factory):
    from backend.app.memory.result_snapshot import IdempotencyClaimStatus as Status
    a, a2, b = await bundle(factory), await bundle(factory), await bundle(factory, principal(2))
    mode = RuntimeDataMode.REAL
    assert (await a.snapshots.claim("same", mode, "A"))[0] == Status.OWNER
    assert (await b.snapshots.claim("same", mode, "B"))[0] == Status.OWNER
    assert (await a2.snapshots.claim("same", mode, "B"))[0] == Status.CONFLICT
    state, waiter = await a2.snapshots.claim("same", mode, "A")
    assert state == Status.WAITER
    await b.snapshots.complete("same", mode)
    assert not waiter.done()
    await a.snapshots.complete("same", mode)
    assert await waiter


async def seed_report(resources, number=0, conversation="same-conversation"):
    from backend.tests.unit.persistence.test_report_artifact_invariants import _artifact
    mode = RuntimeDataMode.REAL
    request = f"request-{number}"
    await resources.snapshots.save(snapshot(request, conversation), mode)
    artifact = _artifact(report_id="rpt_" + f"{number:032x}", source_mode="real",
        conversation_id=conversation, request_id=request)
    await resources.report_metadata.save(artifact)
    (resources.reports.root / artifact.relative_path).write_text(artifact.html, encoding="utf-8")
    return artifact


@pytest.mark.asyncio
async def test_report_view_download_lifecycle_and_file_cleanup_isolation(factory):
    from backend.app.report.resources import ReportNotFoundError
    a, b = await bundle(factory), await bundle(factory, principal(2))
    artifact = await seed_report(a)
    rid = artifact.report_id
    for operation in (lambda: b.reports.get(rid), lambda: b.reports.read_html(rid),
                      lambda: b.reports.rename(rid, "B"), lambda: b.reports.archive(rid, "real"),
                      lambda: b.reports.restore(rid, "real"), lambda: b.reports.delete(rid),
                      lambda: b.reports.delete_html_files([rid])):
        with pytest.raises(ReportNotFoundError):
            await operation()
    assert (await a.reports.read_html(rid))[1] == artifact.html
    assert (await b.history.list_managed_reports(RuntimeDataMode.REAL, "active", limit=10, after=None)).total_count == 0
    # Same report ID, independently managed files and metadata.
    await seed_report(b)
    await a.reports.archive(rid, "real")
    assert (await b.history.list_managed_reports(RuntimeDataMode.REAL, "active", limit=10, after=None)).total_count == 1
    await a.reports.restore(rid, "real")
    await a.reports.delete(rid)
    assert (await b.reports.read_html(rid))[1] == artifact.html
    assert (b.reports.root / artifact.relative_path).exists()


@pytest.mark.asyncio
async def test_delete_intent_crash_recovery_cannot_cross_owner(factory):
    from backend.app.report.resources import ReportNotFoundError
    from backend.app.persistence.repositories.common import PersistenceRepositoryError
    a, b = await bundle(factory), await bundle(factory, principal(2))
    artifact = await seed_report(a)
    await seed_report(b)
    mode = RuntimeDataMode.REAL
    deleted = await a.history.delete(mode, "same-conversation")
    with pytest.raises(PersistenceRepositoryError):
        await a.snapshots.save(snapshot(), mode)
    await b.history.complete_delete(mode, "same-conversation")
    with pytest.raises(ReportNotFoundError):
        await b.reports.delete_html_files(deleted.report_ids)
    a2 = await bundle(factory)
    assert (await a2.history.delete(mode, "same-conversation")).report_ids == deleted.report_ids
    await a2.reports.delete_html_files(deleted.report_ids)
    await a2.history.complete_delete(mode, "same-conversation")
    assert (await b.reports.read_html(artifact.report_id))[1] == artifact.html


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["recent", "archived", "search", "history", "reports", "report_resources"])
async def test_cursor_signed_for_owner_epoch_and_query_scope(factory, kind):
    from backend.app.application.conversation_history_service import InvalidConversationCursorError
    a, b = await bundle(factory), await bundle(factory, principal(2))
    mode = RuntimeDataMode.REAL
    for n in range(3):
        await seed_report(a, n)
        await a.history.record_failed(mode, f"conv-{n}", title="synthetic", error_type="synthetic")
        if kind == "archived":
            await a.history.archive(mode, f"conv-{n}")
    def call(resources, cursor=None):
        service = resources.history_service
        if kind == "recent": return service.list_recent(mode, limit=1, cursor=cursor)
        if kind == "archived": return service.list_archived(mode, limit=1, cursor=cursor)
        if kind == "search": return service.search(mode, query="synthetic", limit=1, cursor=cursor)
        if kind == "history": return service.get_history(mode, "same-conversation", limit=1, cursor=cursor)
        if kind == "reports": return service.list_reports(mode, "same-conversation", limit=1, cursor=cursor)
        return service.list_managed_reports(mode, status="active", limit=1, cursor=cursor)
    cursor = (await call(a)).next_cursor
    assert cursor
    assert (await call(a, cursor)).items
    for resources in (b, await bundle(factory, principal(epoch=2))):
        with pytest.raises(InvalidConversationCursorError):
            await call(resources, cursor)
    with pytest.raises(InvalidConversationCursorError):
        await call(a, cursor[:-1] + ("0" if cursor[-1] != "0" else "1"))


@pytest.mark.asyncio
async def test_search_count_and_local_namespace_are_isolated(factory):
    from backend.app.persistence.repositories.memory import SQLiteMemoryRepository
    from backend.app.persistence.repositories.conversation_history import SQLiteConversationHistoryRepository
    a, b = await bundle(factory), await bundle(factory, principal(2))
    mode = RuntimeDataMode.REAL
    local = SQLiteMemoryRepository(factory._sessions)
    local_history = SQLiteConversationHistoryRepository(factory._sessions)
    await local.create_pending(StructuredWorkMemory(request_id="same", conversation_id="same"), mode)
    await local_history.rename(mode, "same", "local-only synthetic")
    await a.history.record_failed(mode, "same", title="A-only synthetic", error_type="synthetic")
    assert (await b.history.search(mode, "synthetic", limit=10, after=None)).total_count == 0
    assert (await a.history.search(mode, "local-only", limit=10, after=None)).total_count == 0
    assert (await local_history.search(mode, "A-only", limit=10, after=None)).total_count == 0
    assert (await a.history.search(mode, "A-only", limit=10, after=None)).total_count == 1


@pytest.mark.asyncio
async def test_logout_switch_and_late_repository_response_denied(factory):
    from backend.app.auth.models import AuthFailure
    auth = SyntheticAuth(principal())
    a = await factory.for_session(auth, "synthetic-session", auth.principal)
    artifact = await seed_report(a)
    await a.reports.get(artifact.report_id)
    auth.principal = principal(2, epoch=2)
    b = await factory.for_session(auth, "synthetic-session", auth.principal)
    for operation in (lambda: a.reports.read_html(artifact.report_id),
                      lambda: a.memory.get_by_request_id("request-0", RuntimeDataMode.REAL),
                      lambda: a.snapshots.claim("late", RuntimeDataMode.REAL, "a")):
        with pytest.raises(AuthFailure):
            await operation()
    assert (await b.history.list_recent(RuntimeDataMode.REAL, limit=10, after=None)).total_count == 0


@pytest.mark.asyncio
async def test_logout_during_database_await_discards_result(factory, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.app.auth.models import AuthFailure
    auth = SyntheticAuth(principal())
    a = await factory.for_session(auth, "synthetic-session", auth.principal)
    await a.memory.create_pending(StructuredWorkMemory(request_id="late", conversation_id="late"), RuntimeDataMode.REAL)
    execute = AsyncSession.execute

    async def switched(session, *args, **kwargs):
        result = await execute(session, *args, **kwargs)
        auth.principal = principal(2, epoch=2)
        return result

    monkeypatch.setattr(AsyncSession, "execute", switched)
    with pytest.raises(AuthFailure):
        await a.memory.get_by_request_id("late", RuntimeDataMode.REAL)


@pytest.mark.asyncio
async def test_logout_during_idempotency_claim_rejects_and_cleans_up(factory, monkeypatch):
    from backend.app.auth.models import AuthFailure
    from backend.app.memory.result_snapshot import IdempotencyClaimStatus
    auth = SyntheticAuth(principal())
    a = await factory.for_session(auth, "synthetic-session", auth.principal)
    original = factory._in_flight.claim

    async def switched(*args, **kwargs):
        result = await original(*args, **kwargs)
        auth.principal = principal(2, epoch=2)
        return result

    monkeypatch.setattr(factory._in_flight, "claim", switched)
    with pytest.raises(AuthFailure):
        await a.snapshots.claim("late", RuntimeDataMode.REAL, "synthetic")
    monkeypatch.setattr(factory._in_flight, "claim", original)
    # No abandoned owner/waiter after the invalidated operation.
    state, _ = await original(a.snapshots._idempotency._key("late"), RuntimeDataMode.REAL, "synthetic")
    assert state == IdempotencyClaimStatus.OWNER
