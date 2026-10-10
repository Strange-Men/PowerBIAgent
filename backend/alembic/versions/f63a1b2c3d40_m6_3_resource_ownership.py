"""M6.3 deterministic legacy namespace and owner-scoped resource identities.

Forward only: restore a pre-upgrade offline backup with the M6.2 application
for rollback. Downgrade cannot safely merge independent principal IDs.
"""
from alembic import op
import sqlalchemy as sa

revision = "f63a1b2c3d40"
down_revision = "c2e4f6a8b130"
branch_labels = None
depends_on = None

TABLES = (
    "conversations", "conversation_delete_intents", "work_memories",
    "pending_clarifications", "result_snapshots", "report_artifacts",
    "report_presentations", "report_delete_intents",
)
COMPOSITE_PK = {
    "conversations", "conversation_delete_intents", "report_artifacts",
    "report_presentations", "report_delete_intents",
}


def upgrade():
    op.create_table("resource_owners",
        sa.Column("owner_id", sa.String(80), primary_key=True),
        sa.Column("identity_mode", sa.String(24), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("principal_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("identity_mode", "tenant_id", "principal_id", name="uq_resource_owner_identity"),
        sa.CheckConstraint(
            "(identity_mode = 'LOCAL_DEV' AND owner_id = 'local:legacy' "
            "AND tenant_id = 'local' AND principal_id = 'legacy') OR "
            "(identity_mode = 'ENTRA_PRINCIPAL' AND owner_id LIKE 'entra:%' "
            "AND length(tenant_id) = 36 AND length(principal_id) = 36)",
            name="ck_resource_owner_identity"))
    op.execute(sa.text("INSERT INTO resource_owners VALUES ('local:legacy', 'LOCAL_DEV', 'local', 'legacy')"))
    bind = op.get_bind()
    # Alembic's SQLite connection has FK enforcement disabled during table
    # recreation. Runtime connections always enable it. Verify after copy.
    for table in TABLES:
        inspector = sa.inspect(bind)
        primary = inspector.get_pk_constraint(table)
        uniques = inspector.get_unique_constraints(table)
        foreigns = inspector.get_foreign_keys(table)
        indexes = inspector.get_indexes(table)
        with op.batch_alter_table(table, recreate="always",
                naming_convention={"pk": "pk_%(table_name)s",
                    "uq": "uq_%(table_name)s_%(column_0_name)s",
                    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}) as batch:
            batch.add_column(sa.Column("owner_id", sa.String(80), nullable=False,
                server_default="local:legacy"))
            if table in COMPOSITE_PK:
                batch.drop_constraint(primary["name"] or f"pk_{table}", type_="primary")
                batch.create_primary_key(f"pk_{table}", ["owner_id", *primary["constrained_columns"]])
            for unique in uniques:
                unique_name = unique["name"] or f"uq_{table}_{unique['column_names'][0]}"
                batch.drop_constraint(unique_name, type_="unique")
                batch.create_unique_constraint(unique_name, ["owner_id", *unique["column_names"]])
            for foreign in foreigns:
                foreign_name = foreign["name"] or (
                    f"fk_{table}_{foreign['constrained_columns'][0]}_{foreign['referred_table']}")
                batch.drop_constraint(foreign_name, type_="foreignkey")
                batch.create_foreign_key(foreign_name, foreign["referred_table"],
                    ["owner_id", *foreign["constrained_columns"]],
                    ["owner_id", *foreign["referred_columns"]])
            batch.create_foreign_key(f"fk_{table}_owner", "resource_owners", ["owner_id"], ["owner_id"])
            for index in indexes:
                batch.drop_index(index["name"])
                batch.create_index(index["name"], ["owner_id", *index["column_names"]],
                    unique=index["unique"], **index.get("dialect_options", {}))
    if bind.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("ownership migration foreign key validation failed")


def downgrade():
    raise RuntimeError("M6.3 ownership migration is forward-only; restore the offline M6.2 backup")
