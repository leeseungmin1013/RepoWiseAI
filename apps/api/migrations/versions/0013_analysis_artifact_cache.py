"""Add content-addressed analysis artifacts and manifests."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0013_analysis_artifact_cache"
down_revision = "0012_snapshot_lineage_and_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_blobs",
        sa.Column("content_hash", sa.String(80), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "file_parse_artifacts",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "content_hash",
            sa.String(80),
            sa.ForeignKey("source_blobs.content_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("language", sa.String(40), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_parse_artifact_identity",
        "file_parse_artifacts",
        ["content_hash", "language", "parser_version"],
        unique=True,
    )
    op.create_table(
        "chunk_templates",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "content_hash",
            sa.String(80),
            sa.ForeignKey("source_blobs.content_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunker_fingerprint", sa.String(80), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_chunk_template_identity",
        "chunk_templates",
        ["content_hash", "chunker_fingerprint"],
        unique=True,
    )
    op.create_table(
        "embedding_cache",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("text_hash", sa.String(80), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "token_usage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_embedding_cache_identity",
        "embedding_cache",
        ["provider", "model", "dimensions", "prompt_version", "text_hash"],
        unique=True,
    )
    op.create_index(
        "ix_embedding_cache_hnsw",
        "embedding_cache",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "snapshot_manifests",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(48),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("language", sa.String(40), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "uq_snapshot_manifest_path", "snapshot_manifests", ["snapshot_id", "path"], unique=True
    )
    op.create_table(
        "snapshot_file_lineage",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(48),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id", sa.String(48), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("base_file_id", sa.String(48), sa.ForeignKey("files.id", ondelete="SET NULL")),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("previous_path", sa.String(1000)),
        sa.Column("change_kind", sa.String(32), nullable=False),
        sa.Column("reused_parse", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reused_chunks", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reused_embeddings", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_snapshot_lineage_path", "snapshot_file_lineage", ["snapshot_id", "path"], unique=True
    )
    op.add_column("navigation_artifacts", sa.Column("dependency_fingerprint", sa.String(80)))


def downgrade() -> None:
    op.drop_column("navigation_artifacts", "dependency_fingerprint")
    for table in (
        "snapshot_file_lineage",
        "snapshot_manifests",
        "embedding_cache",
        "chunk_templates",
        "file_parse_artifacts",
        "source_blobs",
    ):
        op.drop_table(table)
