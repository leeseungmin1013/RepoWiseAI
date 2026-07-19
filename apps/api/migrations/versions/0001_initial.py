"""Create repository analysis tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("owner", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_repository_provider_owner_name",
        "repositories",
        ["provider", "owner", "name"],
        unique=True,
    )

    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("repository_id", sa.String(length=48), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("index_version", sa.String(length=32), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("symbol_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_repository_snapshots_commit_sha"),
        "repository_snapshots",
        ["commit_sha"],
    )
    op.create_index(
        op.f("ix_repository_snapshots_repository_id"),
        "repository_snapshots",
        ["repository_id"],
    )
    op.create_index(
        op.f("ix_repository_snapshots_status"), "repository_snapshots", ["status"]
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analysis_jobs_snapshot_id"), "analysis_jobs", ["snapshot_id"])
    op.create_index(op.f("ix_analysis_jobs_status"), "analysis_jobs", ["status"])

    op.create_table(
        "files",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("is_documentation", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_files_snapshot_id"), "files", ["snapshot_id"])
    op.create_index("uq_file_snapshot_path", "files", ["snapshot_id", "path"], unique=True)

    op.create_table(
        "symbols",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("file_id", sa.String(length=48), nullable=False),
        sa.Column("qualified_name", sa.String(length=1200), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_symbols_display_name"), "symbols", ["display_name"])
    op.create_index(op.f("ix_symbols_file_id"), "symbols", ["file_id"])
    op.create_index(op.f("ix_symbols_snapshot_id"), "symbols", ["snapshot_id"])
    op.create_index("ix_symbol_file_line", "symbols", ["file_id", "start_line"])
    op.create_index("ix_symbol_snapshot_name", "symbols", ["snapshot_id", "display_name"])

    op.create_table(
        "symbol_edges",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("snapshot_id", sa.String(length=48), nullable=False),
        sa.Column("source_file_id", sa.String(length=48), nullable=False),
        sa.Column("source_symbol_id", sa.String(length=48), nullable=True),
        sa.Column("target_symbol_id", sa.String(length=48), nullable=True),
        sa.Column("target_path", sa.String(length=1200), nullable=True),
        sa.Column("relation", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("analysis_method", sa.String(length=80), nullable=False),
        sa.Column("source_start_line", sa.Integer(), nullable=True),
        sa.Column("source_end_line", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["source_file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_symbol_id"], ["symbols.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["target_symbol_id"], ["symbols.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edge_snapshot_relation", "symbol_edges", ["snapshot_id", "relation"])
    op.create_index(op.f("ix_symbol_edges_snapshot_id"), "symbol_edges", ["snapshot_id"])
    op.create_index(op.f("ix_symbol_edges_source_file_id"), "symbol_edges", ["source_file_id"])
    op.create_index(
        op.f("ix_symbol_edges_source_symbol_id"), "symbol_edges", ["source_symbol_id"]
    )
    op.create_index(
        op.f("ix_symbol_edges_target_symbol_id"), "symbol_edges", ["target_symbol_id"]
    )


def downgrade() -> None:
    op.drop_table("symbol_edges")
    op.drop_table("symbols")
    op.drop_table("files")
    op.drop_table("analysis_jobs")
    op.drop_table("repository_snapshots")
    op.drop_table("repositories")
