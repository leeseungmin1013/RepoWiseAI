"""Add assessment, adaptive curriculum, and unified learning journey.

Revision ID: 0004_adaptive_learning
Revises: 0003_guided_code_tour
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_adaptive_learning"
down_revision = "0003_guided_code_tour"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner_profiles",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("anonymous_key", sa.String(length=120), nullable=False),
        sa.Column("goal", sa.String(length=60), nullable=False),
        sa.Column("preferred_explanation", postgresql.JSONB(), nullable=False),
        sa.Column("pace", sa.String(length=40), nullable=False),
        sa.Column("background", postgresql.JSONB(), nullable=False),
        sa.Column("concept_mastery", postgresql.JSONB(), nullable=False),
        sa.Column("assessment_version", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_learner_profiles_anonymous_key"),
        "learner_profiles",
        ["anonymous_key"],
        unique=True,
    )

    op.create_table(
        "assessment_sessions",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("learner_profile_id", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detected_stack", postgresql.JSONB(), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("assessment_version", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["learner_profile_id"], ["learner_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_assessment_sessions_learner_profile_id"),
        "assessment_sessions",
        ["learner_profile_id"],
    )
    op.create_index(
        op.f("ix_assessment_sessions_snapshot_id"),
        "assessment_sessions",
        ["snapshot_id"],
    )
    op.create_index(op.f("ix_assessment_sessions_status"), "assessment_sessions", ["status"])
    op.create_index(
        "uq_assessment_snapshot_profile_version",
        "assessment_sessions",
        ["snapshot_id", "learner_profile_id", "assessment_version"],
        unique=True,
    )

    op.create_table(
        "assessment_responses",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("assessment_session_id", sa.String(length=48), nullable=False),
        sa.Column("item_id", sa.String(length=80), nullable=False),
        sa.Column("answer", sa.String(length=500), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score_delta", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_session_id"], ["assessment_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_assessment_responses_assessment_session_id"),
        "assessment_responses",
        ["assessment_session_id"],
    )
    op.create_index(
        op.f("ix_assessment_responses_item_id"),
        "assessment_responses",
        ["item_id"],
    )
    op.create_index(
        "uq_assessment_response_session_item",
        "assessment_responses",
        ["assessment_session_id", "item_id"],
        unique=True,
    )

    op.create_table(
        "learning_paths",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("learner_profile_id", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("goal", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("path_version", sa.String(length=60), nullable=False),
        sa.Column("generation_method", sa.String(length=80), nullable=False),
        sa.Column("coverage", postgresql.JSONB(), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_profile_id"], ["learner_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_paths_snapshot_id"), "learning_paths", ["snapshot_id"])
    op.create_index(
        op.f("ix_learning_paths_learner_profile_id"),
        "learning_paths",
        ["learner_profile_id"],
    )
    op.create_index(op.f("ix_learning_paths_status"), "learning_paths", ["status"])
    op.create_index(
        "uq_learning_path_snapshot_profile_version",
        "learning_paths",
        ["snapshot_id", "learner_profile_id", "path_version"],
        unique=True,
    )

    op.create_table(
        "learning_modules",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("path_id", sa.String(length=48), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("module_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("coverage_keys", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_modules_path_id"), "learning_modules", ["path_id"])
    op.create_index(op.f("ix_learning_modules_module_type"), "learning_modules", ["module_type"])
    op.create_index(
        "uq_learning_module_path_ordinal",
        "learning_modules",
        ["path_id", "ordinal"],
        unique=True,
    )

    op.create_table(
        "learning_lessons",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("module_id", sa.String(length=48), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("lesson_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("required_concept_ids", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("optional", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["learning_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_lessons_module_id"), "learning_lessons", ["module_id"])
    op.create_index(op.f("ix_learning_lessons_lesson_type"), "learning_lessons", ["lesson_type"])
    op.create_index(
        "uq_learning_lesson_module_ordinal",
        "learning_lessons",
        ["module_id", "ordinal"],
        unique=True,
    )

    op.create_table(
        "learning_steps",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("lesson_id", sa.String(length=48), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=60), nullable=False),
        sa.Column("chunk_id", sa.String(length=48), nullable=True),
        sa.Column("concept_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["code_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["learning_lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_steps_lesson_id"), "learning_steps", ["lesson_id"])
    op.create_index(op.f("ix_learning_steps_chunk_id"), "learning_steps", ["chunk_id"])
    op.create_index(op.f("ix_learning_steps_concept_id"), "learning_steps", ["concept_id"])
    op.create_index(
        "uq_learning_step_lesson_ordinal",
        "learning_steps",
        ["lesson_id", "ordinal"],
        unique=True,
    )

    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("learner_profile_id", sa.String(length=48), nullable=False),
        sa.Column("path_id", sa.String(length=48), nullable=False),
        sa.Column("current_module_id", sa.String(length=48), nullable=True),
        sa.Column("current_lesson_id", sa.String(length=48), nullable=True),
        sa.Column("current_step_id", sa.String(length=48), nullable=True),
        sa.Column("completed_lesson_ids", postgresql.JSONB(), nullable=False),
        sa.Column("return_stack", postgresql.JSONB(), nullable=False),
        sa.Column("current_selection", postgresql.JSONB(), nullable=False),
        sa.Column("focus_concept_ids", postgresql.JSONB(), nullable=False),
        sa.Column("teaching_state", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["current_lesson_id"], ["learning_lessons.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["current_module_id"], ["learning_modules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["current_step_id"], ["learning_steps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["learner_profile_id"], ["learner_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_sessions_snapshot_id"), "learning_sessions", ["snapshot_id"])
    op.create_index(op.f("ix_learning_sessions_path_id"), "learning_sessions", ["path_id"])
    op.create_index(
        op.f("ix_learning_sessions_learner_profile_id"),
        "learning_sessions",
        ["learner_profile_id"],
    )
    op.create_index(op.f("ix_learning_sessions_status"), "learning_sessions", ["status"])

    op.create_table(
        "journey_events",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("learning_session_id", sa.String(length=48), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("module_id", sa.String(length=48), nullable=True),
        sa.Column("lesson_id", sa.String(length=48), nullable=True),
        sa.Column("step_id", sa.String(length=48), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_journey_events_learning_session_id"),
        "journey_events",
        ["learning_session_id"],
    )
    op.create_index(op.f("ix_journey_events_event_type"), "journey_events", ["event_type"])
    op.create_index(
        "ix_journey_event_session_created",
        "journey_events",
        ["learning_session_id", "created_at"],
    )

    op.create_table(
        "remediation_branches",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("learning_session_id", sa.String(length=48), nullable=False),
        sa.Column("source_lesson_id", sa.String(length=48), nullable=False),
        sa.Column("source_step_id", sa.String(length=48), nullable=True),
        sa.Column("mode", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("concept_ids", postgresql.JSONB(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("return_lesson_id", sa.String(length=48), nullable=False),
        sa.Column("return_step_id", sa.String(length=48), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_lesson_id"], ["learning_lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_step_id"], ["learning_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_remediation_branches_learning_session_id"),
        "remediation_branches",
        ["learning_session_id"],
    )
    op.create_index(
        op.f("ix_remediation_branches_source_lesson_id"),
        "remediation_branches",
        ["source_lesson_id"],
    )
    op.create_index(op.f("ix_remediation_branches_mode"), "remediation_branches", ["mode"])
    op.create_index(op.f("ix_remediation_branches_status"), "remediation_branches", ["status"])

    op.create_table(
        "explanation_artifacts",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("chunk_id", sa.String(length=48), nullable=False),
        sa.Column("artifact_type", sa.String(length=60), nullable=False),
        sa.Column("depth_band", sa.String(length=40), nullable=False),
        sa.Column("segments", postgresql.JSONB(), nullable=False),
        sa.Column("source_hash", sa.String(length=80), nullable=False),
        sa.Column("segmenter_version", sa.String(length=60), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["code_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_explanation_artifacts_snapshot_id"), "explanation_artifacts", ["snapshot_id"]
    )
    op.create_index(
        op.f("ix_explanation_artifacts_chunk_id"), "explanation_artifacts", ["chunk_id"]
    )
    op.create_index(
        "uq_explanation_chunk_type_depth_version",
        "explanation_artifacts",
        ["chunk_id", "artifact_type", "depth_band", "segmenter_version"],
        unique=True,
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("concept_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("publisher", sa.String(length=160), nullable=False),
        sa.Column("canonical_url", sa.String(length=1000), nullable=False),
        sa.Column("source_tier", sa.String(length=40), nullable=False),
        sa.Column("difficulty", sa.String(length=40), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_sources_concept_id"), "knowledge_sources", ["concept_id"])
    op.create_index(
        "uq_knowledge_source_concept_url",
        "knowledge_sources",
        ["concept_id", "canonical_url"],
        unique=True,
    )

    op.add_column(
        "chat_sessions", sa.Column("learning_session_id", sa.String(length=48), nullable=True)
    )
    op.create_foreign_key(
        "fk_chat_sessions_learning_session_id",
        "chat_sessions",
        "learning_sessions",
        ["learning_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_chat_sessions_learning_session_id"),
        "chat_sessions",
        ["learning_session_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_sessions_learning_session_id"), table_name="chat_sessions")
    op.drop_constraint("fk_chat_sessions_learning_session_id", "chat_sessions", type_="foreignkey")
    op.drop_column("chat_sessions", "learning_session_id")
    op.drop_table("knowledge_sources")
    op.drop_table("explanation_artifacts")
    op.drop_table("remediation_branches")
    op.drop_table("journey_events")
    op.drop_table("learning_sessions")
    op.drop_table("learning_steps")
    op.drop_table("learning_lessons")
    op.drop_table("learning_modules")
    op.drop_table("learning_paths")
    op.drop_table("assessment_responses")
    op.drop_table("assessment_sessions")
    op.drop_table("learner_profiles")
