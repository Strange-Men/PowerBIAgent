"""M5.4.1 report archive and global resource pagination indexes.

Revision ID: b7c9d2e4f610
Revises: a4f6b8c2d190
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b7c9d2e4f610"
down_revision: str | None = "a4f6b8c2d190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("report_presentations") as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_report_presentations_resource_status",
        "report_presentations",
        ["source_mode", "archived_at", "updated_at", "report_id"],
        unique=False,
    )
    op.create_index(
        "ix_report_artifacts_source_history",
        "report_artifacts",
        ["source_mode", "created_at", "report_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_artifacts_source_history",
        table_name="report_artifacts",
    )
    op.drop_index(
        "ix_report_presentations_resource_status",
        table_name="report_presentations",
    )
    with op.batch_alter_table("report_presentations") as batch_op:
        batch_op.drop_column("archived_at")
