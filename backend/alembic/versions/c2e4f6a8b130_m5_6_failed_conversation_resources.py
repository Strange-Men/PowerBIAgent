"""M5.6 failed conversation resource metadata and recent sort index.

Revision ID: c2e4f6a8b130
Revises: b7c9d2e4f610
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c2e4f6a8b130"
down_revision: str | None = "b7c9d2e4f610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "resource_status",
                sa.String(length=16),
                nullable=False,
                server_default="ready",
            )
        )
        batch_op.add_column(
            sa.Column("last_error_type", sa.String(length=80), nullable=True)
        )
        batch_op.drop_index("ix_conversations_namespace_recent")
        batch_op.create_index(
            "ix_conversations_namespace_recent",
            [
                "runtime_mode",
                "archived_at",
                "updated_at",
                "created_at",
                "conversation_id",
            ],
            unique=False,
        )
    op.execute(
        """
        UPDATE conversations
        SET resource_status = 'failed',
            last_error_type = (
                SELECT json_extract(rs.payload_json, '$.error_type')
                FROM result_snapshots AS rs
                WHERE rs.runtime_mode = conversations.runtime_mode
                  AND rs.conversation_id = conversations.conversation_id
                  AND COALESCE(json_extract(rs.payload_json, '$.error_type'), '') <> ''
                ORDER BY julianday(rs.created_at) DESC, rs.id DESC
                LIMIT 1
            )
        WHERE EXISTS (
            SELECT 1
            FROM result_snapshots AS rs
            WHERE rs.runtime_mode = conversations.runtime_mode
              AND rs.conversation_id = conversations.conversation_id
              AND COALESCE(json_extract(rs.payload_json, '$.error_type'), '') <> ''
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_index("ix_conversations_namespace_recent")
        batch_op.create_index(
            "ix_conversations_namespace_recent",
            ["runtime_mode", "archived_at", "updated_at", "conversation_id"],
            unique=False,
        )
        batch_op.drop_column("last_error_type")
        batch_op.drop_column("resource_status")
