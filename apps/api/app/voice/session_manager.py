from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.model_routing import ModelRoutingPolicy
from app.models import (
    LearningPath,
    LearningSession,
    VoiceSession,
    VoiceTurn,
    utc_now,
)


def create_voice_session(
    db: Session,
    *,
    learning_session: LearningSession,
    chat_session_id: str,
    provider_call_id: str | None,
    settings: Settings,
    interaction_mode: str,
) -> VoiceSession:
    existing = get_live_voice_session(db, learning_session.id)
    if existing is not None:
        raise ValueError("A live voice session already exists for this learning session")
    realtime_route = ModelRoutingPolicy.from_settings(settings).for_role("realtime")
    voice_session = VoiceSession(
        learning_session_id=learning_session.id,
        chat_session_id=chat_session_id,
        provider_call_id=provider_call_id,
        status="active",
        realtime_model=realtime_route.model,
        prompt_version="voice-tutor-v2",
        interaction_mode=interaction_mode,
        transcript_storage_enabled=settings.store_final_voice_transcripts,
        last_event_at=utc_now(),
    )
    db.add(voice_session)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ValueError("A live voice session already exists for this learning session") from exc
    return voice_session


def get_live_voice_session(
    db: Session,
    learning_session_id: str,
) -> VoiceSession | None:
    return db.scalar(
        select(VoiceSession)
        .where(
            VoiceSession.learning_session_id == learning_session_id,
            VoiceSession.status.in_(["connecting", "active", "reconnecting"]),
        )
        .order_by(VoiceSession.started_at.desc())
        .limit(1)
    )


def end_voice_session(
    db: Session,
    *,
    voice_session_id: str,
    reason: str = "user_stopped",
) -> VoiceSession:
    voice_session = db.scalar(
        select(VoiceSession).where(VoiceSession.id == voice_session_id).with_for_update()
    )
    if voice_session is None:
        raise ValueError("Voice session not found")
    if voice_session.status not in {"ended", "failed"}:
        voice_session.status = "ended"
        voice_session.ended_at = utc_now()
        voice_session.last_event_at = voice_session.ended_at
        voice_session.disconnect_reason = reason
        db.flush()
    return voice_session


def context_snapshot(db: Session, learning_session: LearningSession) -> dict:
    path = db.get(LearningPath, learning_session.path_id)
    revision = int(((path.model_metadata if path else {}) or {}).get("revision", 1))

    return {
        "learning_session_id": learning_session.id,
        "snapshot_id": learning_session.snapshot_id,
        "path_revision": revision,
        "current_module_id": learning_session.current_module_id,
        "current_lesson_id": learning_session.current_lesson_id,
        "current_step_id": learning_session.current_step_id,
        "focus_concept_ids": list(learning_session.focus_concept_ids or []),
        "selection": dict(learning_session.current_selection or {}),
        "preferred_style": (learning_session.teaching_state or {}).get(
            "preferred_style", "beginner"
        ),
    }


def record_final_transcript(
    db: Session,
    *,
    voice_session: VoiceSession,
    transcript: str,
    provider_item_id: str | None,
    route: str | None,
    intent: str | None,
    tool_name: str | None,
) -> VoiceTurn:
    existing = None
    if provider_item_id:
        existing = db.scalar(
            select(VoiceTurn).where(
                VoiceTurn.voice_session_id == voice_session.id,
                VoiceTurn.provider_call_id == provider_item_id,
            )
        )
    if existing is not None:
        return existing
    learning_session = db.get(LearningSession, voice_session.learning_session_id)
    if learning_session is None:
        raise ValueError("Learning session not found")
    turn = VoiceTurn(
        voice_session_id=voice_session.id,
        role="user",
        transcript=transcript if voice_session.transcript_storage_enabled else None,
        transcript_status="final",
        intent=intent,
        route=route,
        tool_name=tool_name,
        provider_call_id=provider_item_id,
        context_snapshot=context_snapshot(db, learning_session),
    )
    voice_session.last_event_at = utc_now()
    db.add(turn)
    db.flush()
    return turn
