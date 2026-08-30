from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import ChatSession, LearnerProfile, LearningSession, VoiceSession
from app.services.usage import UsageContext, UsageService
from app.voice.realtime import OpenAIRealtimeClient, RealtimeUnavailable
from app.voice.session_manager import (
    create_voice_session,
    end_voice_session,
    get_live_voice_session,
)
from app.voice.sideband import sideband_session_manager

router = APIRouter(tags=["voice-learning"])
SessionDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_realtime_client(settings: SettingsDep) -> OpenAIRealtimeClient:
    return OpenAIRealtimeClient(settings)


RealtimeClientDep = Annotated[OpenAIRealtimeClient, Depends(get_realtime_client)]


@router.post(
    "/learning-sessions/{session_id}/voice/offer",
    response_class=Response,
    responses={
        200: {"content": {"application/sdp": {}}},
        415: {"description": "Expected an SDP offer"},
        503: {"description": "Realtime voice is not configured"},
    },
)
async def create_voice_offer(
    session_id: str,
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
    realtime: RealtimeClientDep,
    vad: bool = False,
) -> Response:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"application/sdp", "text/plain"}:
        raise HTTPException(status_code=415, detail="Expected an SDP offer")

    learning_session = db.get(LearningSession, session_id)
    if learning_session is None:
        raise HTTPException(status_code=404, detail="Learning session not found")
    linked_chat_id = db.scalar(
        select(ChatSession.id).where(ChatSession.learning_session_id == learning_session.id)
    )
    if linked_chat_id is None:
        raise HTTPException(status_code=409, detail="Learning session has no linked chat")
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Realtime voice is not configured")
    if get_live_voice_session(db, learning_session.id) is not None:
        raise HTTPException(
            status_code=409,
            detail="A live voice session already exists for this learning session",
        )

    raw_offer = await request.body()
    if not raw_offer or len(raw_offer) > settings.realtime_max_sdp_bytes:
        raise HTTPException(status_code=422, detail="SDP offer is empty or too large")
    try:
        sdp_offer = raw_offer.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="SDP offer must be UTF-8") from exc
    if "v=0" not in sdp_offer[:100]:
        raise HTTPException(status_code=422, detail="Invalid SDP offer")

    usage_context = None
    reservation = None
    if settings.quota_enforcement_mode != "off":
        profile = db.get(LearnerProfile, learning_session.learner_profile_id)
        if profile is not None and profile.organization_id:
            usage_context = UsageContext(
                organization_id=profile.organization_id,
                user_id=profile.user_id,
                feature="realtime_voice",
                request_id=f"voice:{session_id}",
                idempotency_key=f"voice:{session_id}:{hashlib.sha256(raw_offer).hexdigest()}",
            )
            reservation = UsageService(settings).reserve(
                db,
                context=usage_context,
                estimated_cost_micro_usd=settings.realtime_reservation_micro_usd,
            )

    safety_identifier = hashlib.sha256(
        f"repowise:{learning_session.learner_profile_id}".encode()
    ).hexdigest()
    try:
        answer = await realtime.create_call(
            sdp_offer=sdp_offer,
            safety_identifier=safety_identifier,
            vad_enabled=vad,
        )
    except RealtimeUnavailable as exc:
        if reservation is not None:
            UsageService(settings).release(db, reservation.id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        voice_session = create_voice_session(
            db,
            learning_session=learning_session,
            chat_session_id=linked_chat_id,
            provider_call_id=answer.call_id,
            settings=settings,
            interaction_mode="vad" if vad else "push_to_talk",
        )
        db.commit()
        db.refresh(voice_session)
        if answer.call_id:
            sideband_session_manager.start(
                voice_session_id=voice_session.id,
                provider_call_id=answer.call_id,
                settings=settings,
            )
    except ValueError as exc:
        db.rollback()
        if answer.call_id:
            await realtime.hangup_call(answer.call_id)
        if reservation is not None:
            UsageService(settings).release(db, reservation.id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if usage_context is not None:
        UsageService(settings).settle(
            db,
            reservation_id=reservation.id if reservation else None,
            context=usage_context,
            provider="openai",
            model=settings.realtime_model,
            usage={"session_created": 1},
            settled_cost_micro_usd=settings.realtime_reservation_micro_usd,
        )

    headers = {
        "Cache-Control": "no-store",
        "X-Realtime-Max-Duration": str(settings.realtime_max_duration_seconds),
        "X-RepoWise-Voice-Session-Id": voice_session.id,
    }
    if answer.location:
        headers["Location"] = answer.location
    if answer.call_id:
        headers["X-OpenAI-Realtime-Call-Id"] = answer.call_id
    return Response(
        content=answer.sdp,
        status_code=201,
        media_type="application/sdp",
        headers=headers,
    )


@router.get("/voice-sessions/{voice_session_id}")
def get_voice_session(voice_session_id: str, db: SessionDep) -> dict:
    voice_session = db.get(VoiceSession, voice_session_id)
    if voice_session is None:
        raise HTTPException(status_code=404, detail="Voice session not found")
    return _voice_session_payload(voice_session)


@router.post("/voice-sessions/{voice_session_id}/stop")
async def stop_voice_session(
    voice_session_id: str,
    db: SessionDep,
    realtime: RealtimeClientDep,
) -> dict:
    voice_session = db.get(VoiceSession, voice_session_id)
    if voice_session is None:
        raise HTTPException(status_code=404, detail="Voice session not found")
    if voice_session.provider_call_id and voice_session.status not in {"ended", "failed"}:
        try:
            await realtime.hangup_call(voice_session.provider_call_id)
        except RealtimeUnavailable:
            pass
    sideband_session_manager.stop(voice_session.id)
    voice_session = end_voice_session(
        db,
        voice_session_id=voice_session.id,
        reason="user_stopped",
    )
    db.commit()
    db.refresh(voice_session)
    return _voice_session_payload(voice_session)


def _voice_session_payload(voice_session: VoiceSession) -> dict:
    return {
        "id": voice_session.id,
        "learning_session_id": voice_session.learning_session_id,
        "chat_session_id": voice_session.chat_session_id,
        "status": voice_session.status,
        "interaction_mode": voice_session.interaction_mode,
        "realtime_model": voice_session.realtime_model,
        "prompt_version": voice_session.prompt_version,
        "started_at": voice_session.started_at,
        "ended_at": voice_session.ended_at,
        "last_event_at": voice_session.last_event_at,
        "disconnect_reason": voice_session.disconnect_reason,
    }
