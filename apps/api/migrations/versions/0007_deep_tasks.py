"""Add asynchronous deep learning tasks.

Revision ID: 0007_deep_tasks
Revises: 0006_concept_graph
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_deep_tasks"
down_revision = "0006_concept_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deep_tasks",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("learning_session_id", sa.String(length=48), nullable=False),
        sa.Column("chat_session_id", sa.String(length=48), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("modality", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("selection", postgresql.JSONB(), nullable=False),
        sa.Column("teaching_style", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("rq_job_id", sa.String(length=64), nullable=True),
        sa.Column("result_message_id", sa.String(length=48), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(), nullable=True),
        sa.Column("model_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deep_task_learning_status_created",
        "deep_tasks",
        ["learning_session_id", "status", "created_at"],
    )
    op.create_index(
        "uq_deep_task_learning_idempotency",
        "deep_tasks",
        ["learning_session_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_deep_tasks_learning_session_id"),
        "deep_tasks",
        ["learning_session_id"],
    )
    op.create_index(op.f("ix_deep_tasks_chat_session_id"), "deep_tasks", ["chat_session_id"])
    op.create_index(op.f("ix_deep_tasks_kind"), "deep_tasks", ["kind"])
    op.create_index(op.f("ix_deep_tasks_status"), "deep_tasks", ["status"])
    op.create_index(op.f("ix_deep_tasks_rq_job_id"), "deep_tasks", ["rq_job_id"])
    op.create_index(op.f("ix_deep_tasks_result_message_id"), "deep_tasks", ["result_message_id"])


def downgrade() -> None:
    op.drop_table("deep_tasks")
