"""M6.4 immutable owner/exact resource binding metadata.

Only synthetic migration verified; operator authorization required for real DB.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ab64d10e7f20'
down_revision = 'f63a1b2c3d40'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cloud_conversation_bindings',
        sa.Column('owner_id',sa.String(80),sa.ForeignKey('resource_owners.owner_id'),primary_key=True),
        sa.Column('conversation_id',sa.String(64),primary_key=True),
        sa.Column('model_key',sa.String(128),nullable=False),
        sa.Column('workspace_id',sa.String(36),nullable=False),
        sa.Column('model_id',sa.String(36),nullable=False),
        sa.Column('schema_fingerprint',sa.String(64),nullable=False),
        sa.Column('source_mode',sa.String(16),nullable=False),
        sa.UniqueConstraint('owner_id','model_key','conversation_id',name='uq_cloud_conversation_binding'),
        sa.CheckConstraint("source_mode IN ('mock','real')",name='ck_cloud_binding_source'))


def downgrade():
    raise RuntimeError('forward-only: exact binding recovery requires operator backup restore')
