"""Add approval-gated learning roadmap proposals."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_roadmap_proposals"
down_revision = "0020_observability_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roadmap_proposals",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("learning_session_id", sa.String(length=48), nullable=False),
        sa.Column("path_id", sa.String(length=48), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
        sa.Column(
            "request_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "candidates_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "selection_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "diff_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "verification_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_roadmap_proposal_session_created",
        "roadmap_proposals",
        ["learning_session_id", "created_at"],
    )
    op.create_index(
        op.f("ix_roadmap_proposals_learning_session_id"),
        "roadmap_proposals",
        ["learning_session_id"],
    )
    op.create_index(op.f("ix_roadmap_proposals_path_id"), "roadmap_proposals", ["path_id"])
    op.create_index(op.f("ix_roadmap_proposals_status"), "roadmap_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("roadmap_proposals")
