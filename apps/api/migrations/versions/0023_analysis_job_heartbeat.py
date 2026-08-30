"""Track repository analysis worker heartbeat and forward progress."""

import sqlalchemy as sa
from alembic import op

revision = "0023_analysis_job_heartbeat"
down_revision = "0022_voice_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "analysis_jobs",
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_analysis_jobs_heartbeat_at"),
        "analysis_jobs",
        ["heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_jobs_heartbeat_at"), table_name="analysis_jobs")
    op.drop_column("analysis_jobs", "last_progress_at")
    op.drop_column("analysis_jobs", "heartbeat_at")
