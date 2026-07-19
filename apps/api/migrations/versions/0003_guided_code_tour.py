"""Add guided code tour paths, sessions, and progress events.

Revision ID: 0003_guided_code_tour
Revises: 0002_retrieval_and_chat
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_guided_code_tour"
down_revision = "0002_retrieval_and_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guided_paths",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=40), nullable=False),
        sa.Column("path_version", sa.String(length=60), nullable=False),
        sa.Column("generation_method", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_guided_paths_snapshot_id"), "guided_paths", ["snapshot_id"])
    op.create_index(
        "uq_guided_path_snapshot_version",
        "guided_paths",
        ["snapshot_id", "path_version"],
        unique=True,
    )

    op.create_table(
        "guided_steps",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("path_id", sa.String(length=48), nullable=False),
        sa.Column("chunk_id", sa.String(length=48), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("learning_objective", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "concept_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "checkpoint",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["code_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["path_id"], ["guided_paths.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_guided_steps_chunk_id"), "guided_steps", ["chunk_id"])
    op.create_index(op.f("ix_guided_steps_path_id"), "guided_steps", ["path_id"])
    op.create_index(
        "uq_guided_step_path_ordinal",
        "guided_steps",
        ["path_id", "ordinal"],
        unique=True,
    )

    op.create_table(
        "guided_tour_sessions",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("path_id", sa.String(length=48), nullable=False),
        sa.Column("preferred_style", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step_ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "completed_step_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "needs_help_step_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["path_id"], ["guided_paths.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_guided_tour_sessions_path_id"), "guided_tour_sessions", ["path_id"]
    )
    op.create_index(
        op.f("ix_guided_tour_sessions_status"), "guided_tour_sessions", ["status"]
    )

    op.create_table(
        "guided_step_events",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("tour_session_id", sa.String(length=48), nullable=False),
        sa.Column("step_id", sa.String(length=48), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["step_id"], ["guided_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tour_session_id"], ["guided_tour_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_guided_step_events_event_type"), "guided_step_events", ["event_type"]
    )
    op.create_index(
        op.f("ix_guided_step_events_step_id"), "guided_step_events", ["step_id"]
    )
    op.create_index(
        op.f("ix_guided_step_events_tour_session_id"),
        "guided_step_events",
        ["tour_session_id"],
    )
    op.create_index(
        "ix_guided_event_session_created",
        "guided_step_events",
        ["tour_session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("guided_step_events")
    op.drop_table("guided_tour_sessions")
    op.drop_table("guided_steps")
    op.drop_table("guided_paths")
