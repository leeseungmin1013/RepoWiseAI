"""Add navigation context and navigation-scoped deep tasks.

Revision ID: 0009_navigation_change_briefs
Revises: 0008_navigation_graph_artifacts
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_navigation_change_briefs"
down_revision = "0008_navigation_graph_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "navigation_context",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "deep_tasks",
        sa.Column(
            "context_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        "deep_tasks_learning_session_id_fkey", "deep_tasks", type_="foreignkey"
    )
    op.alter_column(
        "deep_tasks",
        "learning_session_id",
        existing_type=sa.String(length=48),
        nullable=True,
    )
    op.create_foreign_key(
        "deep_tasks_learning_session_id_fkey",
        "deep_tasks",
        "learning_sessions",
        ["learning_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_deep_task_chat_idempotency",
        "deep_tasks",
        ["chat_session_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_deep_task_chat_idempotency", table_name="deep_tasks")
    op.drop_constraint(
        "deep_tasks_learning_session_id_fkey", "deep_tasks", type_="foreignkey"
    )
    op.alter_column(
        "deep_tasks",
        "learning_session_id",
        existing_type=sa.String(length=48),
        nullable=False,
    )
    op.create_foreign_key(
        "deep_tasks_learning_session_id_fkey",
        "deep_tasks",
        "learning_sessions",
        ["learning_session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("deep_tasks", "context_json")
    op.drop_column("chat_sessions", "navigation_context")
