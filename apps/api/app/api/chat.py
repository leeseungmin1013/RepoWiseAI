from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthDep
from app.core.authorization import ensure_chat_access, ensure_snapshot_access
from app.core.db import get_db
from app.models import ChatMessage, ChatSession, RepositorySnapshot
from app.schemas import (
    ChatAnswerResponse,
    ChatMessageCreate,
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionUpdate,
)
from app.services.grounded_chat import create_grounded_message

router = APIRouter(prefix="/chat", tags=["chat"])
SessionDep = Annotated[Session, Depends(get_db)]


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_chat_session(payload: ChatSessionCreate, db: SessionDep, auth: AuthDep):
    snapshot = db.get(RepositorySnapshot, payload.snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    ensure_snapshot_access(db, auth, snapshot.id)
    if snapshot.status != "ready":
        raise HTTPException(status_code=409, detail="Snapshot analysis is not ready")
    if snapshot.chunk_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Snapshot has no retrieval index; analyze the repository again",
        )
    session = ChatSession(
        snapshot_id=snapshot.id,
        user_id=auth.user_id if auth.authenticated else None,
        organization_id=auth.organization_id if auth.authenticated else None,
        goal=payload.goal,
        preferred_style=payload.preferred_style,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
def update_chat_session(session_id: str, payload: ChatSessionUpdate, db: SessionDep, auth: AuthDep):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    ensure_chat_access(db, auth, session)
    session.preferred_style = payload.preferred_style
    db.commit()
    db.refresh(session)
    return session


def create_message(session_id: str, payload: ChatMessageCreate, db: SessionDep):
    """Internal helper retained for non-HTTP callers and tests."""
    return create_grounded_message(
        db,
        session_id=session_id,
        content=payload.content,
        requested_selection=payload.selection.model_dump() if payload.selection else None,
        metadata_overrides={"modality": payload.modality},
    )


@router.post("/sessions/{session_id}/messages", response_model=ChatAnswerResponse)
def create_message_endpoint(
    session_id: str,
    payload: ChatMessageCreate,
    response: Response,
    db: SessionDep,
    auth: AuthDep,
):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    ensure_chat_access(db, auth, session)
    result = create_message(session_id, payload, db)
    if result.cache:
        response.headers["X-Retrieval-Cache"] = result.cache.retrieval
        response.headers["X-Generation-Cache"] = result.cache.generation
    if result.quota and result.quota.get("remaining_micro_usd") is not None:
        response.headers["X-Quota-Remaining"] = str(result.quota["remaining_micro_usd"])
    return result


@router.get("/sessions/{session_id}/messages", response_model=list[ChatAnswerResponse])
def list_session_answers(
    session_id: str,
    db: SessionDep,
    auth: AuthDep,
    limit: int = 8,
):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    ensure_chat_access(db, auth, session)
    bounded_limit = max(1, min(limit, 20))
    messages = db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session.id,
            ChatMessage.role == "assistant",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(bounded_limit)
    ).all()
    return [
        ChatAnswerResponse.model_validate(message.structured_payload)
        for message in reversed(messages)
        if message.structured_payload
    ]

@router.get("/messages/{message_id}", response_model=ChatAnswerResponse)
def get_message(message_id: str, db: SessionDep, auth: AuthDep):
    message = db.get(ChatMessage, message_id)
    if message is None or message.role != "assistant" or not message.structured_payload:
        raise HTTPException(status_code=404, detail="Grounded answer not found")
    session = db.get(ChatSession, message.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Grounded answer not found")
    ensure_chat_access(db, auth, session)
    return ChatAnswerResponse.model_validate(message.structured_payload)
