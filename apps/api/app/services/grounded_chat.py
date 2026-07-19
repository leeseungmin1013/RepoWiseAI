from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.answers import GroundedAnswerGenerator
from app.core.config import get_settings
from app.models import ChatMessage, ChatSession, FileRecord, LearningSession
from app.retrieval.evidence import EvidenceRegistry, ResolvedEvidence
from app.retrieval.hybrid import HybridRetriever
from app.schemas import ChatAnswerResponse, CitationResponse


def create_grounded_message(
    db: Session,
    *,
    session_id: str,
    content: str,
    requested_selection: dict[str, Any] | None = None,
    metadata_overrides: dict[str, Any] | None = None,
    preferred_style_override: str | None = None,
    generation_model_override: str | None = None,
    reasoning_effort: str | None = None,
    allow_retrieval_fallback: bool = True,
    task_kind: str | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> ChatAnswerResponse:
    """Generate and persist one repository-grounded chat turn.

    REST chat and realtime voice orchestration share this entry point so selection
    validation, retrieval, citation filtering, and persistence cannot diverge.
    """
    session = db.scalar(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.snapshot))
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    snapshot = session.snapshot
    if snapshot.status != "ready" or snapshot.chunk_count == 0:
        raise HTTPException(status_code=409, detail="Snapshot retrieval index is not ready")

    learning_session = (
        db.get(LearningSession, session.learning_session_id)
        if session.learning_session_id
        else None
    )
    selection_source = (
        requested_selection
        if requested_selection is not None
        else (learning_session.current_selection if learning_session else session.current_selection)
    )
    selection = _validated_selection(db, snapshot.id, selection_source or {})
    session.current_selection = selection
    if learning_session is not None:
        learning_session.current_selection = selection
    learning_context = _learning_context(session, learning_session)
    question = content.strip()
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=question,
        structured_payload={
            "selection": selection,
            "learning_context": learning_context,
        },
    )
    db.add(user_message)
    db.flush()

    settings = get_settings()
    retrieval = HybridRetriever(settings).retrieve(
        db,
        snapshot=snapshot,
        session_id=session.id,
        message_id=user_message.id,
        query=_retrieval_query(question, learning_context),
        selection=selection,
    )
    resolved = EvidenceRegistry().resolve(db, retrieval.hits)
    preferred_style = preferred_style_override or session.preferred_style
    generation_options = {}
    if generation_model_override:
        generation_options["model_name"] = generation_model_override
    if reasoning_effort:
        generation_options["reasoning_effort"] = reasoning_effort
    if not allow_retrieval_fallback:
        generation_options["allow_retrieval_fallback"] = False
    if task_kind:
        generation_options["task_kind"] = task_kind
    generated = GroundedAnswerGenerator(settings).generate(
        question,
        resolved,
        preferred_style=preferred_style,
        learning_context=learning_context,
        **generation_options,
    )
    if should_continue is not None and not should_continue():
        db.rollback()
        raise GroundedGenerationCancelled
    selected = _select_evidence(resolved, generated.evidence_ids)
    citations = [_citation(item) for item in selected]

    model_metadata = {
        "mode": generated.mode,
        "model": generated.model_name,
        "preferred_style": preferred_style,
        "index_version": snapshot.index_version,
        "learning_context": learning_context,
    }
    if reasoning_effort:
        model_metadata["reasoning_effort"] = reasoning_effort
    if metadata_overrides:
        model_metadata.update(metadata_overrides)
    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=generated.answer,
        model_metadata=model_metadata,
    )
    db.add(assistant_message)
    db.flush()
    response = ChatAnswerResponse(
        id=assistant_message.id,
        session_id=session.id,
        question=question,
        answer=generated.answer,
        status=generated.status,
        intent=retrieval.analysis.intent,
        retrieval_run_id=retrieval.run.id,
        citations=citations,
        follow_up=generated.follow_up,
        voice_summary=generated.voice_summary,
        generation_mode=generated.mode,
        model_name=generated.model_name,
        created_at=assistant_message.created_at,
    )
    assistant_message.structured_payload = response.model_dump(mode="json")
    db.commit()
    return response


class GroundedGenerationCancelled(RuntimeError):
    pass


def _validated_selection(db: Session, snapshot_id: str, selection: dict) -> dict:
    if not selection:
        return {}
    file = db.scalar(
        select(FileRecord).where(
            FileRecord.id == selection.get("file_id"),
            FileRecord.snapshot_id == snapshot_id,
        )
    )
    if file is None:
        raise HTTPException(status_code=422, detail="Selected file is not in this snapshot")
    start_line = int(selection.get("start_line", 0))
    end_line = int(selection.get("end_line", 0))
    if start_line < 1 or start_line > end_line or end_line > file.line_count:
        raise HTTPException(status_code=422, detail="Selected line range is invalid")
    return {"file_id": file.id, "start_line": start_line, "end_line": end_line}


def _learning_context(session: ChatSession, learning_session: LearningSession | None) -> dict:
    if learning_session is None:
        return {}
    teaching = learning_session.teaching_state or session.teaching_state or {}
    return {
        "learning_session_id": learning_session.id,
        "module": teaching.get("module_title"),
        "lesson": teaching.get("lesson_title"),
        "objective": teaching.get("objective"),
        "step_instruction": teaching.get("step_instruction"),
        "concept_ids": list(learning_session.focus_concept_ids or []),
        "help_requested": bool(teaching.get("help_requested")),
    }


def _retrieval_query(question: str, learning_context: dict) -> str:
    if not learning_context:
        return question
    context = " ".join(
        str(value)
        for key in ("module", "lesson", "objective", "step_instruction")
        if (value := learning_context.get(key))
    )
    concepts = " ".join(learning_context.get("concept_ids") or [])
    return f"{question}\n현재 학습 단계: {context}\n관련 개념: {concepts}"[:6_000]


def _select_evidence(
    evidence: list[ResolvedEvidence], selected_ids: list[str]
) -> list[ResolvedEvidence]:
    allowed = set(selected_ids)
    return [item for item in evidence if item.evidence_id in allowed]


def _citation(evidence: ResolvedEvidence) -> CitationResponse:
    return CitationResponse(
        evidence_id=evidence.evidence_id,
        snapshot_id=evidence.snapshot_id,
        file_id=evidence.file_id,
        path=evidence.path,
        language=evidence.language,
        title=evidence.title,
        chunk_type=evidence.chunk_type,
        start_line=evidence.start_line,
        end_line=evidence.end_line,
        preview=evidence.preview,
        score=evidence.score,
        retrievers=evidence.retrievers,
    )
