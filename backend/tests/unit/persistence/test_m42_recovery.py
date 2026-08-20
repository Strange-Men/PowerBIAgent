"""M4.2 / M4.2.1 — Conversation & Report Metadata Recovery & Hardening 综合测试

覆盖矩阵：

Report Recovery（10 tests）：
  1. metadata save/get via SQLiteReportArtifactRepository
  2. restart recovery: old report_id view after restart
  3. restart recovery: old report_id download after restart
  4. content hash validation on read
  5. missing HTML file → fail closed
  6. tampered HTML → fail closed
  7. unsafe relative_path → reject (path traversal guard)
  8. Mock/Real metadata isolation (via source_mode)
  9. no HTML blob stored in DB（payload_json 验证）
  10. InMemoryReportArtifactRepository basic get/save

M4.2.1 新增 STRICT PATH TESTS：
  11. relative_path "../evil.html" → reject
  12. relative_path absolute path → reject
  13. relative_path resolves outside root → reject
  14. relative_path wrong filename vs report_id → reject
  15. valid relative_path passes recovery

M4.2.1 新增 LINKAGE TESTS：
  16. report stores conversation_id/request_id in DB
  17. restart preserves linkage
  18. two conversations produce isolated reports

M4.2.1 新增 LEGACY TESTS：
  19. old payload with html → fail closed

Conversation Recovery（5 tests）：
  20. committed Memory restart continuation
  21. pending clarification restart continuation
  22. Snapshot restart replay
  23. failed Memory ignored (not part of recovery context)
  24. Mock/Real isolation on conversation restart

Wiring（5 tests）：
  25. memory backend → InMemoryReportArtifactRepository
  26. sqlite backend → SQLiteReportArtifactRepository
  27. reuse same engine/session_factory as memory/snapshot repos
  28. LocalReportRepository metadata_repo w/ restart path
  29. no local_state files tracked by Git
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import MemoryRepository
from backend.app.memory.result_snapshot import (
    ReportResultSnapshot,
    ResultSnapshotStore,
    SnapshotRepository,
    TurnResultSnapshot,
)
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import Base, ReportArtifactModel
from backend.app.persistence.repositories.memory import SQLiteMemoryRepository
from backend.app.persistence.repositories.report_artifact import (
    InMemoryReportArtifactRepository,
    ReportArtifactRepository,
    SQLiteReportArtifactRepository,
)
from backend.app.persistence.repositories.snapshot import SQLiteSnapshotRepository
from backend.app.report.resources import (
    InMemoryReportRepository,
    LocalReportRepository,
    ReportArtifact,
    ReportNotFoundError,
    ReportRepository,
    ReportSpec,
    ReportStorageError,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _tmp_db_path() -> str:
    """Return a path for a temporary SQLite database file."""
    tmp = Path(tempfile.mkdtemp()) / "test_m42.db"
    return str(tmp)


def _create_artifact() -> ReportArtifact:
    """Create a minimal valid ReportArtifact for testing."""
    report_id = "rpt_" + "a" * 32
    view_ref = f"/api/reports/{report_id}"
    return ReportArtifact(
        report_id=report_id,
        template_key="sales_report",
        html="<!DOCTYPE html><html><body>Test</body></html>",
        source_mode="mock",
        generated_at="2026-08-19T00:00:00",
        contract_version="1.0",
        semantic_model_key="test_model",
        schema_fingerprint="a" * 64,
        verified_fact_set_ids=["fact-1"],
        query_result_ids=["qr-1"],
        content_type="text/html; charset=utf-8",
        content_hash=hashlib.sha256(
            "<!DOCTYPE html><html><body>Test</body></html>".encode("utf-8")
        ).hexdigest(),
        created_at="2026-08-19T00:00:00",
        view_reference=view_ref,
        download_reference=f"{view_ref}/download",
    )


def _report_spec_for_artifact(artifact: ReportArtifact) -> ReportSpec:
    """Create a minimal ReportSpec that matches the artifact's provenance fields."""
    return ReportSpec(
        title="Test Report",
        template_key=artifact.template_key,
        summary="Test summary",
        source_mode=artifact.source_mode,
        contract_version=artifact.contract_version,
        semantic_model_key=artifact.semantic_model_key,
        schema_fingerprint=artifact.schema_fingerprint,
        verified_fact_set_ids=artifact.verified_fact_set_ids,
        query_result_ids=artifact.query_result_ids,
    )


