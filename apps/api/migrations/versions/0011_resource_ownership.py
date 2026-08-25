"""Add nullable ownership roots for expand/backfill migration."""

import sqlalchemy as sa
from alembic import op

revision = "0011_resource_ownership"
down_revision = "0010_identity_and_organizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("learner_profiles", "chat_sessions"):
        op.add_column(table, sa.Column("user_id", sa.String(128), nullable=True))
        op.add_column(table, sa.Column("organization_id", sa.String(48), nullable=True))
        op.create_foreign_key(
            f"{table}_user_id_fkey", table, "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        op.create_foreign_key(
            f"{table}_organization_id_fkey",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    op.add_column("deep_tasks", sa.Column("user_id", sa.String(128), nullable=True))
    op.add_column("deep_tasks", sa.Column("organization_id", sa.String(48), nullable=True))
    op.add_column("deep_tasks", sa.Column("cost_reservation_id", sa.String(48), nullable=True))
    op.create_foreign_key(
        "deep_tasks_user_id_fkey", "deep_tasks", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "deep_tasks_organization_id_fkey",
        "deep_tasks",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    for table in ("deep_tasks", "chat_sessions", "learner_profiles"):
        for column in ("cost_reservation_id",) if table == "deep_tasks" else ():
            op.drop_column(table, column)
        op.drop_constraint(f"{table}_organization_id_fkey", table, type_="foreignkey")
        op.drop_constraint(f"{table}_user_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
        op.drop_column(table, "user_id")
