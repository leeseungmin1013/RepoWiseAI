from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.repositories import load_snapshot, require_ready
from app.core.db import get_db
from app.guidance.path_builder import ensure_guided_path
from app.guidance.progress import apply_progress_event
from app.models import (
    CodeChunk,
    FileRecord,
    GuidedPath,
    GuidedStep,
    GuidedStepEvent,
    GuidedTourSession,
)
from app.retrieval.hybrid import evidence_id_for_chunk
from app.schemas import (
    CitationResponse,
    GuidedPathResponse,
    GuidedStepFeedbackCreate,
    GuidedStepResponse,
    GuidedTourSessionCreate,
    GuidedTourSessionResponse,
)

router = APIRouter(tags=["guided-learning"])
SessionDep = Annotated[Session, Depends(get_db)]


@router.get("/snapshots/{snapshot_id}/guided-path", response_model=GuidedPathResponse)
def get_guided_path(snapshot_id: str, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    try:
        path = ensure_guided_path(db, snapshot_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _path_response(db, path)


@router.post(
    "/guided-paths/{path_id}/sessions",
    response_model=GuidedTourSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_guided_tour_session(
    path_id: str, payload: GuidedTourSessionCreate, db: SessionDep
):
    path = db.get(GuidedPath, path_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Guided path not found")
    first_ordinal = db.scalar(
        select(func.min(GuidedStep.ordinal)).where(GuidedStep.path_id == path_id)
    )
    if first_ordinal is None:
        raise HTTPException(status_code=409, detail="Guided path has no steps")
    tour_session = GuidedTourSession(
        path_id=path_id,
        preferred_style=payload.preferred_style,
        current_step_ordinal=first_ordinal,
    )
    db.add(tour_session)
    db.commit()
    db.refresh(tour_session)
    return _session_response(db, tour_session)


@router.get(
    "/guided-tour-sessions/{session_id}", response_model=GuidedTourSessionResponse
)
def get_guided_tour_session(session_id: str, db: SessionDep):
    tour_session = db.get(GuidedTourSession, session_id)
    if tour_session is None:
        raise HTTPException(status_code=404, detail="Guided tour session not found")
    return _session_response(db, tour_session)


@router.post(
    "/guided-tour-sessions/{session_id}/steps/{step_id}/feedback",
    response_model=GuidedTourSessionResponse,
)
def record_guided_step_feedback(
    session_id: str,
    step_id: str,
    payload: GuidedStepFeedbackCreate,
    db: SessionDep,
):
    tour_session = db.get(GuidedTourSession, session_id)
    if tour_session is None:
        raise HTTPException(status_code=404, detail="Guided tour session not found")
    steps = db.scalars(
        select(GuidedStep)
        .where(GuidedStep.path_id == tour_session.path_id)
        .order_by(GuidedStep.ordinal)
    ).all()
    ordered_step_ids = [step.id for step in steps]
    try:
        update = apply_progress_event(
            ordered_step_ids=ordered_step_ids,
            current_step_ordinal=tour_session.current_step_ordinal,
            completed_step_ids=list(tour_session.completed_step_ids or []),
            needs_help_step_ids=list(tour_session.needs_help_step_ids or []),
            preferred_style=tour_session.preferred_style,
            step_id=step_id,
            event_type=payload.event_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    tour_session.preferred_style = update.preferred_style
    tour_session.status = update.status
    tour_session.current_step_ordinal = update.current_step_ordinal
    tour_session.completed_step_ids = update.completed_step_ids
    tour_session.needs_help_step_ids = update.needs_help_step_ids
    db.add(
        GuidedStepEvent(
            tour_session_id=tour_session.id,
            step_id=step_id,
            event_type=payload.event_type,
            payload=payload.payload,
        )
    )
    db.commit()
    db.refresh(tour_session)
    return _session_response(db, tour_session)


def _path_response(db: Session, path: GuidedPath) -> GuidedPathResponse:
    rows = db.execute(
        select(GuidedStep, CodeChunk, FileRecord)
        .join(CodeChunk, GuidedStep.chunk_id == CodeChunk.id)
        .join(FileRecord, CodeChunk.file_id == FileRecord.id)
        .where(GuidedStep.path_id == path.id)
        .order_by(GuidedStep.ordinal)
    ).all()
    steps: list[GuidedStepResponse] = []
    for step, chunk, file in rows:
        source = "\n".join(file.content.splitlines()[chunk.start_line - 1 : chunk.end_line])
        if (
            chunk.start_line < 1
            or chunk.end_line > file.line_count
            or source != chunk.content
        ):
            raise HTTPException(status_code=409, detail="Guided path evidence is stale")
        steps.append(
            GuidedStepResponse(
                id=step.id,
                ordinal=step.ordinal,
                step_type=step.step_type,
                title=step.title,
                learning_objective=step.learning_objective,
                summary=step.summary,
                concept_ids=list(step.concept_ids or []),
                checkpoint=step.checkpoint or {},
                estimated_minutes=step.estimated_minutes,
                evidence=CitationResponse(
                    evidence_id=evidence_id_for_chunk(chunk.id),
                    snapshot_id=chunk.snapshot_id,
                    file_id=file.id,
                    path=file.path,
                    language=file.language,
                    title=chunk.title,
                    chunk_type=chunk.chunk_type,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    preview=_preview(chunk.content),
                    score=1.0,
                    retrievers=["guided_path"],
                ),
            )
        )
    return GuidedPathResponse(
        id=path.id,
        snapshot_id=path.snapshot_id,
        title=path.title,
        goal=path.goal,
        difficulty=path.difficulty,
        path_version=path.path_version,
        generation_method=path.generation_method,
        total_minutes=sum(step.estimated_minutes for step in steps),
        steps=steps,
        created_at=path.created_at,
        updated_at=path.updated_at,
    )


def _session_response(
    db: Session, tour_session: GuidedTourSession
) -> GuidedTourSessionResponse:
    total_steps = db.scalar(
        select(func.count(GuidedStep.id)).where(GuidedStep.path_id == tour_session.path_id)
    ) or 0
    completed = list(tour_session.completed_step_ids or [])
    return GuidedTourSessionResponse(
        id=tour_session.id,
        path_id=tour_session.path_id,
        preferred_style=tour_session.preferred_style,
        status=tour_session.status,
        current_step_ordinal=tour_session.current_step_ordinal,
        completed_step_ids=completed,
        needs_help_step_ids=list(tour_session.needs_help_step_ids or []),
        completed_count=len(completed),
        total_steps=total_steps,
        created_at=tour_session.created_at,
        updated_at=tour_session.updated_at,
    )


def _preview(content: str, limit: int = 320) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    return compact if len(compact) <= limit else f"{compact[: limit - 3].rstrip()}..."
