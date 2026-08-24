"""M5.4 mutable report presentation metadata and deletion tombstones.

Revision ID: a4f6b8c2d190
Revises: e7a9c2d4f631
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4f6b8c2d190"
down_revision: Union[str, Sequence[str], None] = "e7a9c2d4f631"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_presentations",
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("source_mode", sa.String(length=16), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("display_title", sa.String(length=120), nullable=False),
        sa.Column(
            "availability_status",
            sa.String(length=16),
            server_default="available",
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_index(
        "ix_report_presentations_namespace_history",
        "report_presentations",
        ["source_mode", "conversation_id", "request_id", "report_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO report_presentations (
                report_id,
                source_mode,
                conversation_id,
                request_id,
                display_title,
                availability_status,
                created_at,
                updated_at
            )
            SELECT
                report_id,
                source_mode,
                conversation_id,
                request_id,
                '销售分析报告',
                'available',
                created_at,
                created_at
            FROM report_artifacts
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_presentations_namespace_history",
        table_name="report_presentations",
    )
    op.drop_table("report_presentations")