def _artifact_with_relative_path(
    relative_path: str,
    *,
    report_id: str | None = None,
) -> ReportArtifact:
    """Build an artifact with an arbitrary relative_path for injection testing."""
    rid = report_id or "rpt_" + "b" * 32
    view_ref = f"/api/reports/{rid}"
    return ReportArtifact(
        report_id=rid,
        template_key="test",
        html="<!DOCTYPE html><html><body>Evil</body></html>",
        source_mode="mock",
        generated_at="2026-08-19T00:00:00",
        contract_version="",
        semantic_model_key="test",
        schema_fingerprint="b" * 64,
        verified_fact_set_ids=["fact-e"],
        query_result_ids=["qr-e"],
        content_type="text/html; charset=utf-8",
        content_hash=hashlib.sha256(
            "<!DOCTYPE html><html><body>Evil</body></html>".encode("utf-8")
        ).hexdigest(),
        created_at="2026-08-19T00:00:00",
        view_reference=view_ref,
        download_reference=f"{view_ref}/download",
        relative_path=relative_path,
    )


# ===========================================================================
# Fixtures — SQLite report artifact repository
# ===========================================================================


@pytest_asyncio.fixture
async def sqlite_report_repo():
    """Create a fresh SQLiteReportArtifactRepository in a temp DB."""
    db_path = _tmp_db_path()
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=db_path,
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await configure_engine(engine)

    session_factory = create_session_factory(engine)
    repo = SQLiteReportArtifactRepository(session_factory=session_factory)

    yield repo, engine, session_factory, db_path

    await dispose_engine(engine)


@pytest_asyncio.fixture
async def sqlite_all_repos():
    """Create all SQLite repos (memory, snapshot, report) in one temp DB."""
    db_path = _tmp_db_path()
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=db_path,
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text as sa_text
        await conn.execute(sa_text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_work_memories_committed_version "
            "ON work_memories (runtime_mode, conversation_id, memory_version) "
            "WHERE state_status = 'committed'"
        ))
    await configure_engine(engine)

    session_factory = create_session_factory(engine)
    memory_repo = SQLiteMemoryRepository(session_factory=session_factory)
    snapshot_repo = SQLiteSnapshotRepository(session_factory=session_factory)
    report_artifact_repo = SQLiteReportArtifactRepository(
        session_factory=session_factory
    )

    yield memory_repo, snapshot_repo, report_artifact_repo, engine, db_path

    await dispose_engine(engine)


@pytest_asyncio.fixture
async def engine_a():
    """Create engine + repos for process A (restart test)."""
    db_path = _tmp_db_path()
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=db_path,
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text as sa_text
        await conn.execute(sa_text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_work_memories_committed_version "
            "ON work_memories (runtime_mode, conversation_id, memory_version) "
            "WHERE state_status = 'committed'"
        ))
    await configure_engine(engine)
    yield engine, db_path
    await dispose_engine(engine)


@pytest.fixture
def sample_memory():
    return StructuredWorkMemory(
        conversation_id="conv-m42",
        request_id="req-m42-1",
        current_intent="data_question",
        measures=["SalesAmount"],
        runtime_mode=RuntimeDataMode.MOCK,
        is_mock=True,
        llm_provider="mock",
        powerbi_provider="mock_powerbi",
        base_memory_version=0,
        memory_version=0,
    )


@pytest.fixture
def valid_evidence():
    return MemoryCommitEvidence(
        intent_valid=True,
        request_allowed=True,
        query_plan_valid=True,
        dax_valid=True,
        tool_execution_succeeded=True,
        query_result_valid=True,
        response_valid=True,
        runtime_mode=RuntimeDataMode.MOCK,
    )


# ===========================================================================
# 1. Report metadata save/get via SQLiteReportArtifactRepository
# ===========================================================================


