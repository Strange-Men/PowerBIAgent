"""M5.3.3 durable independent report deletion.

Revision ID: e7a9c2d4f631
Revises: d3b7f9a1c524
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a9c2d4f631"
down_revision: Union[str, Sequence[str], None] = "d3b7f9a1c524"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_delete_intents",
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("source_mode", sa.String(length=16), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=False,
            comment="metadata-only report delete recovery payload",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("report_id"),
    )


def downgrade() -> None:
    op.drop_table("report_delete_intents")
