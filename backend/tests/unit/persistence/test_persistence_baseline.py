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
import pytest_asyncio
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
            "conversation_delete_intents", "report_delete_intents",
            "report_presentations",
        }
        missing = expected - tables
        assert not missing, f"Tables missing after migration: {missing}"

        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()[0]
        assert version == "c2e4f6a8b130"
        conversation_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        conn.close()
        assert "title" in conversation_columns
        assert "resource_status" in conversation_columns
        assert "last_error_type" in conversation_columns

    def test_failed_resource_migration_backfills_existing_error_snapshots(self):
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()
        TestMigrationConstraints._run_alembic_upgrade(
            tmp_db_path,
            posix_path,
            project_root,
            target="b7c9d2e4f610",
        )
        with sqlite3.connect(tmp_db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (runtime_mode, conversation_id) "
                "VALUES (?, ?)",
                ("real", "failed-before-m56"),
            )
            conn.execute(
                """
                INSERT INTO result_snapshots (
                    request_id, runtime_mode, conversation_id,
                    request_fingerprint_hash, terminal_state, response_type,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "failed-request",
                    "real",
                    "failed-before-m56",
                    "f" * 64,
                    "tool_failed",
                    "",
                    json.dumps({"error_type": "powerbi_query_failed"}),
                ),
            )
        TestMigrationConstraints._run_alembic_upgrade(
            tmp_db_path,
            posix_path,
            project_root,
            target="head",
        )
        with sqlite3.connect(tmp_db_path) as conn:
            row = conn.execute(
                "SELECT resource_status, last_error_type FROM conversations "
                "WHERE runtime_mode = ? AND conversation_id = ?",
                ("real", "failed-before-m56"),
            ).fetchone()
        assert row == ("failed", "powerbi_query_failed")

    def test_report_presentation_migration_backfills_existing_artifacts(self):
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()
        TestMigrationConstraints._run_alembic_upgrade(
            tmp_db_path,
            posix_path,
            project_root,
            target="e7a9c2d4f631",
        )
        report_id = "rpt_" + "a" * 32
        with sqlite3.connect(tmp_db_path) as conn:
            conn.execute(
                """
                INSERT INTO report_artifacts (
                    report_id, conversation_id, request_id, template_key,
                    semantic_model_key, schema_fingerprint, source_mode,
                    content_hash, relative_path, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    "conv-existing",
                    "req-existing",
                    "sales_report",
                    "model",
                    "f" * 64,
                    "real",
                    "c" * 64,
                    f"{report_id}.html",
                    None,
                ),
            )
        TestMigrationConstraints._run_alembic_upgrade(
            tmp_db_path,
            posix_path,
            project_root,
            target="head",
        )
        with sqlite3.connect(tmp_db_path) as conn:
            row = conn.execute(
                """
                SELECT source_mode, conversation_id, request_id,
                       display_title, availability_status
                FROM report_presentations WHERE report_id = ?
                """,
                (report_id,),
            ).fetchone()
        assert row == (
            "real",
            "conv-existing",
            "req-existing",
            "销售分析报告",
            "available",
        )


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

    @pytest_asyncio.fixture
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

    @pytest_asyncio.fixture
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
        await self._create_conversation(db_engine, "test-pc-conv-async")
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
    async def test_pragmas_set_on_connection(self, db_engine):
        """Verify PRAGMAs are set on engine connections.

        ``foreign_keys`` and ``busy_timeout`` are set per-connection via
        ``_set_sqlite_pragmas`` (attached as a pool event in ``create_engine``).
        ``journal_mode = WAL`` is set database-level via ``configure_engine``.
        """
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


# ===========================================================================
# 18. Migration composite PK/FK verification
# ===========================================================================