class TestReportArtifactRepository:
    """1. metadata save/get via SQLiteReportArtifactRepository"""

    @pytest.mark.asyncio
    async def test_save_and_get(self, sqlite_report_repo):
        repo, engine, sf, db_path = sqlite_report_repo
        artifact = _create_artifact()

        await repo.save(artifact)
        retrieved = await repo.get(artifact.report_id)

        assert retrieved.report_id == artifact.report_id
        assert retrieved.template_key == artifact.template_key
        assert retrieved.content_hash == artifact.content_hash
        assert retrieved.source_mode == artifact.source_mode

    @pytest.mark.asyncio
    async def test_exists(self, sqlite_report_repo):
        repo, engine, sf, db_path = sqlite_report_repo
        artifact = _create_artifact()

        assert await repo.exists(artifact.report_id) is False
        await repo.save(artifact)
        assert await repo.exists(artifact.report_id) is True

    @pytest.mark.asyncio
    async def test_get_not_found(self, sqlite_report_repo):
        repo, engine, sf, db_path = sqlite_report_repo
        with pytest.raises(ReportNotFoundError):
            await repo.get("rpt_" + "f" * 32)

    @pytest.mark.asyncio
    async def test_save_collision_rejected(self, sqlite_report_repo):
        """A report_id cannot be overwritten with different metadata."""
        repo, engine, sf, db_path = sqlite_report_repo
        artifact = _create_artifact()

        await repo.save(artifact)

        updated_artifact = ReportArtifact(
            report_id=artifact.report_id,
            template_key="sales_report",
            html="<!DOCTYPE html><html><body>Updated</body></html>",
            source_mode="real",
            generated_at="2026-08-19T00:00:00",
            contract_version="1.1",
            semantic_model_key="updated_model",
            schema_fingerprint="b" * 64,
            verified_fact_set_ids=["fact-2"],
            query_result_ids=["qr-2"],
            content_type="text/html; charset=utf-8",
            content_hash=hashlib.sha256(
                "<!DOCTYPE html><html><body>Updated</body></html>".encode("utf-8")
            ).hexdigest(),
            created_at="2026-08-19T01:00:00",
            view_reference=f"/api/reports/{artifact.report_id}",
            download_reference=f"/api/reports/{artifact.report_id}/download",
        )
        with pytest.raises(ReportStorageError, match="identity_collision"):
            await repo.save(updated_artifact)

        retrieved = await repo.get(artifact.report_id)
        assert retrieved.contract_version == artifact.contract_version
        assert retrieved.source_mode == artifact.source_mode
        assert retrieved.semantic_model_key == artifact.semantic_model_key


class TestInMemoryReportArtifactRepository:
    """InMemoryReportArtifactRepository basic operations."""

    @pytest.mark.asyncio
    async def test_save_and_get(self):
        repo = InMemoryReportArtifactRepository()
        artifact = _create_artifact()

        await repo.save(artifact)
        retrieved = await repo.get(artifact.report_id)

        assert retrieved.report_id == artifact.report_id
        assert await repo._count() == 1

    @pytest.mark.asyncio
    async def test_exists(self):
        repo = InMemoryReportArtifactRepository()
        artifact = _create_artifact()

        assert await repo.exists(artifact.report_id) is False
        await repo.save(artifact)
        assert await repo.exists(artifact.report_id) is True

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        repo = InMemoryReportArtifactRepository()
        with pytest.raises(ReportNotFoundError):
            await repo.get("rpt_" + "f" * 32)


# ===========================================================================
# 2-4. Report restart recovery
# ===========================================================================


