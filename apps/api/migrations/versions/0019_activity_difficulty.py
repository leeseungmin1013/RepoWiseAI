"""Add adaptive difficulty to grounded learning activities."""

import sqlalchemy as sa
from alembic import op

revision = "0019_activity_difficulty"
down_revision = "0018_assessment_timeout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_activities",
        sa.Column(
            "difficulty",
            sa.String(length=32),
            nullable=False,
            server_default="beginner",
        ),
    )
    op.create_index(
        op.f("ix_learning_activities_difficulty"),
        "learning_activities",
        ["difficulty"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_learning_activities_difficulty"),
        table_name="learning_activities",
    )
    op.drop_column("learning_activities", "difficulty")