"""M4.3 conversation archive state and namespace query indexes.

Revision ID: f4c3a2b1907d
Revises: ab8d7df39a02
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4c3a2b1907d"
down_revision: Union[str, Sequence[str], None] = "ab8d7df39a02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=False),
            nullable=True,
            comment="UTC logical archive timestamp; null means visible",
        ),
    )
    op.create_index(
        "ix_conversations_namespace_recent",
        "conversations",
        ["runtime_mode", "archived_at", "updated_at", "conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_work_memories_namespace_history",
        "work_memories",
        ["runtime_mode", "conversation_id", "state_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_result_snapshots_namespace_history",
        "result_snapshots",
        ["runtime_mode", "conversation_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_report_artifacts_namespace_history",
        "report_artifacts",
        ["source_mode", "conversation_id", "created_at", "report_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_artifacts_namespace_history", table_name="report_artifacts"
    )
    op.drop_index(
        "ix_result_snapshots_namespace_history", table_name="result_snapshots"
    )
    op.drop_index(
        "ix_work_memories_namespace_history", table_name="work_memories"
    )
    op.drop_index(
        "ix_conversations_namespace_recent", table_name="conversations"
    )
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("archived_at")
