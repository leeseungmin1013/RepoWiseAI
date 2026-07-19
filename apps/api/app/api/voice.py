from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import ChatSession, LearningSession
from app.voice.realtime import OpenAIRealtimeClient, RealtimeUnavailable

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

    raw_offer = await request.body()
    if not raw_offer or len(raw_offer) > settings.realtime_max_sdp_bytes:
        raise HTTPException(status_code=422, detail="SDP offer is empty or too large")
    try:
        sdp_offer = raw_offer.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="SDP offer must be UTF-8") from exc
    if "v=0" not in sdp_offer[:100]:
        raise HTTPException(status_code=422, detail="Invalid SDP offer")

    safety_identifier = hashlib.sha256(
        f"repowise:{learning_session.learner_profile_id}".encode()
    ).hexdigest()
    try:
        answer = await realtime.create_call(
            sdp_offer=sdp_offer,
            safety_identifier=safety_identifier,
        )
    except RealtimeUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    headers = {"Cache-Control": "no-store"}
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
