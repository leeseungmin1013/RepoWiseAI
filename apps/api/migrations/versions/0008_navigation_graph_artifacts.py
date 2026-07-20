"""Add semantic edge metadata and navigation artifacts.

Revision ID: 0008_navigation_graph_artifacts
Revises: 0007_deep_tasks
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_navigation_graph_artifacts"
down_revision = "0007_deep_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "symbol_edges",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "navigation_artifacts",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("artifact_type", sa.String(length=60), nullable=False),
        sa.Column("artifact_key", sa.String(length=500), nullable=False),
        sa.Column("artifact_version", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "confidence_summary",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "generation_metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_navigation_artifacts_snapshot_id"),
        "navigation_artifacts",
        ["snapshot_id"],
    )
    op.create_index(
        op.f("ix_navigation_artifacts_artifact_type"),
        "navigation_artifacts",
        ["artifact_type"],
    )
    op.create_index(
        op.f("ix_navigation_artifacts_artifact_version"),
        "navigation_artifacts",
        ["artifact_version"],
    )
    op.create_index(
        op.f("ix_navigation_artifacts_status"),
        "navigation_artifacts",
        ["status"],
    )
    op.create_index(
        "uq_navigation_artifact_snapshot_type_key_version",
        "navigation_artifacts",
        ["snapshot_id", "artifact_type", "artifact_key", "artifact_version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("navigation_artifacts")
    op.drop_column("symbol_edges", "metadata_json")
