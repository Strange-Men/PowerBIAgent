"""Real Alembic upgrades of synthetic DBs, never the developer database."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import pytest

from backend.app.persistence.models import LOCAL_OWNER_ID


TABLES = ("conversations", "conversation_delete_intents", "work_memories",
    "pending_clarifications", "result_snapshots", "report_artifacts",
    "report_presentations", "report_delete_intents")


def config(path):
    cfg = Config()
    cfg.set_main_option("script_location", str(Path("backend/alembic").resolve()))
    cfg.set_main_option("sqlalchemy.url", "sqlite+aiosqlite:///" + path.as_posix())
    return cfg


@pytest.mark.parametrize("legacy", [False, True])
def test_fresh_and_m62_upgrade_preserves_all_local_resources(tmp_path, legacy):
    path = tmp_path / "synthetic.db"
    cfg = config(path)
    if legacy:
        command.upgrade(cfg, "c2e4f6a8b130")
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("INSERT INTO conversations (conversation_id,runtime_mode,title) VALUES ('same','real','local synthetic')")
            conn.execute("INSERT INTO work_memories (request_id,conversation_id,runtime_mode,state_status,base_memory_version,memory_version,payload_json) VALUES ('same','same','real','pending',0,0,'{}')")
            conn.execute("INSERT INTO result_snapshots (request_id,conversation_id,runtime_mode,request_fingerprint_hash,terminal_state,response_type,payload_json) VALUES ('same','same','real','synthetic','completed','answer','{}')")
            conn.execute("INSERT INTO pending_clarifications (conversation_id,runtime_mode,chain_id,semantic_model_key,schema_fingerprint,payload_json) VALUES ('same','real','synthetic','synthetic','synthetic','{}')")
            conn.execute("INSERT INTO conversation_delete_intents (conversation_id,runtime_mode,report_ids_json,deleted_counts_json) VALUES ('deleted','real','[]','{}')")
            conn.execute("INSERT INTO report_artifacts (report_id,conversation_id,request_id,template_key,semantic_model_key,schema_fingerprint,source_mode,content_hash,relative_path,payload_json) VALUES ('rpt_synthetic','same','same','synthetic','synthetic','synthetic','real','synthetic','synthetic.html','{}')")
            conn.execute("INSERT INTO report_presentations (report_id,source_mode,display_title) VALUES ('rpt_synthetic','real','synthetic')")
            conn.execute("INSERT INTO report_delete_intents (report_id,source_mode,payload_json) VALUES ('rpt_deleted','real','{}')")
            conn.commit()
            before = {table: conn.execute(f'SELECT * FROM "{table}"').fetchall() for table in TABLES}
    command.upgrade(cfg, "head")
    # Running upgrade head twice is a no-op.
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT * FROM resource_owners").fetchall() == [
            (LOCAL_OWNER_ID, "LOCAL_DEV", "local", "legacy")]
        for table in TABLES:
            columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            owner = next(col for col in columns if col[1] == "owner_id")
            assert owner[3] == 1  # non-null
            rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
            if legacy:
                assert [row[:-1] for row in rows] == before[table]
                assert all(row[-1] == LOCAL_OWNER_ID for row in rows)
            else:
                assert not rows
            foreigns = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            assert any(fk[2] == "resource_owners" and fk[3] == "owner_id" for fk in foreigns)
        for table in ("work_memories", "result_snapshots", "pending_clarifications"):
            foreigns = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            links = [fk for fk in foreigns if fk[2] == "conversations"]
            assert [fk[3] for fk in links] == ["owner_id", "runtime_mode", "conversation_id"]
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO conversations (owner_id,conversation_id,runtime_mode) VALUES ('missing-owner','bad','real')")
    with pytest.raises(RuntimeError, match="forward-only"):
        command.downgrade(cfg, "c2e4f6a8b130")
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "f63a1b2c3d40"


def test_upgraded_db_supports_same_ids_across_principals(tmp_path):
    from backend.app.config.settings import Settings
    from backend.app.persistence.database import create_engine, create_session_factory
    from backend.app.persistence.ownership import PrincipalScopedRepositoryFactory
    from backend.tests.unit.persistence.test_m63_ownership import bundle, principal, snapshot
    from backend.app.memory.models import RuntimeDataMode, StructuredWorkMemory, MemoryCommitEvidence
    path = tmp_path / "synthetic.db"
    command.upgrade(config(path), "head")

    async def exercise():
        engine = create_engine(Settings(_env_file=None, persistence_database_path=str(path)))
        try:
            factory = PrincipalScopedRepositoryFactory(create_session_factory(engine), tmp_path / "reports")
            a, b = await bundle(factory), await bundle(factory, principal(2))
            mode = RuntimeDataMode.REAL
            for resources in (a, b):
                pending = await resources.memory.create_pending(StructuredWorkMemory(request_id="same", conversation_id="same"), mode)
                committed = await resources.memory.commit(pending, MemoryCommitEvidence(
                    intent_valid=True, request_allowed=True, query_plan_valid=True,
                    dax_valid=True, tool_execution_succeeded=True, query_result_valid=True,
                    response_valid=True, runtime_mode=mode))
                assert committed.memory_version == 1
                await resources.snapshots.save(snapshot("same", "same"), mode)
            assert await a.snapshots.exists("same", mode)
            assert await b.snapshots.exists("same", mode)
        finally:
            await engine.dispose()
    asyncio.run(exercise())
