from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AdminDep
from app.core.authorization import ensure_chat_access
from app.core.config import get_settings
from app.core.db import get_db
from app.models import ChatSession, CodeChunk, FileRecord, RetrievalCandidate, RetrievalRun
from app.schemas import RetrievalCandidateDebug, RetrievalRunDebug

router = APIRouter(prefix="/debug", tags=["debug"])
SessionDep = Annotated[Session, Depends(get_db)]


@router.get("/retrieval-runs/{run_id}", response_model=RetrievalRunDebug)
def get_retrieval_run(run_id: str, db: SessionDep, admin: AdminDep):
    if get_settings().app_env == "production":
        raise HTTPException(status_code=404, detail="Not found")
    run = db.get(RetrievalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Retrieval run not found")
    session = db.get(ChatSession, run.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Retrieval run not found")
    ensure_chat_access(db, admin, session)
    rows = db.execute(
        select(RetrievalCandidate, CodeChunk, FileRecord)
        .join(CodeChunk, CodeChunk.id == RetrievalCandidate.source_id)
        .join(FileRecord, FileRecord.id == CodeChunk.file_id)
        .where(RetrievalCandidate.retrieval_run_id == run.id)
        .order_by(RetrievalCandidate.retriever, RetrievalCandidate.rank)
    ).all()
    candidates = [
        RetrievalCandidateDebug(
            evidence_id=candidate.evidence_id,
            source_id=candidate.source_id,
            retriever=candidate.retriever,
            rank=candidate.rank,
            raw_score=candidate.raw_score,
            rrf_score=candidate.rrf_score,
            rerank_score=candidate.rerank_score,
            selected=candidate.selected,
            title=chunk.title,
            path=file.path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
        )
        for candidate, chunk, file in rows
    ]
    return RetrievalRunDebug(
        id=run.id,
        session_id=run.session_id,
        message_id=run.message_id,
        query_text=run.query_text,
        intent=run.intent,
        resolved_context=run.resolved_context,
        retrieval_plan=run.retrieval_plan,
        index_version=run.index_version,
        latency_ms=run.latency_ms,
        created_at=run.created_at,
        candidates=candidates,
    )
