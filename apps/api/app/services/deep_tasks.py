from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import current_trace_id
from app.models import ChatSession, DeepTask, FileRecord, LearningSession
from app.queue import enqueue_deep_task
from app.services.usage import UsageContext, UsageService


class DeepTaskQueueUnavailable(RuntimeError):
    pass


def create_learning_deep_task(
    db: Session,
    *,
    session_id: str,
    kind: str,
    prompt: str,
    idempotency_key: str,
    modality: str = "text",
    requested_selection: dict | None = None,
    source_policy: str | None = None,
    enqueue: Callable[[str], str] = enqueue_deep_task,
) -> DeepTask:
    learning_session = db.get(LearningSession, session_id)
    if learning_session is None:
        raise ValueError("Learning session not found")
    normalized_key = idempotency_key.strip()
    if not normalized_key or len(normalized_key) > 200:
        raise ValueError("Idempotency-Key is invalid")
    normalized_prompt = prompt.strip()
    if len(normalized_prompt) < 2 or len(normalized_prompt) > 4_000:
        raise ValueError("Deep task prompt length is invalid")
    if kind not in {
        "deep_explanation",
        "impact_analysis",
        "roadmap_proposal",
        "research_materials",
    }:
        raise ValueError("Deep task kind is invalid")
    existing = db.scalar(
        select(DeepTask).where(
            DeepTask.learning_session_id == learning_session.id,
            DeepTask.idempotency_key == normalized_key,
        )
    )
    if existing is not None:
        if existing.status == "queued" and not existing.rq_job_id:
            _enqueue_task(db, existing, enqueue)
        return existing

    chat_session = db.scalar(
        select(ChatSession).where(ChatSession.learning_session_id == learning_session.id)
    )
    if chat_session is None:
        raise ValueError("Learning session has no linked chat")
    selection = _validated_selection(
        db,
        learning_session.snapshot_id,
        requested_selection
        if requested_selection is not None
        else (learning_session.current_selection or chat_session.current_selection or {}),
    )
    context_json = {"scope": "learning"}
    if source_policy:
        context_json["source_policy"] = source_policy
    task = DeepTask(
        learning_session_id=learning_session.id,
        user_id=getattr(chat_session, "user_id", None),
        organization_id=getattr(chat_session, "organization_id", None),
        chat_session_id=chat_session.id,
        kind=kind,
        modality=modality,
        idempotency_key=normalized_key,
        prompt=normalized_prompt,
        selection=selection,
        context_json=context_json,
        teaching_style=chat_session.preferred_style,
        status="queued",
        progress=0,
        message="심층 작업이 대기열에 등록되었습니다.",
        trace_id=current_trace_id(),
    )
    if getattr(task, "organization_id", None):
        reservation = UsageService().reserve(
            db,
            context=UsageContext(
                organization_id=task.organization_id,
                user_id=task.user_id,
                feature=(
                    "research_web_search"
                    if task.kind == "research_materials"
                    else "deep_explanation"
                ),
                request_id=task.id,
                idempotency_key=f"deep-task:{task.id}",
            ),
            estimated_cost_micro_usd=get_settings().deep_task_reservation_micro_usd,
        )
        task.cost_reservation_id = reservation.id if reservation else None
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(DeepTask).where(
                DeepTask.learning_session_id == learning_session.id,
                DeepTask.idempotency_key == normalized_key,
            )
        )
        if existing is None:
            raise
        if existing.status == "queued" and not existing.rq_job_id:
            _enqueue_task(db, existing, enqueue)
        return existing
    db.refresh(task)
    _enqueue_task(db, task, enqueue)
    return task


def _validated_selection(
    db: Session,
    snapshot_id: str,
    selection: dict,
) -> dict:
    if not selection:
        return {}
    file = db.scalar(
        select(FileRecord).where(
            FileRecord.id == selection.get("file_id"),
            FileRecord.snapshot_id == snapshot_id,
        )
    )
    if file is None:
        raise ValueError("Selected file is not in this snapshot")
    start_line = int(selection.get("start_line", 0))
    end_line = int(selection.get("end_line", 0))
    if start_line < 1 or start_line > end_line or end_line > file.line_count:
        raise ValueError("Selected line range is invalid")
    return {"file_id": file.id, "start_line": start_line, "end_line": end_line}


def _enqueue_task(db: Session, task: DeepTask, enqueue: Callable[[str], str]) -> None:
    try:
        task.rq_job_id = enqueue(task.id)
        db.commit()
    except Exception as exc:
        task.status = "failed"
        task.message = "심층 작업 대기열을 사용할 수 없습니다."
        task.error_code = "queue_unavailable"
        task.error_detail = "심층 작업 대기열을 사용할 수 없습니다."
        task.finished_at = datetime.now(UTC)
        db.commit()
        UsageService().release(db, getattr(task, "cost_reservation_id", None))
        raise DeepTaskQueueUnavailable("Deep task queue is unavailable") from exc