class TestMigrationConstraints:
    """Verify that the Alembic corrective migration produces correct
    composite PK and FK constraints."""

    SAMPLE_INI = """\
[alembic]
script_location = {project_root}/backend/alembic
prepend_sys_path = {project_root}
sqlalchemy.url = sqlite+aiosqlite:///{db_path}

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

    def test_migration_composite_pk(self):
        """Fresh DB: alembic upgrade head creates composite PK."""
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()

        self._run_alembic_upgrade(tmp_db_path, posix_path, project_root)

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='conversations'"
        )
        ddl = cur.fetchone()[0]
        conn.close()
        assert "PRIMARY KEY (runtime_mode, conversation_id)" in ddl or \
               "PRIMARY KEY (\"runtime_mode\", \"conversation_id\")" in ddl, \
            f"Expected composite PK in:\n{ddl}"

    def test_migration_composite_fk_work_memories(self):
        """Fresh DB: work_memories has composite FK."""
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()

        self._run_alembic_upgrade(tmp_db_path, posix_path, project_root)

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='work_memories'"
        )
        ddl = cur.fetchone()[0]
        conn.close()
        assert "FOREIGN KEY (runtime_mode, conversation_id)" in ddl, \
            f"Expected composite FK in:\n{ddl}"
        # Ensure no old single-column FK remains
        assert "FOREIGN KEY (conversation_id)" not in ddl.replace(
            "(runtime_mode, conversation_id)", ""
        ), f"Old FK should not remain:\n{ddl}"

    def test_migration_composite_fk_result_snapshots(self):
        """Fresh DB: result_snapshots has composite FK."""
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()

        self._run_alembic_upgrade(tmp_db_path, posix_path, project_root)

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='result_snapshots'"
        )
        ddl = cur.fetchone()[0]
        conn.close()
        assert "FOREIGN KEY (runtime_mode, conversation_id)" in ddl, \
            f"Expected composite FK in:\n{ddl}"

    def test_migration_composite_fk_pending_clarifications(self):
        """Fresh DB: pending_clarifications has composite FK."""
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()

        self._run_alembic_upgrade(tmp_db_path, posix_path, project_root)

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='pending_clarifications'"
        )
        ddl = cur.fetchone()[0]
        conn.close()
        assert "FOREIGN KEY (runtime_mode, conversation_id)" in ddl, \
            f"Expected composite FK in:\n{ddl}"

    def test_upgrade_from_initial_to_head(self):
        """Upgrade 42821213393c -> head produces composite schema."""
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()

        self._run_alembic_upgrade(
            tmp_db_path, posix_path, project_root,
            target="42821213393c",
        )

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='conversations'"
        )
        initial_ddl = cur.fetchone()[0]
        conn.close()
        assert "PRIMARY KEY (conversation_id)" in initial_ddl, \
            f"Expected single PK in initial:\n{initial_ddl}"

        self._run_alembic_upgrade(
            tmp_db_path, posix_path, project_root,
            target="head",
        )

        conn = sqlite3.connect(tmp_db_path)
        cur = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='conversations'"
        )
        ddl = cur.fetchone()[0]
        conn.close()
        assert "PRIMARY KEY (runtime_mode, conversation_id)" in ddl or \
               "PRIMARY KEY (\"runtime_mode\", \"conversation_id\")" in ddl, \
            f"Expected composite PK after upgrade in:\n{ddl}"

    def test_upgrade_from_m43_to_head_adds_delete_intents(self):
        """Upgrade the exact M4.3 schema to the M4.4 cleanup journal."""
        tmp_db_path = _tmp_db_path()
        posix_path = Path(tmp_db_path).resolve().as_posix()
        project_root = Path.cwd().resolve()

        self._run_alembic_upgrade(
            tmp_db_path,
            posix_path,
            project_root,
            target="f4c3a2b1907d",
        )
        with sqlite3.connect(tmp_db_path) as conn:
            before = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='conversation_delete_intents'"
            ).fetchone()
        assert before is None

        self._run_alembic_upgrade(
            tmp_db_path,
            posix_path,
            project_root,
            target="head",
        )
        with sqlite3.connect(tmp_db_path) as conn:
            after = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='conversation_delete_intents'"
            ).fetchone()
            version = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert after == ("conversation_delete_intents",)
        assert version == "c2e4f6a8b130"

    @staticmethod
    def _run_alembic_upgrade(
        tmp_db_path: str,
        posix_path: str,
        project_root: Path,
        target: str = "head",
    ) -> None:
        ini_content = TestMigrationConstraints.SAMPLE_INI.format(
            project_root=project_root.as_posix(),
            db_path=posix_path,
        )
        ini_dir = Path(tempfile.mkdtemp())
        ini_file = ini_dir / "alembic.ini"
        ini_file.write_text(ini_content, encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root)
        for key in list(env.keys()):
            if key.startswith("ALEMBIC_"):
                del env[key]

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ini_file),
             "upgrade", target],
            capture_output=True, text=True,
            cwd=ini_dir, env=env,
        )
        if result.returncode != 0:
            pytest.fail(
                f"alembic upgrade {target} failed "
                f"(exit {result.returncode}):\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )


# ===========================================================================
# 19. Conversation namespace isolation (async)
# ===========================================================================


class TestConversationNamespace:
    """Verify Mock/Real namespace isolation for conversations."""

    @pytest_asyncio.fixture
    async def db_engine(self):
        tmp_db_path = _tmp_db_path()
        settings = _sqlite_settings(tmp_db_path)
        engine = create_engine(settings, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await configure_engine(engine)
        yield engine
        await dispose_engine(engine)

    @pytest.mark.asyncio
    async def test_mock_and_real_same_conv_id_allowed(self, db_engine):
        """Same conversation_id with different runtime_mode is allowed."""
        factory = create_session_factory(db_engine)
        async with factory() as session:
            conv_mock = ConversationModel(
                conversation_id="shared-conv-1",
                runtime_mode="mock",
            )
            session.add(conv_mock)
            await session.commit()

        async with factory() as session:
            conv_real = ConversationModel(
                conversation_id="shared-conv-1",
                runtime_mode="real",
            )
            session.add(conv_real)
            await session.commit()

        # Verify both exist
        async with factory() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(ConversationModel).where(
                    ConversationModel.conversation_id == "shared-conv-1"
                )
            )
            rows = result.scalars().all()
            assert len(rows) == 2
            modes = {r.runtime_mode for r in rows}
            assert modes == {"mock", "real"}

    @pytest.mark.asyncio
    async def test_same_mode_same_conv_id_rejected(self, db_engine):
        """Same (runtime_mode, conversation_id) duplicate is rejected."""
        factory = create_session_factory(db_engine)
        async with factory() as session:
            conv1 = ConversationModel(
                conversation_id="dup-conv-1",
                runtime_mode="mock",
            )
            session.add(conv1)
            await session.commit()

        async with factory() as session:
            conv2 = ConversationModel(
                conversation_id="dup-conv-1",
                runtime_mode="mock",
            )
            session.add(conv2)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            error_msg = str(exc_info.value).lower()
            assert "primary" in error_msg or "unique" in error_msg or "constraint" in error_msg


# ===========================================================================
# 20. Composite FK enforcement (async)
# ===========================================================================


class TestCompositeFKEnforcement:
    """Verify that composite FK correctly enforces namespace isolation."""

    @pytest_asyncio.fixture
    async def db_engine(self):
        tmp_db_path = _tmp_db_path()
        settings = _sqlite_settings(tmp_db_path)
        engine = create_engine(settings, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await configure_engine(engine)
        yield engine
        await dispose_engine(engine)

    @pytest.mark.asyncio
    async def test_work_memory_fk_requires_matching_mode(self, db_engine):
        """work_memory with different runtime_mode than conversation should fail FK."""
        factory = create_session_factory(db_engine)

        # Create a mock conversation
        async with factory() as session:
            conv = ConversationModel(
                conversation_id="conv-ns-1",
                runtime_mode="mock",
            )
            session.add(conv)
            await session.commit()

        # work_memory referencing same conversation_id but different mode
        async with factory() as session:
            wm = WorkMemoryModel(
                request_id="ns-test-wm-1",
                conversation_id="conv-ns-1",
                runtime_mode="real",  # <-- different from conversation's mock!
                state_status="pending",
                payload_json='{"test": true}',
            )
            session.add(wm)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            error_msg = str(exc_info.value).lower()
            assert "foreign" in error_msg or "constraint" in error_msg

    @pytest.mark.asyncio
    async def test_work_memory_fk_matching_mode_succeeds(self, db_engine):
        """work_memory with same runtime_mode as conversation succeeds."""
        factory = create_session_factory(db_engine)

        async with factory() as session:
            conv = ConversationModel(
                conversation_id="conv-ns-2",
                runtime_mode="mock",
            )
            session.add(conv)
            await session.commit()

        async with factory() as session:
            wm = WorkMemoryModel(
                request_id="ns-test-wm-2",
                conversation_id="conv-ns-2",
                runtime_mode="mock",
                state_status="pending",
                payload_json='{"test": true}',
            )
            session.add(wm)
            await session.commit()  # should succeed

    @pytest.mark.asyncio
    async def test_snapshot_fk_requires_matching_mode(self, db_engine):
        """Snapshot with different runtime_mode than conversation should fail FK."""
        factory = create_session_factory(db_engine)

        async with factory() as session:
            conv = ConversationModel(
                conversation_id="conv-ns-3",
                runtime_mode="mock",
            )
            session.add(conv)
            await session.commit()

        async with factory() as session:
            rs = ResultSnapshotModel(
                request_id="ns-test-rs-1",
                conversation_id="conv-ns-3",
                runtime_mode="real",  # <-- different!
                request_fingerprint_hash="a" * 64,
                terminal_state="completed",
                response_type="answer",
                payload_json='{"test": true}',
            )
            session.add(rs)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            error_msg = str(exc_info.value).lower()
            assert "foreign" in error_msg or "constraint" in error_msg

    @pytest.mark.asyncio
    async def test_pending_fk_requires_matching_mode(self, db_engine):
        """Pending clarification with different runtime_mode should fail FK."""
        factory = create_session_factory(db_engine)

        async with factory() as session:
            conv = ConversationModel(
                conversation_id="conv-ns-4",
                runtime_mode="mock",
            )
            session.add(conv)
            await session.commit()

        async with factory() as session:
            pc = PendingClarificationModel(
                conversation_id="conv-ns-4",
                runtime_mode="real",  # <-- different!
                chain_id="chain-test",
                semantic_model_key="model_key",
                schema_fingerprint="a" * 64,
                payload_json='{"test": true}',
            )
            session.add(pc)
            with pytest.raises(Exception) as exc_info:
                await session.commit()
            error_msg = str(exc_info.value).lower()
            assert "foreign" in error_msg or "constraint" in error_msg


# ===========================================================================
# 21. PRAGMA per-connection (async)
# ===========================================================================


class TestPragmaPerConnection:
    """Verify PRAGMAs are applied to every new connection, not just the first."""

    @pytest_asyncio.fixture
    async def db_path(self):
        tmp = _tmp_db_path()
        yield tmp

    @pytest_asyncio.fixture
    async def shared_engine(self, db_path):
        settings = _sqlite_settings(db_path)
        engine = create_engine(settings, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await configure_engine(engine)
        yield engine
        await dispose_engine(engine)

    @pytest.mark.asyncio
    async def test_first_connection_has_pragmas(self, shared_engine):
        """First connection from the pool has all PRAGMAs set."""
        async with shared_engine.connect() as conn:
            def check(sync_conn):
                fk = sync_conn.exec_driver_sql(
                    "PRAGMA foreign_keys;"
                ).fetchone()[0]
                timeout = sync_conn.exec_driver_sql(
                    "PRAGMA busy_timeout;"
                ).fetchone()[0]
                assert fk == 1, f"Expected foreign_keys=1, got {fk}"
                assert timeout == 5000, f"Expected busy_timeout=5000, got {timeout}"
            await conn.run_sync(check)

    @pytest.mark.asyncio
    async def test_separate_connection_has_pragmas(self, shared_engine):
        """A fresh new connection from the pool also has all PRAGMAs set.

        This verifies that the per-connection PRAGMA event listener
        (``_set_sqlite_pragmas``) fires on every ``connect`` event, not
        just on the first one.
        """
        # Close all pooled connections to force a fresh one
        await shared_engine.dispose()
        # Re-acquire (will create a new connection with the event handler)
        async with shared_engine.connect() as conn:
            def check(sync_conn):
                fk = sync_conn.exec_driver_sql(
                    "PRAGMA foreign_keys;"
                ).fetchone()[0]
                timeout = sync_conn.exec_driver_sql(
                    "PRAGMA busy_timeout;"
                ).fetchone()[0]
                assert fk == 1, f"Expected foreign_keys=1 on new conn, got {fk}"
                assert timeout == 5000, f"Expected busy_timeout=5000 on new conn, got {timeout}"
            await conn.run_sync(check)


# ===========================================================================
# 22. PRAGMA per-connection: two independent engines (async)
# ===========================================================================


class TestPragmaTwoEngines:
    """Verify two independent DB engines each get per-connection PRAGMAs."""

    @pytest.mark.asyncio
    async def test_two_independent_connections_both_have_pragmas(self):
        """Two independent SQLite engines each get PRAGMAs on their connections.

        This is the most rigorous test: separate engine instances, each with
        its own event handler, each creating a fresh connection.
        """
        tmp_db = _tmp_db_path()
        settings = _sqlite_settings(tmp_db)

        engine1 = create_engine(settings, echo=False)
        engine2 = create_engine(settings, echo=False)

        # Both engines talk to the same SQLite file
        async with engine1.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await configure_engine(engine1)

        # Verify engine1's connection
        async with engine1.connect() as conn:
            def check1(sync_conn):
                row1 = sync_conn.exec_driver_sql("PRAGMA foreign_keys;").fetchone()
                row2 = sync_conn.exec_driver_sql("PRAGMA busy_timeout;").fetchone()
                assert row1[0] == 1, f"engine1 foreign_keys={row1[0]}"
                assert row2[0] == 5000, f"engine1 busy_timeout={row2[0]}"
            await conn.run_sync(check1)

        # Verify engine2's connection
        async with engine2.connect() as conn:
            def check2(sync_conn):
                row1 = sync_conn.exec_driver_sql("PRAGMA foreign_keys;").fetchone()
                row2 = sync_conn.exec_driver_sql("PRAGMA busy_timeout;").fetchone()
                assert row1[0] == 1, f"engine2 foreign_keys={row1[0]}"
                assert row2[0] == 5000, f"engine2 busy_timeout={row2[0]}"
            await conn.run_sync(check2)

        await dispose_engine(engine1)
        await dispose_engine(engine2)
