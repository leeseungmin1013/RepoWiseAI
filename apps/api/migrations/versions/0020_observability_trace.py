"""Persist cross-stage observability trace identifiers and activity latency."""

import sqlalchemy as sa
from alembic import op

revision = "0020_observability_trace"
down_revision = "0019_activity_difficulty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("analysis_jobs", "deep_tasks", "retrieval_runs", "activity_attempts"):
        op.add_column(table, sa.Column("trace_id", sa.String(length=128), nullable=True))
        op.create_index(op.f(f"ix_{table}_trace_id"), table, ["trace_id"])
    op.add_column(
        "activity_attempts",
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("activity_attempts", "latency_ms")
    for table in reversed(("analysis_jobs", "deep_tasks", "retrieval_runs", "activity_attempts")):
        op.drop_index(op.f(f"ix_{table}_trace_id"), table_name=table)
        op.drop_column(table, "trace_id")