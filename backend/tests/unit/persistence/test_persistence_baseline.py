"""M4.0 persistence infrastructure tests.

Covers
------
1. SQLite engine creation (sync)
2. Alembic migration upgrade head (sync)
3. SQLite file created under local_state (sync)
4. .db gitignored (sync)
5. MemoryRepository ABC accepts InMemoryMemoryRepository (sync)
6. SnapshotRepository ABC accepts ResultSnapshotStore (sync)
7. TurnPipeline accepts MemoryRepository (sync)
8. JSON serialization roundtrip (sync)
9. JSON corruption fail-closed (sync)
10. UNIQUE(runtime_mode, request_id) constraint on work_memories (async)
11. UNIQUE(runtime_mode, request_id) constraint on result_snapshots (async)
12. UNIQUE(runtime_mode, conversation_id) on pending_clarifications (async)
13. foreign_keys ON via configure_engine (async)
14. WAL / bounded busy_timeout via configure_engine (async)
15. FK constraint enforcement (async)
16. Settings persistence fields (sync)
17. Snapshot serialization roundtrip (sync)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import sqlite3

from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.memory.models import (
    MemoryStatus,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryRepository,
)
from backend.app.memory.result_snapshot import (
    ResultSnapshotStore,
    SnapshotRepository,
    TurnResultSnapshot,
)
from backend.app.persistence.database import (
    build_sqlite_url,
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import (
    PendingClarificationModel,
    ResultSnapshotModel,
    WorkMemoryModel,
    ConversationModel,
    Base,
)
from backend.app.persistence.serialization import (
    domain_to_json,
    json_to_domain,
    safe_json_loads,
)
from backend.app.application.turn_pipeline import TurnPipeline
from backend.app.harness.models import HarnessConfig


# ===========================================================================
# Sync helpers
# ===========================================================================


def _tmp_db_path() -> str:
    tmp = Path(tempfile.mkdtemp()) / "test_persistence.db"
    return str(tmp)


def _sqlite_settings(tmp_db_path: str = None) -> Settings:
    if tmp_db_path is None:
        tmp_db_path = _tmp_db_path()
    return Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(tmp_db_path),
    )


# ===========================================================================
# 1. SQLite engine creation and disposal (sync)
# ===========================================================================


class TestEngineLifecycle:
    """Engine creation and disposal — deterministic behavior."""

    def test_engine_can_be_created(self):
        engine = create_engine(_sqlite_settings(), echo=False)
        assert engine is not None
        import asyncio
        asyncio.run(dispose_engine(engine))

    def test_engine_can_be_disposed(self):
        engine = create_engine(_sqlite_settings(), echo=False)
        import asyncio
        asyncio.run(dispose_engine(engine))

    def test_dispose_none_is_safe(self):
        import asyncio
        asyncio.run(dispose_engine(None))

    def test_engine_url_built_deterministically(self):
        tmp_db_path = _tmp_db_path()
        settings = _sqlite_settings(tmp_db_path)
        url = build_sqlite_url(settings)
        assert url.startswith("sqlite+aiosqlite:///")
        resolved = Path(tmp_db_path).resolve().as_posix()
        assert resolved in url


# ===========================================================================
# 2. Alembic migration upgrade head (sync)
# ===========================================================================


class TestAlembicMigration:

    def test_migration_upgrade_head(self):
        """Run alembic upgrade head from scratch in a temp dir."""
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()

        # Build a temp alembic.ini pointing at our test DB
        alembic_ini_content = f"""\
[alembic]
script_location = {project_root.as_posix()}/backend/alembic
prepend_sys_path = {project_root.as_posix()}
sqlalchemy.url = sqlite+aiosqlite:///{posix_path}

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

        ini_dir = Path(tempfile.mkdtemp())
        ini_file = ini_dir / "alembic.ini"
        ini_file.write_text(alembic_ini_content, encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root)
        # Remove any existing ALEMBIC_ overrides
        for key in list(env.keys()):
            if key.startswith("ALEMBIC_"):
                del env[key]

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ini_file),
             "upgrade", "head"],
            capture_output=True, text=True,
            cwd=ini_dir, env=env,
        )
        if result.returncode != 0:
            pytest.fail(
                f"alembic upgrade head failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

        assert os.path.isfile(tmp_db_path), f"DB file not created at {tmp_db_path}"

        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "alembic_version", "conversations", "work_memories",
            "pending_clarifications", "result_snapshots", "report_artifacts",
        }
        missing = expected - tables
        assert not missing, f"Tables missing after migration: {missing}"

        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()[0]
        conn.close()
        assert version is not None and len(version) > 0


# ===========================================================================
# 3. SQLite file created under local_state (sync)
# ===========================================================================