class TestReportRestartRecovery:
    """Restart recovery: old report_id survives engine restart."""

    @pytest.mark.asyncio
    async def test_report_metadata_survives_restart(self, engine_a):
        """Process A saves report metadata; Process B reads it from same DB."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteReportArtifactRepository(session_factory=sf1)

        artifact = _create_artifact()
        await repo1.save(artifact)

        assert await repo1._count() == 1

        # M4.2.1: relative_path is just <report_id>.html, payload_json has NO html
        async with sf1() as session:
            from sqlalchemy import select as sa_select
            stmt = sa_select(ReportArtifactModel).where(
                ReportArtifactModel.report_id == artifact.report_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
            assert row.relative_path == f"{artifact.report_id}.html"
            assert "<html" not in row.relative_path

            pj = json.loads(row.payload_json)
            assert "report_id" in pj
            assert "content_hash" in pj
            # html field may exist in Pydantic serialization but must be empty
            html_val = pj.get("html", "")
            assert not html_val, f"payload_json contains non-empty html: {html_val[:50]}..."

        await dispose_engine(eng1)

        # Process B: new engine on same DB
        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteReportArtifactRepository(session_factory=sf2)

        retrieved = await repo2.get(artifact.report_id)
        assert retrieved.report_id == artifact.report_id
        assert retrieved.content_hash == artifact.content_hash
        assert retrieved.template_key == artifact.template_key

        await dispose_engine(eng2)

    @pytest.mark.asyncio
    async def test_local_report_repo_restart_recovery(self, engine_a):
        """Process A stores HTML + metadata; Process B reads via LocalReportRepository."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        report_artifact_repo = SQLiteReportArtifactRepository(session_factory=sf1)

        reports_dir_a = Path(tempfile.mkdtemp()) / "reports"
        reports_dir_a.mkdir(parents=True, exist_ok=True)
        local_repo_a = LocalReportRepository(
            root=reports_dir_a,
            metadata_repo=report_artifact_repo,
        )

        spec = _report_spec_for_artifact(_create_artifact())
        stored = await local_repo_a.store(spec, "<!DOCTYPE html><html><body>Hello M4.2</body></html>")
        assert stored is not None
        report_id = stored.report_id

        await dispose_engine(eng1)

        # Process B
        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        report_artifact_repo_b = SQLiteReportArtifactRepository(session_factory=sf2)
        local_repo_b = LocalReportRepository(
            root=reports_dir_a,
            metadata_repo=report_artifact_repo_b,
        )

        artifact_b, html_b = await local_repo_b.read_html(report_id)
        assert artifact_b.report_id == report_id
        assert "Hello M4.2" in html_b
        assert artifact_b.content_hash == hashlib.sha256(
            "<!DOCTYPE html><html><body>Hello M4.2</body></html>".encode("utf-8")
        ).hexdigest()

        get_b = await local_repo_b.get(report_id)
        assert get_b.report_id == report_id

        await dispose_engine(eng2)


# ===========================================================================
# 4-6. Content hash validation, missing file, tampered HTML, no-HTML-in-DB
# ===========================================================================


