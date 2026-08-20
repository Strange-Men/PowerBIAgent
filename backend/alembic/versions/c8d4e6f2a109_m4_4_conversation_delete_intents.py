"""M4.4 durable conversation delete intents.

Revision ID: c8d4e6f2a109
Revises: f4c3a2b1907d
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d4e6f2a109"
down_revision: Union[str, Sequence[str], None] = "f4c3a2b1907d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_delete_intents",
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("runtime_mode", sa.String(length=16), nullable=False),
        sa.Column("report_ids_json", sa.Text(), nullable=False),
        sa.Column("deleted_counts_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "conversation_id",
            "runtime_mode",
            name="pk_conversation_delete_intents",
        ),
    )


def downgrade() -> None:
    op.drop_table("conversation_delete_intents")
