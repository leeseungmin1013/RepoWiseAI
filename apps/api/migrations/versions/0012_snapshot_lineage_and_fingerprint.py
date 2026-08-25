"""Add snapshot identity, lineage and analysis job ownership."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_snapshot_lineage_and_fingerprint"
down_revision = "0011_resource_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Descriptive revision identifiers exceed Alembic's historical VARCHAR(32)
    # default. Expand it before Alembic records this revision.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.add_column("repository_snapshots", sa.Column("analysis_fingerprint", sa.String(80)))
    op.add_column("repository_snapshots", sa.Column("base_snapshot_id", sa.String(48)))
    op.add_column(
        "repository_snapshots",
        sa.Column("reuse_mode", sa.String(32), nullable=False, server_default="full"),
    )
    op.add_column("repository_snapshots", sa.Column("manifest_hash", sa.String(80)))
    op.add_column(
        "repository_snapshots",
        sa.Column(
            "change_summary",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("repository_snapshots", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column("repository_snapshots", sa.Column("ready_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "repository_snapshots_base_snapshot_id_fkey",
        "repository_snapshots",
        "repository_snapshots",
        ["base_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_snapshot_identity_lookup",
        "repository_snapshots",
        ["repository_id", "commit_sha", "analysis_fingerprint"],
    )
    op.create_index(
        "ix_snapshot_repository_branch_created",
        "repository_snapshots",
        ["repository_id", "branch", sa.text("created_at DESC")],
    )
    op.add_column("analysis_jobs", sa.Column("requested_by_user_id", sa.String(128)))
    op.add_column("analysis_jobs", sa.Column("organization_id", sa.String(48)))
    op.add_column("analysis_jobs", sa.Column("base_snapshot_id", sa.String(48)))
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "reuse_metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("analysis_jobs", sa.Column("cost_reservation_id", sa.String(48)))
    op.create_foreign_key(
        "analysis_jobs_user_id_fkey",
        "analysis_jobs",
        "users",
        ["requested_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "analysis_jobs_organization_id_fkey",
        "analysis_jobs",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "analysis_jobs_base_snapshot_id_fkey",
        "analysis_jobs",
        "repository_snapshots",
        ["base_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    for column in (
        "cost_reservation_id",
        "reuse_metrics",
        "base_snapshot_id",
        "organization_id",
        "requested_by_user_id",
    ):
        op.drop_column("analysis_jobs", column)
    op.drop_index("ix_snapshot_repository_branch_created", table_name="repository_snapshots")
    op.drop_index("ix_snapshot_identity_lookup", table_name="repository_snapshots")
    op.drop_constraint(
        "repository_snapshots_base_snapshot_id_fkey", "repository_snapshots", type_="foreignkey"
    )
    for column in (
        "ready_at",
        "resolved_at",
        "change_summary",
        "manifest_hash",
        "reuse_mode",
        "base_snapshot_id",
        "analysis_fingerprint",
    ):
        op.drop_column("repository_snapshots", column)