class TestDatabasePath:

    def test_file_created_in_local_state(self):
        tmp_db_path = _tmp_db_path()
        assert not os.path.isfile(tmp_db_path)

        settings = _sqlite_settings(tmp_db_path)
        import asyncio
        engine = create_engine(settings, echo=False)

        async def connect_and_dispose():
            async with engine.begin():
                pass
            await dispose_engine(engine)

        asyncio.run(connect_and_dispose())
        assert os.path.isfile(tmp_db_path)

    def test_default_path_under_local_state(self):
        settings = Settings()
        assert settings.persistence_database_path.startswith("local_state/")


# ===========================================================================
# 4. .db gitignored (sync)
# ===========================================================================


class TestGitIgnore:

    def test_db_not_tracked(self):
        gitignore = Path(".gitignore").read_text(encoding="utf-8")
        assert "*.db" in gitignore
        assert "local_state/" in gitignore or "local_state" in gitignore
        assert "*.sqlite" in gitignore


# ===========================================================================
# 5-6. Repository ABC (sync)
# ===========================================================================


class TestRepositoryAbstraction:

    def test_memory_repository_abc(self):
        repo: MemoryRepository = InMemoryMemoryRepository()
        assert repo is not None

    def test_snapshot_repository_abc(self):
        store: SnapshotRepository = ResultSnapshotStore()
        assert store is not None


# ===========================================================================
# 7. TurnPipeline type check (sync)
# ===========================================================================


class TestTurnPipelineType:

    def test_turn_pipeline_accepts_memory_repository(self):
        config = HarnessConfig()
        repo: MemoryRepository = InMemoryMemoryRepository()
        store: SnapshotRepository = ResultSnapshotStore()
        pipeline = TurnPipeline(config=config, memory_repo=repo, snapshot_store=store)
        assert pipeline.memory_repo is repo
        assert pipeline.snapshot_store is store

    def test_turn_pipeline_defaults_snapshot_store(self):
        config = HarnessConfig()
        repo: MemoryRepository = InMemoryMemoryRepository()
        pipeline = TurnPipeline(config=config, memory_repo=repo)
        assert isinstance(pipeline.snapshot_store, ResultSnapshotStore)


# ===========================================================================
# 8-9. JSON serialization (sync)
# ===========================================================================


class TestSerializationRoundtrip:

    def test_domain_to_json_and_back(self):
        memory = StructuredWorkMemory(
            request_id="test-req-001",
            conversation_id="test-conv-001",
            semantic_model_key="local_desktop_model",
            current_intent="data_question",
            analysis_goal="test roundtrip",
            state_status=MemoryStatus.PENDING,
            runtime_mode=RuntimeDataMode.MOCK,
        )
        json_str = domain_to_json(memory)
        restored = json_to_domain(StructuredWorkMemory, json_str)
        assert restored.request_id == memory.request_id
        assert restored.conversation_id == memory.conversation_id
        assert restored.semantic_model_key == memory.semantic_model_key
        assert restored.state_status == MemoryStatus.PENDING
        assert restored.runtime_mode == RuntimeDataMode.MOCK

    def test_domain_to_json_contains_no_pickle(self):
        memory = StructuredWorkMemory(
            request_id="test-no-pickle",
            conversation_id="test-conv-pickle",
        )
        json_str = domain_to_json(memory)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert parsed["request_id"] == "test-no-pickle"

    def test_safe_json_loads_none(self):
        assert safe_json_loads(None) is None
        assert safe_json_loads("") is None

    def test_safe_json_loads_invalid_raises(self):
        with pytest.raises(json.JSONDecodeError):
            safe_json_loads("not valid json")

    def test_corrupted_json_raises_validation_error(self):
        with pytest.raises((json.JSONDecodeError, Exception)):
            json_to_domain(StructuredWorkMemory, "this is not json at all")

    def test_turn_result_snapshot_to_json_and_back(self):
        snapshot = TurnResultSnapshot(
            request_id="snap-req-001",
            conversation_id="snap-conv-001",
            intent="data_question",
            response_type="answer",
            terminal_state="completed",
            answer="This is a test answer.",
            request_fingerprint_hash="f" * 64,
        )
        json_str = domain_to_json(snapshot)
        restored = json_to_domain(TurnResultSnapshot, json_str)
        assert restored.request_id == snapshot.request_id
        assert restored.answer == snapshot.answer
        assert restored.response_type == "answer"


# ===========================================================================
# 10-15. Async DB tests
# ===========================================================================


