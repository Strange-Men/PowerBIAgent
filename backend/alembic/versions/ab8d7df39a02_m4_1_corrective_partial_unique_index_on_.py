"""M4.1 corrective: partial unique index on committed memory version

Add a SQLite partial unique index on ``work_memories``:

    CREATE UNIQUE INDEX ix_work_memories_committed_version
    ON work_memories (runtime_mode, conversation_id, memory_version)
    WHERE state_status = 'committed'

This is the **database-level invariant** that guarantees at most
one row per (runtime_mode, conversation_id, memory_version) can
ever be COMMITTED.  Two concurrent ``commit()`` calls racing on
the same base_version will both write ``memory_version = N + 1``,
but only the first transaction to finish will successfully commit;
the second will hit an IntegrityError (converted to
``MemoryVersionConflictError`` at the repository layer).

NOTE
----
``memory_version`` is NOT nullable.  PENDING rows always have
``memory_version = 0``.  The partial index only covers COMMITTED
rows, so multiple PENDING rows per conversation can coexist safely.

Revision ID: ab8d7df39a02
Revises: 01dc0d90d920
Create Date: 2026-08-18 16:00:36.681920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab8d7df39a02'
down_revision: Union[str, Sequence[str], None] = '01dc0d90d920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial unique index on committed memory version.

    SQLite supports ``CREATE UNIQUE INDEX … WHERE`` natively (partial
    indexes were added in SQLite 3.8.0).  This is handled as a raw
    SQL statement since SQLAlchemy/Alembic do not have a portable
    ``create_partial_unique_index()`` helper.
    """
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_work_memories_committed_version "
        "ON work_memories (runtime_mode, conversation_id, memory_version) "
        "WHERE state_status = 'committed'"
    )


def downgrade() -> None:
    """Drop the partial unique index."""
    op.execute(
        "DROP INDEX IF EXISTS ix_work_memories_committed_version"
    )