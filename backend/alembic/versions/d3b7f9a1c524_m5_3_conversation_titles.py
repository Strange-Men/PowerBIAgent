"""M5.3 presentation-only conversation titles.

Revision ID: d3b7f9a1c524
Revises: c8d4e6f2a109
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3b7f9a1c524"
down_revision: Union[str, Sequence[str], None] = "c8d4e6f2a109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "title",
            sa.String(length=80),
            nullable=True,
            comment="Presentation-only conversation title",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("title")
