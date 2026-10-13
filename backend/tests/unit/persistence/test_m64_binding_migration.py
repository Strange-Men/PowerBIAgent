"""New empty synthetic DB only; no production migrations or data."""
import sqlite3
from contextlib import closing
from alembic import command
from backend.tests.unit.persistence.test_m63_migration import config


def test_binding_migration_preserves_legacy_and_creates_empty_owner_table(tmp_path):
    path=tmp_path/'synthetic.db';cfg=config(path)
    command.upgrade(cfg,'f63a1b2c3d40')
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("INSERT INTO conversations(owner_id,conversation_id,runtime_mode,title) VALUES ('local:legacy','legacy','mock','synthetic')")
        conn.commit()
    command.upgrade(cfg,'head')
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute('SELECT * FROM cloud_conversation_bindings').fetchall()==[]
        assert conn.execute("SELECT title FROM conversations WHERE conversation_id='legacy'").fetchone()==('synthetic',)
        foreigns=conn.execute('PRAGMA foreign_key_list(cloud_conversation_bindings)').fetchall()
        assert any(x[2]=='resource_owners' and x[3]=='owner_id' for x in foreigns)
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