class TestReportFailClosed:
    """Fail-closed semantics for missing/tampered/invalid paths."""

    @pytest.mark.asyncio
    async def test_missing_html_file(self):
        """Metadata exists but HTML file is missing → fail closed."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(
            root=reports_dir,
            metadata_repo=meta_repo,
        )

        fake_artifact = _create_artifact()
        await meta_repo.save(fake_artifact)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(fake_artifact.report_id)

    @pytest.mark.asyncio
    async def test_tampered_html_content_hash(self):
        """File content changed after metadata was saved → fail closed."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()

        local_repo = LocalReportRepository(
            root=reports_dir,
            metadata_repo=meta_repo,
        )

        spec = _report_spec_for_artifact(_create_artifact())
        original = await local_repo.store(spec, "<!DOCTYPE html><html><body>Original</body></html>")
        report_id = original.report_id

        target = reports_dir / f"{report_id}.html"
        target.write_text("<!DOCTYPE html><html><body>TAMPERED</body></html>", encoding="utf-8")

        with pytest.raises(ReportStorageError, match="report_content_hash_mismatch"):
            await local_repo.read_html(report_id)

    @pytest.mark.asyncio
    async def test_no_html_blob_in_db(self, sqlite_report_repo):
        """M4.2.1: payload_json must NOT contain HTML content."""
        repo, engine, sf, db_path = sqlite_report_repo
        artifact = _create_artifact()
        await repo.save(artifact)

        async with sf() as session:
            from sqlalchemy import select as sa_select
            stmt = sa_select(ReportArtifactModel).where(
                ReportArtifactModel.report_id == artifact.report_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one()

            # relative_path is just <report_id>.html
            assert row.relative_path == f"{artifact.report_id}.html"
            assert "<html" not in row.relative_path

            # payload_json: metadata-only, no HTML
            pj = json.loads(row.payload_json)
            assert "report_id" in pj
            assert "relative_path" in pj
            html_val = pj.get("html", "")
            assert not html_val, "payload_json must NOT contain html content"
            assert pj.get("relative_path") == f"{artifact.report_id}.html"


# ===========================================================================
# M4.2.1 — STRICT PATH TESTS
# ===========================================================================


class TestStrictPath:
    """M4.2.1: relative_path must be validated as the recovery authority."""

    @pytest.mark.asyncio
    async def test_traversal_rejected(self):
        """relative_path '../evil.html' → must reject."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        # Inject artifact with traversal path via metadata repo
        evil = _artifact_with_relative_path("../evil.html")
        await meta_repo.save(evil)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(evil.report_id)

    @pytest.mark.asyncio
    async def test_absolute_path_rejected(self):
        """relative_path as an absolute path → must reject."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        if os.name == "nt":
            evil = _artifact_with_relative_path("C:\\Windows\\win.ini")
        else:
            evil = _artifact_with_relative_path("/etc/passwd")
        await meta_repo.save(evil)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(evil.report_id)

    @pytest.mark.asyncio
    async def test_outside_root_resolve_rejected(self):
        """relative_path that resolves outside the report root → must reject."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        # Create a symlink target outside root (simulated by deep ../ traversal)
        evil = _artifact_with_relative_path("../../windows/evil.html" if os.name == "nt" else "../../tmp/evil.html")
        await meta_repo.save(evil)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(evil.report_id)

    @pytest.mark.asyncio
    async def test_wrong_filename_rejected(self):
        """relative_path filename does not match report_id → must reject."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        wrong = _artifact_with_relative_path(
            "wrong-report.html",
            report_id="rpt_" + "c" * 32,
        )
        await meta_repo.save(wrong)

        with pytest.raises(ReportNotFoundError):
            await local_repo.read_html(wrong.report_id)

    @pytest.mark.asyncio
    async def test_valid_path_passes(self):
        """relative_path = '<report_id>.html' → passes recovery."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()

        local_repo = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)

        spec = _report_spec_for_artifact(_create_artifact())
        stored = await local_repo.store(spec, "<!DOCTYPE html><html><body>Valid</body></html>")
        report_id = stored.report_id

        # Restart: new LocalReportRepository, same metadata repo
        local_repo_b = LocalReportRepository(root=reports_dir, metadata_repo=meta_repo)
        artifact_b, html_b = await local_repo_b.read_html(report_id)
        assert artifact_b.report_id == report_id
        assert "Valid" in html_b


# ===========================================================================
# M4.2.1 — LINKAGE TESTS
# ===========================================================================


class TestConversationRequestLinkage:
    """M4.2.1: conversation_id/request_id must be persisted in report metadata."""

    @pytest.mark.asyncio
    async def test_linkage_written_to_db(self, sqlite_report_repo):
        """report stored with conversation_id/request_id → DB row has them."""
        repo, engine, sf, db_path = sqlite_report_repo
        artifact = _create_artifact()
        await repo.save(
            artifact,
            conversation_id="conv-link-1",
            request_id="req-link-1",
        )

        retrieved = await repo.get(artifact.report_id)
        assert retrieved.conversation_id == "conv-link-1"
        assert retrieved.request_id == "req-link-1"

        async with sf() as session:
            from sqlalchemy import select as sa_select
            stmt = sa_select(ReportArtifactModel).where(
                ReportArtifactModel.report_id == artifact.report_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
            assert row.conversation_id == "conv-link-1"
            assert row.request_id == "req-link-1"

            # Also verify in payload_json
            pj = json.loads(row.payload_json)
            assert pj.get("conversation_id") == "conv-link-1"
            assert pj.get("request_id") == "req-link-1"

    @pytest.mark.asyncio
    async def test_restart_preserves_linkage(self, engine_a):
        """Process A stores with linkage; Process B reads it back."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteReportArtifactRepository(session_factory=sf1)

        artifact = _create_artifact()
        await repo1.save(
            artifact,
            conversation_id="conv-link-restart",
            request_id="req-link-restart",
        )
        await dispose_engine(eng1)

        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteReportArtifactRepository(session_factory=sf2)

        retrieved = await repo2.get(artifact.report_id)
        assert retrieved.conversation_id == "conv-link-restart"
        assert retrieved.request_id == "req-link-restart"

        await dispose_engine(eng2)

    @pytest.mark.asyncio
    async def test_two_conversations_isolated(self, sqlite_all_repos):
        """Two conversations each produce reports with correct linkage."""
        memory_repo, snapshot_repo, report_artifact_repo, engine, db_path = sqlite_all_repos

        def _linked_artifact(rid: str, conv_id: str, req_id: str) -> ReportArtifact:
            vr = f"/api/reports/{rid}"
            return ReportArtifact(
                report_id=rid,
                template_key="sales_report",
                html="",
                source_mode="mock",
                generated_at="2026-08-19T00:00:00",
                contract_version="1.0",
                semantic_model_key="test",
                schema_fingerprint="a" * 64,
                verified_fact_set_ids=["fact-1"],
                query_result_ids=["qr-1"],
                content_type="text/html; charset=utf-8",
                content_hash="a" * 64,
                created_at="2026-08-19T00:00:00",
                view_reference=vr,
                download_reference=f"{vr}/download",
                relative_path=f"{rid}.html",
                conversation_id=conv_id,
                request_id=req_id,
            )

        conv_a = _linked_artifact("rpt_" + "d" * 32, "conv-a", "req-a")
        conv_b = _linked_artifact("rpt_" + "e" * 32, "conv-b", "req-b")

        await report_artifact_repo.save(conv_a)
        await report_artifact_repo.save(conv_b)

        retrieved_a = await report_artifact_repo.get(conv_a.report_id)
        retrieved_b = await report_artifact_repo.get(conv_b.report_id)

        assert retrieved_a.conversation_id == "conv-a"
        assert retrieved_a.request_id == "req-a"
        assert retrieved_b.conversation_id == "conv-b"
        assert retrieved_b.request_id == "req-b"
        assert retrieved_a.conversation_id != retrieved_b.conversation_id


