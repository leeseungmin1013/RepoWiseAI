"""Add grounded checkpoint activities and mastery event ledger.

Revision ID: 0005_grounded_activities
Revises: 0004_adaptive_learning
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_grounded_activities"
down_revision = "0004_adaptive_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_activities",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("step_id", sa.String(length=48), nullable=False),
        sa.Column("activity_type", sa.String(length=60), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("choices", postgresql.JSONB(), nullable=False),
        sa.Column("answer_key", sa.String(length=80), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("concept_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("source_hash", sa.String(length=80), nullable=False),
        sa.Column("generator_version", sa.String(length=60), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["step_id"], ["learning_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_learning_activities_step_id"),
        "learning_activities",
        ["step_id"],
    )
    op.create_index(
        op.f("ix_learning_activities_activity_type"),
        "learning_activities",
        ["activity_type"],
    )
    op.create_index(
        "uq_learning_activity_step_type_version",
        "learning_activities",
        ["step_id", "activity_type", "generator_version"],
        unique=True,
    )

    op.create_table(
        "activity_attempts",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("learning_session_id", sa.String(length=48), nullable=False),
        sa.Column("activity_id", sa.String(length=48), nullable=False),
        sa.Column("selected_choice_id", sa.String(length=80), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("score_delta", sa.Float(), nullable=False),
        sa.Column("feedback", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["learning_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activity_attempts_learning_session_id"),
        "activity_attempts",
        ["learning_session_id"],
    )
    op.create_index(
        op.f("ix_activity_attempts_activity_id"),
        "activity_attempts",
        ["activity_id"],
    )
    op.create_index(
        op.f("ix_activity_attempts_is_correct"),
        "activity_attempts",
        ["is_correct"],
    )
    op.create_index(
        "ix_activity_attempt_session_created",
        "activity_attempts",
        ["learning_session_id", "created_at"],
    )

    op.create_table(
        "mastery_events",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("learner_profile_id", sa.String(length=48), nullable=False),
        sa.Column("learning_session_id", sa.String(length=48), nullable=True),
        sa.Column("concept_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("source_type", sa.String(length=60), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=True),
        sa.Column("previous_score", sa.Float(), nullable=False),
        sa.Column("new_score", sa.Float(), nullable=False),
        sa.Column("previous_confidence", sa.Float(), nullable=False),
        sa.Column("new_confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_profile_id"], ["learner_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mastery_events_learner_profile_id"),
        "mastery_events",
        ["learner_profile_id"],
    )
    op.create_index(
        op.f("ix_mastery_events_learning_session_id"),
        "mastery_events",
        ["learning_session_id"],
    )
    op.create_index(
        op.f("ix_mastery_events_concept_id"),
        "mastery_events",
        ["concept_id"],
    )
    op.create_index(
        op.f("ix_mastery_events_event_type"),
        "mastery_events",
        ["event_type"],
    )
    op.create_index(
        op.f("ix_mastery_events_source_type"),
        "mastery_events",
        ["source_type"],
    )
    op.create_index(
        "ix_mastery_profile_concept_created",
        "mastery_events",
        ["learner_profile_id", "concept_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("mastery_events")
    op.drop_table("activity_attempts")
    op.drop_table("learning_activities")
