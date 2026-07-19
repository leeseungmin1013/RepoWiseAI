"""Add versioned concept and prerequisite graph.

Revision ID: 0006_concept_graph
Revises: 0005_grounded_activities
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_concept_graph"
down_revision = "0005_grounded_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("difficulty", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("graph_version", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_concepts_domain"), "concepts", ["domain"])
    op.create_index(op.f("ix_concepts_difficulty"), "concepts", ["difficulty"])
    op.create_index(op.f("ix_concepts_graph_version"), "concepts", ["graph_version"])

    op.create_table(
        "concept_edges",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("source_concept_id", sa.String(length=120), nullable=False),
        sa.Column("target_concept_id", sa.String(length=120), nullable=False),
        sa.Column("relation", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("graph_version", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_concept_edges_source_concept_id"),
        "concept_edges",
        ["source_concept_id"],
    )
    op.create_index(
        op.f("ix_concept_edges_target_concept_id"),
        "concept_edges",
        ["target_concept_id"],
    )
    op.create_index(op.f("ix_concept_edges_relation"), "concept_edges", ["relation"])
    op.create_index(
        op.f("ix_concept_edges_graph_version"),
        "concept_edges",
        ["graph_version"],
    )
    op.create_index(
        "uq_concept_edge_version_relation",
        "concept_edges",
        ["source_concept_id", "target_concept_id", "relation", "graph_version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("concept_edges")
    op.drop_table("concepts")
