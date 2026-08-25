"""Add tenant-scoped exact and semantic chat cache."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0014_semantic_cache"
down_revision = "0013_analysis_artifact_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "semantic_cache_entries",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("cache_kind", sa.String(24), nullable=False),
        sa.Column("scope", sa.String(24), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.String(48),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("compatible_evidence_fingerprint", sa.String(80), nullable=False),
        sa.Column("exact_key", sa.String(80), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column("query_embedding", Vector(768)),
        sa.Column("intent", sa.String(40), nullable=False),
        sa.Column("context_fingerprint", sa.String(80), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("prompt_version", sa.String(80)),
        sa.Column("index_version", sa.String(80), nullable=False),
        sa.Column("source_run_id", sa.String(48)),
        sa.Column("source_message_id", sa.String(48)),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.Column("quality_status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_semantic_cache_exact_scope",
        "semantic_cache_entries",
        ["cache_kind", "scope", "scope_id", "exact_key"],
        unique=True,
    )
    op.create_index(
        "ix_semantic_cache_scope_snapshot_intent",
        "semantic_cache_entries",
        ["scope", "scope_id", "snapshot_id", "intent", "created_at"],
    )
    op.create_index(
        "ix_semantic_cache_embedding_hnsw",
        "semantic_cache_entries",
        ["query_embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"query_embedding": "vector_cosine_ops"},
    )
    op.add_column("retrieval_runs", sa.Column("cache_source_run_id", sa.String(48)))
    op.add_column(
        "retrieval_runs",
        sa.Column("cache_status", sa.String(32), nullable=False, server_default="miss"),
    )
    op.add_column("retrieval_runs", sa.Column("cache_similarity", sa.Float()))
    op.create_foreign_key(
        "retrieval_runs_cache_source_run_id_fkey",
        "retrieval_runs",
        "retrieval_runs",
        ["cache_source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "retrieval_runs_cache_source_run_id_fkey", "retrieval_runs", type_="foreignkey"
    )
    for column in ("cache_similarity", "cache_status", "cache_source_run_id"):
        op.drop_column("retrieval_runs", column)
    op.drop_table("semantic_cache_entries")