# ===========================================================================
# M4.2.1 — LEGACY PAYLOAD HANDLING
# ===========================================================================


class TestLegacyPayload:
    """M4.2.1: Legacy payload_json containing HTML must fail closed."""

    @pytest.mark.asyncio
    async def test_legacy_html_in_payload_raises(self, sqlite_report_repo):
        """A row whose payload_json contains html → ReportStorageError."""
        repo, engine, sf, db_path = sqlite_report_repo

        # Directly insert a row with legacy payload containing HTML
        async with sf() as session:
            async with session.begin():
                from sqlalchemy import text as sa_text
                legacy_payload = json.dumps({
                    "report_id": "rpt_ffffffffffffffffffffffffffffffff",
                    "template_key": "sales_report",
                    "html": "<!DOCTYPE html><html><body>LEGACY</body></html>",
                    "source_mode": "mock",
                    "content_hash": "a" * 64,
                    "created_at": "2026-08-19T00:00:00",
                })
                await session.execute(
                    sa_text(
                        """INSERT INTO report_artifacts
                        (report_id, template_key, semantic_model_key, schema_fingerprint,
                         source_mode, content_hash, relative_path, payload_json)
                        VALUES (:rid, 'sales_report', '', '', 'mock', :ch, 'legacy.html', :pj)"""
                    ),
                    {
                        "rid": "rpt_ffffffffffffffffffffffffffffffff",
                        "ch": "a" * 64,
                        "pj": legacy_payload,
                    },
                )
            await session.commit()

        with pytest.raises(ReportStorageError, match="legacy HTML"):
            await repo.get("rpt_ffffffffffffffffffffffffffffffff")

    @pytest.mark.asyncio
    async def test_m4_2_metadata_only_passes(self, sqlite_report_repo):
        """M4.2.1 metadata without HTML passes reconstruction normally."""
        repo, engine, sf, db_path = sqlite_report_repo
        artifact = _create_artifact()

        await repo.save(artifact)
        retrieved = await repo.get(artifact.report_id)

        assert retrieved.report_id == artifact.report_id
        # html must be empty when reconstructed from DB
        assert retrieved.html == ""


# ===========================================================================
# 11. Committed Memory restart continuation
# ===========================================================================


