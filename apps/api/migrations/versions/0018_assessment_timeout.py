"""Add assessment deadline and timeout audit timestamps."""

import sqlalchemy as sa
from alembic import op

revision = "0018_assessment_timeout"
down_revision = "0017_knowledge_source_freshness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assessment_sessions",
        sa.Column("timed_out_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE assessment_sessions
        SET expires_at = created_at + interval '15 minutes'
        WHERE expires_at IS NULL
        """
    )
    op.alter_column("assessment_sessions", "expires_at", nullable=False)


def downgrade() -> None:
    op.drop_column("assessment_sessions", "timed_out_at")
    op.drop_column("assessment_sessions", "expires_at")