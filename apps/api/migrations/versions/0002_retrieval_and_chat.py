"""Add hierarchical chunks, hybrid retrieval traces, and chat sessions.

Revision ID: 0002_retrieval_and_chat
Revises: 0001_initial
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0002_retrieval_and_chat"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "repository_snapshots",
        sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "repository_snapshots",
        sa.Column(
            "embedding_model",
            sa.String(length=120),
            server_default="local-hash-v1",
            nullable=False,
        ),
    )

    op.create_table(
        "code_chunks",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("file_id", sa.String(length=48), nullable=False),
        sa.Column("symbol_id", sa.String(length=48), nullable=True),
        sa.Column("parent_chunk_id", sa.String(length=48), nullable=True),
        sa.Column("chunk_type", sa.String(length=40), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1400), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(search_text, ''))", persisted=True),
            nullable=True,
        ),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_chunk_id"], ["code_chunks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_code_chunks_file_id"), "code_chunks", ["file_id"])
    op.create_index(
        op.f("ix_code_chunks_parent_chunk_id"), "code_chunks", ["parent_chunk_id"]
    )
    op.create_index(op.f("ix_code_chunks_snapshot_id"), "code_chunks", ["snapshot_id"])
    op.create_index(op.f("ix_code_chunks_symbol_id"), "code_chunks", ["symbol_id"])
    op.create_index(op.f("ix_code_chunks_chunk_type"), "code_chunks", ["chunk_type"])
    op.create_index(
        "ix_chunk_snapshot_file_line", "code_chunks", ["snapshot_id", "file_id", "start_line"]
    )
    op.create_index(
        "ix_chunk_snapshot_type", "code_chunks", ["snapshot_id", "chunk_type"]
    )
    op.create_index(
        "ix_chunk_search_vector", "code_chunks", ["search_vector"], postgresql_using="gin"
    )
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "code_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("goal", sa.String(length=500), nullable=True),
        sa.Column("preferred_style", sa.String(length=40), nullable=False),
        sa.Column("teaching_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_selection", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_sessions_snapshot_id"), "chat_sessions", ["snapshot_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("session_id", sa.String(length=48), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_messages_role"), "chat_messages", ["role"])
    op.create_index(op.f("ix_chat_messages_session_id"), "chat_messages", ["session_id"])

    op.create_table(
        "retrieval_runs",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("session_id", sa.String(length=48), nullable=False),
        sa.Column("message_id", sa.String(length=48), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("resolved_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("retrieval_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("index_version", sa.String(length=60), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_retrieval_runs_intent"), "retrieval_runs", ["intent"])
    op.create_index(op.f("ix_retrieval_runs_message_id"), "retrieval_runs", ["message_id"])
    op.create_index(op.f("ix_retrieval_runs_session_id"), "retrieval_runs", ["session_id"])

    op.create_table(
        "retrieval_candidates",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("retrieval_run_id", sa.String(length=48), nullable=False),
        sa.Column("evidence_id", sa.String(length=48), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=48), nullable=False),
        sa.Column("retriever", sa.String(length=40), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("rrf_score", sa.Float(), nullable=False),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["retrieval_run_id"], ["retrieval_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["code_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_retrieval_candidates_evidence_id"),
        "retrieval_candidates",
        ["evidence_id"],
    )
    op.create_index(
        op.f("ix_retrieval_candidates_retrieval_run_id"),
        "retrieval_candidates",
        ["retrieval_run_id"],
    )
    op.create_index(
        op.f("ix_retrieval_candidates_retriever"), "retrieval_candidates", ["retriever"]
    )
    op.create_index(
        op.f("ix_retrieval_candidates_source_id"), "retrieval_candidates", ["source_id"]
    )
    op.create_index(
        "ix_candidate_run_rank",
        "retrieval_candidates",
        ["retrieval_run_id", "retriever", "rank"],
    )


def downgrade() -> None:
    op.drop_table("retrieval_candidates")
    op.drop_table("retrieval_runs")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("code_chunks")
    op.drop_column("repository_snapshots", "embedding_model")
    op.drop_column("repository_snapshots", "chunk_count")
    op.execute("DROP EXTENSION IF EXISTS vector")