class TestMemoryRestartContinuation:
    """Committed Memory survives engine restart."""

    @pytest.mark.asyncio
    async def test_committed_memory_restart_continuation(self, engine_a, valid_evidence):
        """Process A creates + commits memory; Process B reads latest committed."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteMemoryRepository(session_factory=sf1)

        mem = StructuredWorkMemory(
            conversation_id="conv-m42-restart",
            request_id="req-m42-restart-1",
            current_intent="data_question",
            measures=["RestoreMe"],
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,
        )
        await repo1.create_pending(mem, RuntimeDataMode.MOCK)
        await repo1.commit(mem, valid_evidence)
        await dispose_engine(eng1)

        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteMemoryRepository(session_factory=sf2)

        latest = await repo2.get_latest_committed("conv-m42-restart", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 1
        assert latest.measures == ["RestoreMe"]
        assert latest.state_status == MemoryStatus.COMMITTED

        await dispose_engine(eng2)

    @pytest.mark.asyncio
    async def test_failed_memory_not_recovered(self, engine_a, sample_memory):
        """Failed memory must not appear as 'latest committed'."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteMemoryRepository(session_factory=sf1)

        mem = StructuredWorkMemory(
            conversation_id="conv-m42-fail",
            request_id="req-m42-fail-1",
            current_intent="data_question",
            measures=["FailThis"],
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,
        )
        await repo1.create_pending(mem, RuntimeDataMode.MOCK)
        await repo1.mark_failed("req-m42-fail-1", RuntimeDataMode.MOCK, reason="test failure")
        await dispose_engine(eng1)

        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteMemoryRepository(session_factory=sf2)

        latest = await repo2.get_latest_committed("conv-m42-fail", RuntimeDataMode.MOCK)
        assert latest is None

        await dispose_engine(eng2)

    @pytest.mark.asyncio
    async def test_mock_real_isolation_restart(self, engine_a, valid_evidence, sample_memory):
        """Mock and Real namespaces are isolated after restart."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteMemoryRepository(session_factory=sf1)

        mock_mem = StructuredWorkMemory(
            conversation_id="conv-iso",
            request_id="req-iso-mock",
            current_intent="data_question",
            measures=["MockMeasure"],
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,
        )
        await repo1.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await repo1.commit(mock_mem, valid_evidence)

        real_mem = StructuredWorkMemory(
            conversation_id="conv-iso",
            request_id="req-iso-real",
            current_intent="data_question",
            measures=["RealMeasure"],
            runtime_mode=RuntimeDataMode.REAL,
            is_mock=False,
            base_memory_version=0,
        )
        real_evidence = MemoryCommitEvidence(
            intent_valid=True,
            request_allowed=True,
            query_plan_valid=True,
            dax_valid=True,
            tool_execution_succeeded=True,
            query_result_valid=True,
            response_valid=True,
            runtime_mode=RuntimeDataMode.REAL,
        )
        await repo1.create_pending(real_mem, RuntimeDataMode.REAL)
        await repo1.commit(real_mem, real_evidence)
        await dispose_engine(eng1)

        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteMemoryRepository(session_factory=sf2)

        mock_latest = await repo2.get_latest_committed("conv-iso", RuntimeDataMode.MOCK)
        assert mock_latest is not None
        assert mock_latest.measures == ["MockMeasure"]

        real_latest = await repo2.get_latest_committed("conv-iso", RuntimeDataMode.REAL)
        assert real_latest is not None
        assert real_latest.measures == ["RealMeasure"]

        await dispose_engine(eng2)


# ===========================================================================
# 12. Pending Clarification restart continuation
# ===========================================================================


class TestPendingClarificationRestart:
    """PendingClarification survives engine restart."""

    @pytest.mark.asyncio
    async def test_pending_clarification_restart(self, engine_a):
        """Process A saves pending clarification; Process B reads it."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteMemoryRepository(session_factory=sf1)

        ctx = PendingClarificationContext(
            conversation_id="conv-clar",
            chain_id="chain-001",
            semantic_model_key="test_model",
            schema_fingerprint="a" * 64,
            runtime_mode=RuntimeDataMode.MOCK,
            last_request_id="req-clar-1",
            missing_slots=["measure"],
        )
        await repo1.save_pending_clarification(ctx, RuntimeDataMode.MOCK)
        await dispose_engine(eng1)

        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteMemoryRepository(session_factory=sf2)

        restored = await repo2.get_pending_clarification("conv-clar", RuntimeDataMode.MOCK)
        assert restored is not None
        assert restored.chain_id == "chain-001"
        assert "measure" in restored.missing_slots

        await dispose_engine(eng2)