class TestAsyncDatabaseConstraints:

    @pytest.fixture
    async def db_engine(self):
        """Create engine + tables for one async test method."""
        tmp_db_path = _tmp_db_path()
        settings = _sqlite_settings(tmp_db_path)
        engine = create_engine(settings, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await configure_engine(engine)
        yield engine
        await dispose_engine(engine)

    @pytest.fixture
    async def db_conversation(self, db_engine):
        """Insert one conversation for FK tests."""
        factory = create_session_factory(db_engine)
        async with factory() as session:
            conv = ConversationModel(
                conversation_id="test-conv-async",
                runtime_mode="mock",
            )
            session.add(conv)
            await session.commit()

    async def _create_conversation(self, db_engine, conv_id: str):
        factory = create_session_factory(db_engine)
        async with factory() as session:
            conv = ConversationModel(
                conversation_id=conv_id,
                runtime_mode="mock",
            )
            session.add(conv)
            await session.commit()

    @pytest.mark.asyncio
    async def test_unique_runtime_request_on_work_memories(self, db_engine):
        await self._create_conversation(db_engine, "test-unique-conv-wm")
        factory = create_session_factory(db_engine)

        async with factory() as session:
            wm1 = WorkMemoryModel(
                request_id="unique-req-wm",
                conversation_id="test-unique-conv-wm",
                runtime_mode="mock",
                state_status="pending",
                payload_json='{"test": true}',
            )
            session.add(wm1)
            await session.commit()

        async with factory() as session:
            wm2 = WorkMemoryModel(
                request_id="unique-req-wm",
                conversation_id="test-unique-conv-wm",
                runtime_mode="mock",
                state_status="pending",
                payload_json='{"test": true}',
            )
            session.add(wm2)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            assert "UNIQUE" in str(exc_info.value).upper() or "unique" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_unique_runtime_request_on_result_snapshots(self, db_engine):
        await self._create_conversation(db_engine, "test-unique-conv-rs")
        factory = create_session_factory(db_engine)

        async with factory() as session:
            rs1 = ResultSnapshotModel(
                request_id="snap-unique-001",
                runtime_mode="mock",
                conversation_id="test-unique-conv-rs",
                request_fingerprint_hash="a" * 64,
                terminal_state="completed",
                response_type="answer",
                payload_json='{"test": true}',
            )
            session.add(rs1)
            await session.commit()

        async with factory() as session:
            rs2 = ResultSnapshotModel(
                request_id="snap-unique-001",
                runtime_mode="mock",
                conversation_id="test-unique-conv-rs",
                request_fingerprint_hash="b" * 64,
                terminal_state="completed",
                response_type="answer",
                payload_json='{"test": true}',
            )
            session.add(rs2)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            assert "UNIQUE" in str(exc_info.value).upper() or "unique" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_unique_runtime_conversation_on_pending(self, db_engine):
        factory = create_session_factory(db_engine)

        async with factory() as session:
            pc1 = PendingClarificationModel(
                conversation_id="test-pc-conv-async",
                runtime_mode="mock",
                chain_id="chain-001",
                semantic_model_key="model_key",
                schema_fingerprint="a" * 64,
                payload_json='{"test": true}',
            )
            session.add(pc1)
            await session.commit()

        async with factory() as session:
            pc2 = PendingClarificationModel(
                conversation_id="test-pc-conv-async",
                runtime_mode="mock",
                chain_id="chain-002",
                semantic_model_key="model_key",
                schema_fingerprint="b" * 64,
                payload_json='{"test": true}',
            )
            session.add(pc2)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            assert "UNIQUE" in str(exc_info.value).upper() or "unique" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_configure_engine_sets_pragmas(self, db_engine):
        """Ensure configure_engine sets correct PRAGMAs."""
        async with db_engine.connect() as conn:
            def check_fk(sync_conn):
                row = sync_conn.exec_driver_sql("PRAGMA foreign_keys;").fetchone()
                assert row[0] == 1, f"foreign_keys should be 1, got {row[0]}"
            await conn.run_sync(check_fk)

            def check_journal(sync_conn):
                row = sync_conn.exec_driver_sql("PRAGMA journal_mode;").fetchone()
                assert row[0].upper() == "WAL", f"journal_mode should be WAL, got {row[0]}"
            await conn.run_sync(check_journal)

            def check_timeout(sync_conn):
                row = sync_conn.exec_driver_sql("PRAGMA busy_timeout;").fetchone()
                assert row[0] == 5000, f"busy_timeout should be 5000, got {row[0]}"
            await conn.run_sync(check_timeout)

    @pytest.mark.asyncio
    async def test_foreign_key_violation_rejected(self, db_engine):
        """Inserting work_memory with non-existent conversation_id should fail."""
        factory = create_session_factory(db_engine)
        async with factory() as session:
            wm = WorkMemoryModel(
                request_id="fk-test-001",
                conversation_id="nonexistent-conversation",
                runtime_mode="mock",
                state_status="pending",
                payload_json='{}',
            )
            session.add(wm)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            error_msg = str(exc_info.value).lower()
            assert "foreign" in error_msg or "constraint" in error_msg


# ===========================================================================
# 16. Settings tests (sync)
# ===========================================================================


class TestPersistenceSettings:

    def test_default_persistence_backend_is_memory(self):
        settings = Settings()
        assert settings.persistence_backend == PersistenceBackend.MEMORY

    def test_sqlite_backend_configured(self):
        settings = Settings(persistence_backend=PersistenceBackend.SQLITE)
        assert settings.is_persistence_sqlite

    def test_memory_backend_not_sqlite(self):
        settings = Settings()
        assert not settings.is_persistence_sqlite