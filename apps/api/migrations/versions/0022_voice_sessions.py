"""Persist realtime voice sessions and final turns."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_voice_sessions"
down_revision = "0021_roadmap_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("learning_session_id", sa.String(length=48), nullable=False),
        sa.Column("chat_session_id", sa.String(length=48), nullable=False),
        sa.Column("provider_call_id", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="connecting"),
        sa.Column("realtime_model", sa.String(length=120), nullable=False),
        sa.Column(
            "prompt_version", sa.String(length=60), nullable=False, server_default="voice-tutor-v2"
        ),
        sa.Column(
            "interaction_mode", sa.String(length=32), nullable=False, server_default="push_to_talk"
        ),
        sa.Column(
            "transcript_storage_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnect_reason", sa.String(length=240), nullable=True),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_call_id"),
    )
    op.create_index(
        "ix_voice_session_learning_started",
        "voice_sessions",
        ["learning_session_id", "started_at"],
    )
    op.create_index(
        "uq_voice_session_one_live_per_learning_session",
        "voice_sessions",
        ["learning_session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('connecting', 'active', 'reconnecting')"),
    )
    op.create_index(
        op.f("ix_voice_sessions_learning_session_id"),
        "voice_sessions",
        ["learning_session_id"],
    )
    op.create_index(
        op.f("ix_voice_sessions_chat_session_id"),
        "voice_sessions",
        ["chat_session_id"],
    )
    op.create_index(op.f("ix_voice_sessions_status"), "voice_sessions", ["status"])

    op.create_table(
        "voice_turns",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("voice_session_id", sa.String(length=48), nullable=False),
        sa.Column("chat_message_id", sa.String(length=48), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column(
            "transcript_status", sa.String(length=32), nullable=False, server_default="final"
        ),
        sa.Column("intent", sa.String(length=80), nullable=True),
        sa.Column("route", sa.String(length=80), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column("provider_call_id", sa.String(length=160), nullable=True),
        sa.Column(
            "context_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("interrupted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("audio_duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("speech_end_to_ack_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_audio_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["voice_session_id"], ["voice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_voice_turn_session_created",
        "voice_turns",
        ["voice_session_id", "created_at"],
    )
    op.create_index(
        "uq_voice_turn_session_provider_call",
        "voice_turns",
        ["voice_session_id", "provider_call_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_voice_turns_voice_session_id"),
        "voice_turns",
        ["voice_session_id"],
    )
    op.create_index(
        op.f("ix_voice_turns_chat_message_id"),
        "voice_turns",
        ["chat_message_id"],
    )
    op.create_index(op.f("ix_voice_turns_route"), "voice_turns", ["route"])


def downgrade() -> None:
    op.drop_table("voice_turns")
    op.drop_table("voice_sessions")
