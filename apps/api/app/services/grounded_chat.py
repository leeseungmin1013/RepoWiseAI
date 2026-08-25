from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.answers import GroundedAnswerGenerator
from app.core.config import get_settings
from app.models import (
    ChatMessage,
    ChatSession,
    FileRecord,
    LearningSession,
    RetrievalCandidate,
    RetrievalRun,
)
from app.retrieval.evidence import EvidenceRegistry, ResolvedEvidence
from app.retrieval.hybrid import HybridRetriever, RetrievalResult
from app.retrieval.query import analyze_query
from app.schemas import CacheSummary, ChatAnswerResponse, CitationResponse
from app.services.semantic_cache import SemanticCacheService
from app.services.usage import UsageContext, UsageService


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
    cost_reservation_id: str | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> ChatAnswerResponse:
    """Generate one grounded turn with tenant-safe retrieval and answer caching."""
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
        structured_payload={"selection": selection, "learning_context": learning_context},
    )
    db.add(user_message)
    db.flush()

    settings = get_settings()
    preferred_style = preferred_style_override or session.preferred_style
    model_name = generation_model_override or getattr(settings, "generation_model", None)
    modality = str((metadata_overrides or {}).get("modality", "text"))
    cache_service = SemanticCacheService(settings)
    organization_id = getattr(session, "organization_id", None)
    user_id = getattr(session, "user_id", None)
    cache_enabled = bool(organization_id or user_id)
    context_fingerprint = (
        cache_service.context_fingerprint(
            db,
            snapshot=snapshot,
            selection=selection,
            learning_context=learning_context,
            preferred_style=preferred_style,
            modality=modality,
            task_kind=task_kind,
            model=model_name,
            reasoning_effort=reasoning_effort,
        )
        if cache_enabled
        else ""
    )
    retrieval_query = _retrieval_query(question, learning_context)
    query_analysis = analyze_query(retrieval_query)
    retrieval_lookup = None
    query_embedding = None
    if cache_enabled:
        retrieval_lookup = cache_service.lookup(
            db,
            kind="retrieval",
            scope="public",
            scope_id="public",
            snapshot=snapshot,
            query=retrieval_query,
            intent=query_analysis.intent,
            context_fingerprint=context_fingerprint,
            model=None,
        )
        if retrieval_lookup is None:
            query_embedding = cache_service.embed_query(snapshot, retrieval_query)
            retrieval_lookup = cache_service.lookup(
                db,
                kind="retrieval",
                scope="public",
                scope_id="public",
                snapshot=snapshot,
                query=retrieval_query,
                intent=query_analysis.intent,
                context_fingerprint=context_fingerprint,
                model=None,
                query_embedding=query_embedding,
            )

    retrieval_shadow_lookup = (
        retrieval_lookup
        if retrieval_lookup is not None and getattr(settings, "semantic_cache_shadow_mode", False)
        else None
    )
    if retrieval_shadow_lookup is not None:
        retrieval_lookup = None

    if retrieval_lookup is not None:
        run = RetrievalRun(
            session_id=session.id,
            message_id=user_message.id,
            query_text=retrieval_query,
            resolved_context=selection,
            intent=query_analysis.intent,
            retrieval_plan={"cache": retrieval_lookup.status},
            index_version=snapshot.index_version,
            latency_ms=0,
            token_usage={},
            cache_source_run_id=retrieval_lookup.entry.source_run_id,
            cache_status=retrieval_lookup.status,
            cache_similarity=retrieval_lookup.similarity,
        )
        db.add(run)
        db.flush()
        for rank, hit in enumerate(retrieval_lookup.hits, start=1):
            db.add(
                RetrievalCandidate(
                    retrieval_run_id=run.id,
                    evidence_id=hit.evidence_id,
                    source_id=hit.chunk.id,
                    retriever="cache",
                    rank=rank,
                    raw_score=hit.score,
                    rrf_score=hit.score,
                    rerank_score=hit.score,
                    selected=True,
                )
            )
        retrieval = RetrievalResult(
            run=run,
            analysis=query_analysis,
            hits=retrieval_lookup.hits,
            query_embedding=query_embedding,
        )
    else:
        retrieval = HybridRetriever(settings).retrieve(
            db,
            snapshot=snapshot,
            session_id=session.id,
            message_id=user_message.id,
            query=retrieval_query,
            selection=selection,
            query_embedding=query_embedding,
        )
        if retrieval_shadow_lookup is not None:
            retrieval.run.cache_status = f"shadow_{retrieval_shadow_lookup.status}"
            retrieval.run.cache_similarity = retrieval_shadow_lookup.similarity
        if cache_enabled:
            cache_service.store(
                db,
                kind="retrieval",
                scope="public",
                scope_id="public",
                snapshot=snapshot,
                query=retrieval_query,
                intent=retrieval.analysis.intent,
                context_fingerprint=context_fingerprint,
                model=None,
                query_embedding=retrieval.query_embedding,
                hits=retrieval.hits,
                payload={},
                source_run_id=retrieval.run.id,
                source_message_id=None,
            )
    resolved = EvidenceRegistry().resolve(db, retrieval.hits)

    generation_scope = "organization" if organization_id else "user"
    generation_scope_id = organization_id or user_id or session.id
    generation_lookup = (
        cache_service.lookup(
            db,
            kind="generation",
            scope=generation_scope,
            scope_id=generation_scope_id,
            snapshot=snapshot,
            query=question,
            intent=retrieval.analysis.intent,
            context_fingerprint=context_fingerprint,
            model=model_name,
            query_embedding=retrieval.query_embedding,
        )
        if cache_enabled
        else None
    )
    generation_shadow_lookup = (
        generation_lookup
        if generation_lookup is not None and getattr(settings, "semantic_cache_shadow_mode", False)
        else None
    )
    if generation_shadow_lookup is not None:
        generation_lookup = None

    generation_options = {}
    if generation_model_override:
        generation_options["model_name"] = generation_model_override
    if reasoning_effort:
        generation_options["reasoning_effort"] = reasoning_effort
    if not allow_retrieval_fallback:
        generation_options["allow_retrieval_fallback"] = False
    if task_kind:
        generation_options["task_kind"] = task_kind

    usage_service = UsageService(settings)
    usage_context = None
    reservation = None
    if organization_id:
        feature = task_kind or "chat_generation"
        if feature not in {"deep_explanation", "roadmap_proposal"}:
            feature = "chat_generation"
        usage_context = UsageContext(
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
            request_id=user_message.id,
            idempotency_key=f"{user_message.id}:{feature}",
        )
        if generation_lookup is None and cost_reservation_id is None:
            reservation = usage_service.reserve(
                db,
                context=usage_context,
                estimated_cost_micro_usd=(
                    getattr(settings, "deep_task_reservation_micro_usd", 500_000)
                    if task_kind
                    else getattr(settings, "chat_generation_reservation_micro_usd", 100_000)
                ),
            )
    try:
        generated = (
            cache_service.generated_answer(generation_lookup)
            if generation_lookup is not None
            else GroundedAnswerGenerator(settings).generate(
                question,
                resolved,
                preferred_style=preferred_style,
                learning_context=learning_context,
                **generation_options,
            )
        )
    except Exception:
        if reservation is not None:
            usage_service.release(db, reservation.id)
        raise

    usage_summary = getattr(generated, "usage", {})
    quota_summary: dict[str, Any] = {}
    if usage_context is not None:
        if generation_lookup is not None:
            cached_context = UsageContext(
                organization_id=usage_context.organization_id,
                user_id=usage_context.user_id,
                feature="cached_request",
                request_id=user_message.id,
                idempotency_key=f"{user_message.id}:cached_request",
            )
            usage_service.settle(
                db,
                reservation_id=None,
                context=cached_context,
                provider=None,
                model=None,
                usage={},
                settled_cost_micro_usd=0,
                cache_status=generation_lookup.status,
            )
        else:
            usage_service.settle(
                db,
                reservation_id=cost_reservation_id or (reservation.id if reservation else None),
                context=usage_context,
                provider="openai" if generated.mode == "openai" else None,
                model=generated.model_name,
                usage=getattr(generated, "usage", {}),
                cache_status="miss",
            )
        current_quota = usage_service.current_snapshot(db, usage_context.organization_id)
        quota_summary = {
            "period_end": current_quota.period_end.isoformat(),
            "remaining_micro_usd": current_quota.remaining_micro_usd,
            "reserved_micro_usd": current_quota.reserved_micro_usd,
        }

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
    if retrieval_shadow_lookup or generation_shadow_lookup:
        model_metadata["shadow_cache"] = {
            "retrieval": retrieval_shadow_lookup.status if retrieval_shadow_lookup else "miss",
            "generation": generation_shadow_lookup.status if generation_shadow_lookup else "miss",
        }
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
    if cache_enabled and generation_lookup is None:
        cache_service.store(
            db,
            kind="generation",
            scope=generation_scope,
            scope_id=generation_scope_id,
            snapshot=snapshot,
            query=question,
            intent=retrieval.analysis.intent,
            context_fingerprint=context_fingerprint,
            model=model_name,
            query_embedding=retrieval.query_embedding,
            hits=[hit for hit in retrieval.hits if hit.evidence_id in set(generated.evidence_ids)],
            payload={
                "answer": generated.answer,
                "follow_up": generated.follow_up,
                "status": generated.status,
                "model_name": generated.model_name,
                "voice_summary": generated.voice_summary,
            },
            source_run_id=retrieval.run.id,
            source_message_id=assistant_message.id,
        )
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
        cache=CacheSummary(
            retrieval=retrieval_lookup.status if retrieval_lookup else "miss",
            generation=generation_lookup.status if generation_lookup else "miss",
            similarity=(generation_lookup or retrieval_lookup).similarity
            if (generation_lookup or retrieval_lookup)
            else None,
        )
        if cache_enabled
        else None,
        usage=usage_summary or None,
        quota=quota_summary or None,
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
