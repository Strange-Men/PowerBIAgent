"""M4.0 corrective: composite conversation PK and composite FK constraints

Revision ID: 01dc0d90d920
Revises: 42821213393c
Create Date: 2026-08-18 13:34:51.727312

NOTE
----
SQLite does not support ALTER TABLE to add/drop PK or FK constraints.
This migration uses Alembic's batch_alter_table (table rebuild) for
all affected tables.  FK enforcement is temporarily disabled during
the migration to avoid ordering issues.

Migration order (safe for SQLite):
1. Disable FK checks (re-enabled at the end)
2. Rebuild ``conversations`` with composite PK
3. Rebuild child tables with new composite FKs (old unnamed FKs are
   dropped as a side effect of the table rebuild)
4. Re-create indexes that the rebuild dropped
5. Re-enable FK checks
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01dc0d90d920'
down_revision: Union[str, Sequence[str], None] = '42821213393c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _child_table_cols(table: str) -> str:
    """Return comma-separated column names for *table* (used in INSERT)."""
    cols = {
        "work_memories": (
            "id, request_id, conversation_id, runtime_mode, "
            "state_status, base_memory_version, memory_version, "
            "semantic_model_key, report_template_key, current_intent, "
            "analysis_goal, payload_json, failure_reason, failure_stage, "
            "created_at, updated_at"
        ),
        "result_snapshots": (
            "id, request_id, runtime_mode, conversation_id, "
            "request_fingerprint_hash, terminal_state, response_type, "
            "payload_json, created_at"
        ),
        "pending_clarifications": (
            "id, conversation_id, runtime_mode, chain_id, "
            "semantic_model_key, schema_fingerprint, payload_json, "
            "created_at, updated_at"
        ),
    }
    return cols[table]


def _rebuild_table_with(
    table: str,
    create_sql: str,
    *,
    indexes: list[tuple[str, list[str]]] | None = None,
) -> None:
    """SQLite safe table rebuild.

    1. CREATE TABLE <table>_new
    2. INSERT INTO <table>_new SELECT ... FROM <table>
    3. DROP TABLE <table>
    4. ALTER TABLE <table>_new RENAME TO <table>
    5. Re-create indexes
    """
    op.execute(f"CREATE TABLE {table}_new ({create_sql})")
    op.execute(
        f"INSERT INTO {table}_new ({_child_table_cols(table)}) "
        f"SELECT {_child_table_cols(table)} FROM {table}"
    )
    op.execute(f"DROP TABLE {table}")
    op.execute(f"ALTER TABLE {table}_new RENAME TO {table}")

    if indexes:
        for ix_name, cols in indexes:
            cols_sql = ", ".join(cols)
            op.execute(
                f"CREATE INDEX {ix_name} ON {table} ({cols_sql})"
            )


def upgrade() -> None:
    """Upgrade schema.

    1. ``conversations`` — PK from single ``conversation_id`` to
       composite ``(runtime_mode, conversation_id)``.
    2. ``work_memories`` — FK replaced with composite FK referencing
       ``conversations(runtime_mode, conversation_id)``.
    3. ``result_snapshots`` — Same FK change.
    4. ``pending_clarifications`` — New composite FK added.
    """
    # Temporarily disable FK checks.  SQLite table rebuilds in batch mode
    # use ``defer_foreign_keys`` internally, but our own explicit CREATE
    # + INSERT pattern for child tables needs foreign_keys OFF to avoid
    # ordering conflicts.
    op.execute("PRAGMA foreign_keys = OFF")

    # ------------------------------------------------------------------
    # 1. conversations: change PK to composite (using Alembic batch mode)
    # ------------------------------------------------------------------
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.create_primary_key(
            "pk_conversations", ["runtime_mode", "conversation_id"]
        )

    # ------------------------------------------------------------------
    # 2. work_memories: rebuild with composite FK
    # ------------------------------------------------------------------
    _rebuild_table_with("work_memories", """
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        request_id VARCHAR(64) NOT NULL,
        conversation_id VARCHAR(64) NOT NULL,
        runtime_mode VARCHAR(16) NOT NULL,
        state_status VARCHAR(16) NOT NULL,
        base_memory_version INTEGER NOT NULL,
        memory_version INTEGER NOT NULL,
        semantic_model_key VARCHAR(128),
        report_template_key VARCHAR(64),
        current_intent VARCHAR(64),
        analysis_goal VARCHAR(512),
        payload_json TEXT,
        failure_reason TEXT,
        failure_stage VARCHAR(64),
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        CONSTRAINT uq_work_memories_runtime_request
            UNIQUE (runtime_mode, request_id),
        FOREIGN KEY (runtime_mode, conversation_id)
            REFERENCES conversations (runtime_mode, conversation_id)
    """, indexes=[
        ("ix_work_memories_request_id", ["request_id"]),
        ("ix_work_memories_conversation_id", ["conversation_id"]),
    ])

    # ------------------------------------------------------------------
    # 3. result_snapshots: rebuild with composite FK
    # ------------------------------------------------------------------
    _rebuild_table_with("result_snapshots", """
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        request_id VARCHAR(64) NOT NULL,
        runtime_mode VARCHAR(16) NOT NULL,
        conversation_id VARCHAR(64) NOT NULL,
        request_fingerprint_hash VARCHAR(64) NOT NULL,
        terminal_state VARCHAR(32) NOT NULL,
        response_type VARCHAR(32) NOT NULL,
        payload_json TEXT NOT NULL,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        CONSTRAINT uq_result_snapshots_runtime_request
            UNIQUE (runtime_mode, request_id),
        FOREIGN KEY (runtime_mode, conversation_id)
            REFERENCES conversations (runtime_mode, conversation_id)
    """, indexes=[
        ("ix_result_snapshots_request_id", ["request_id"]),
        ("ix_result_snapshots_conversation_id", ["conversation_id"]),
    ])

    # ------------------------------------------------------------------
    # 4. pending_clarifications: rebuild with composite FK
    # ------------------------------------------------------------------
    _rebuild_table_with("pending_clarifications", """
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        conversation_id VARCHAR(64) NOT NULL,
        runtime_mode VARCHAR(16) NOT NULL,
        chain_id VARCHAR(64) NOT NULL,
        semantic_model_key VARCHAR(128) NOT NULL,
        schema_fingerprint VARCHAR(64) NOT NULL,
        payload_json TEXT NOT NULL,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        CONSTRAINT uq_pending_clarifications_runtime_conv
            UNIQUE (runtime_mode, conversation_id),
        FOREIGN KEY (runtime_mode, conversation_id)
            REFERENCES conversations (runtime_mode, conversation_id)
    """, indexes=[
        ("ix_pending_clarifications_conversation_id", ["conversation_id"]),
    ])

    op.execute("PRAGMA foreign_keys = ON")


def downgrade() -> None:
    """Downgrade schema — revert to original single-column FK/PK setup."""
    op.execute("PRAGMA foreign_keys = OFF")

    # 4. pending_clarifications: rebuild without FK
    _rebuild_table_with("pending_clarifications", """
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        conversation_id VARCHAR(64) NOT NULL,
        runtime_mode VARCHAR(16) NOT NULL,
        chain_id VARCHAR(64) NOT NULL,
        semantic_model_key VARCHAR(128) NOT NULL,
        schema_fingerprint VARCHAR(64) NOT NULL,
        payload_json TEXT NOT NULL,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        CONSTRAINT uq_pending_clarifications_runtime_conv
            UNIQUE (runtime_mode, conversation_id)
    """, indexes=[
        ("ix_pending_clarifications_conversation_id", ["conversation_id"]),
    ])

    # 3. result_snapshots: rebuild with old FK on conversation_id only
    _rebuild_table_with("result_snapshots", """
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        request_id VARCHAR(64) NOT NULL,
        runtime_mode VARCHAR(16) NOT NULL,
        conversation_id VARCHAR(64) NOT NULL,
        request_fingerprint_hash VARCHAR(64) NOT NULL,
        terminal_state VARCHAR(32) NOT NULL,
        response_type VARCHAR(32) NOT NULL,
        payload_json TEXT NOT NULL,
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        CONSTRAINT uq_result_snapshots_runtime_request
            UNIQUE (runtime_mode, request_id),
        FOREIGN KEY (conversation_id)
            REFERENCES conversations (conversation_id)
    """, indexes=[
        ("ix_result_snapshots_request_id", ["request_id"]),
        ("ix_result_snapshots_conversation_id", ["conversation_id"]),
    ])

    # 2. work_memories: rebuild with old FK on conversation_id only
    _rebuild_table_with("work_memories", """
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        request_id VARCHAR(64) NOT NULL,
        conversation_id VARCHAR(64) NOT NULL,
        runtime_mode VARCHAR(16) NOT NULL,
        state_status VARCHAR(16) NOT NULL,
        base_memory_version INTEGER NOT NULL,
        memory_version INTEGER NOT NULL,
        semantic_model_key VARCHAR(128),
        report_template_key VARCHAR(64),
        current_intent VARCHAR(64),
        analysis_goal VARCHAR(512),
        payload_json TEXT,
        failure_reason TEXT,
        failure_stage VARCHAR(64),
        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
        CONSTRAINT uq_work_memories_runtime_request
            UNIQUE (runtime_mode, request_id),
        FOREIGN KEY (conversation_id)
            REFERENCES conversations (conversation_id)
    """, indexes=[
        ("ix_work_memories_request_id", ["request_id"]),
        ("ix_work_memories_conversation_id", ["conversation_id"]),
    ])

    # 1. conversations: revert to single-column PK
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.create_primary_key("pk_conversations_old", ["conversation_id"])

    op.execute("PRAGMA foreign_keys = ON")