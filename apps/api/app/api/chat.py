from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
def create_chat_session(payload: ChatSessionCreate, db: SessionDep):
    snapshot = db.get(RepositorySnapshot, payload.snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if snapshot.status != "ready":
        raise HTTPException(status_code=409, detail="Snapshot analysis is not ready")
    if snapshot.chunk_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Snapshot has no retrieval index; analyze the repository again",
        )
    session = ChatSession(
        snapshot_id=snapshot.id,
        goal=payload.goal,
        preferred_style=payload.preferred_style,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
def update_chat_session(session_id: str, payload: ChatSessionUpdate, db: SessionDep):
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    session.preferred_style = payload.preferred_style
    db.commit()
    db.refresh(session)
    return session


@router.post("/sessions/{session_id}/messages", response_model=ChatAnswerResponse)
def create_message(
    session_id: str,
    payload: ChatMessageCreate,
    db: SessionDep,
):
    return create_grounded_message(
        db,
        session_id=session_id,
        content=payload.content,
        requested_selection=payload.selection.model_dump() if payload.selection else None,
        metadata_overrides={"modality": payload.modality},
    )


@router.get("/messages/{message_id}", response_model=ChatAnswerResponse)
def get_message(message_id: str, db: SessionDep):
    message = db.get(ChatMessage, message_id)
    if message is None or message.role != "assistant" or not message.structured_payload:
        raise HTTPException(status_code=404, detail="Grounded answer not found")
    return ChatAnswerResponse.model_validate(message.structured_payload)
