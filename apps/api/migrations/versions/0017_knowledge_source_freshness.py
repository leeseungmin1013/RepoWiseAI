"""Track official learning source freshness without losing last-known-good state."""

import sqlalchemy as sa
from alembic import op

revision = "0017_knowledge_source_freshness"
down_revision = "0016_backfill_and_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column(
            "freshness_status",
            sa.String(length=32),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column(
        "knowledge_sources", sa.Column("last_check_status", sa.Integer(), nullable=True)
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("last_check_error", sa.String(length=240), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_sources", "last_check_error")
    op.drop_column("knowledge_sources", "last_check_status")
    op.drop_column("knowledge_sources", "freshness_status")
