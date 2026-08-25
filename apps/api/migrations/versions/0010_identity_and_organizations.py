"""Add users, organizations, memberships and preferences."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_identity_and_organizations"
down_revision = "0009_navigation_change_briefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(200)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="personal"),
        sa.Column(
            "owner_user_id",
            sa.String(128),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("uq_organization_slug", "organizations", ["slug"], unique=True)
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_membership_organization_user",
        "organization_memberships",
        ["organization_id", "user_id"],
        unique=True,
    )
    op.create_table(
        "organization_repositories",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(48),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.String(48),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("added_by", sa.String(128), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("visibility", sa.String(32), nullable=False, server_default="organization"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_organization_repository",
        "organization_repositories",
        ["organization_id", "repository_id"],
        unique=True,
    )
    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id",
            sa.String(128),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "preferences_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_table("organization_repositories")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
    op.drop_table("users")