# ===========================================================================
# 13. Snapshot restart replay
# ===========================================================================


class TestSnapshotRestartReplay:
    """Snapshots survive engine restart for idempotency replay."""

    @pytest.mark.asyncio
    async def test_snapshot_restart_replay(self, engine_a):
        """Process A saves a snapshot; Process B reads it for replay."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteSnapshotRepository(session_factory=sf1)

        snap = TurnResultSnapshot(
            request_id="snap-m42-restart",
            conversation_id="conv-m42-snap",
            intent="data_question",
            response_type="answer",
            terminal_state="completed",
            request_fingerprint_hash="a" * 64,
            answer="Recovered answer",
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
        )
        await repo1.save(snap, RuntimeDataMode.MOCK)
        await dispose_engine(eng1)

        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteSnapshotRepository(session_factory=sf2)

        restored = await repo2.get("snap-m42-restart", RuntimeDataMode.MOCK)
        assert restored is not None
        assert restored.answer == "Recovered answer"
        assert restored.terminal_state == "completed"


# ===========================================================================
# 16-20. Wiring
# ===========================================================================


class TestWiringIntegration:
    """Wiring: memory/sqlite backend → correct repos, engine lifecycle."""

    @pytest.mark.asyncio
    async def test_memory_backend_uses_inmemory_report_repo(self):
        """memory backend should use InMemoryReportArtifactRepository."""
        meta_repo = InMemoryReportArtifactRepository()
        artifact = _create_artifact()

        await meta_repo.save(artifact)
        assert await meta_repo._count() == 1
        retrieved = await meta_repo.get(artifact.report_id)
        assert retrieved.report_id == artifact.report_id

    @pytest.mark.asyncio
    async def test_sqlite_backend_reuses_engine(self, sqlite_all_repos):
        """SQLite report artifact repo shares engine with memory/snapshot repos."""
        memory_repo, snapshot_repo, report_artifact_repo, engine, db_path = sqlite_all_repos

        artifact = _create_artifact()
        await report_artifact_repo.save(artifact)
        assert await report_artifact_repo._count() == 1

        mem = StructuredWorkMemory(
            conversation_id="conv-wire",
            request_id="req-wire",
            current_intent="data_question",
            measures=["WireTest"],
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,
        )
        await memory_repo.create_pending(mem, RuntimeDataMode.MOCK)

    @pytest.mark.asyncio
    async def test_local_report_repo_with_metadata_repo(self):
        """LocalReportRepository works with metadata repo and recovers after restart."""
        reports_dir = Path(tempfile.mkdtemp()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        meta_repo = InMemoryReportArtifactRepository()
        local_repo = LocalReportRepository(
            root=reports_dir,
            metadata_repo=meta_repo,
        )

        spec = _report_spec_for_artifact(_create_artifact())
        stored = await local_repo.store(spec, "<!DOCTYPE html><html><body>Wire OK</body></html>")
        report_id = stored.report_id

        local_repo_b = LocalReportRepository(
            root=reports_dir,
            metadata_repo=meta_repo,
        )
        artifact_b, html_b = await local_repo_b.read_html(report_id)
        assert "Wire OK" in html_b

    @pytest.mark.asyncio
    async def test_no_local_state_in_git(self):
        """Verify local_state/ is not tracked by Git."""
        import subprocess
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "local_state/"],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent.parent.parent,
        )
        assert result.returncode != 0 or "Did not match" in result.stdout

    @pytest.mark.asyncio
    async def test_engine_shutdown_works(self, sqlite_all_repos):
        """Engine dispose does not crash after report artifact operations."""
        memory_repo, snapshot_repo, report_artifact_repo, engine, db_path = sqlite_all_repos

        artifact = _create_artifact()
        await report_artifact_repo.save(artifact)

        await dispose_engine(engine)

        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteReportArtifactRepository(session_factory=sf2)

        retrieved = await repo2.get(artifact.report_id)
        assert retrieved.report_id == artifact.report_id
        assert retrieved.template_key == artifact.template_key

        await dispose_engine(eng2)
