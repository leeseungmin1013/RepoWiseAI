from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.core.logging import current_trace_id
from app.models import ChatSession, DeepTask, FileRecord
from app.queue import cancel_deep_task_job, enqueue_deep_task
from app.schemas import (
    ChangeBriefResponse,
    ChatAnswerResponse,
    DeepTaskCreate,
    DeepTaskErrorResponse,
    DeepTaskResponse,
    ResearchMaterialsResponse,
)
from app.services.deep_tasks import (
    DeepTaskQueueUnavailable,
    create_learning_deep_task,
)
from app.services.usage import UsageContext, UsageService

router = APIRouter(tags=["deep-learning"])
SessionDep = Annotated[Session, Depends(get_db)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _task_response(task: DeepTask) -> DeepTaskResponse:
    result = None
    if task.result_payload:
        if task.kind == "research_materials":
            result_schema = ResearchMaterialsResponse
        elif getattr(task, "context_json", {}).get("scope") == "navigation":
            result_schema = ChangeBriefResponse
        else:
            result_schema = ChatAnswerResponse
        result = result_schema.model_validate(task.result_payload)
    error = (
        DeepTaskErrorResponse(
            code=task.error_code or "deep_task_failed",
            message=task.message or "심층 작업을 완료하지 못했습니다.",
        )
        if task.status == "failed"
        else None
    )
    return DeepTaskResponse(
        id=task.id,
        status=task.status,
        kind=task.kind,
        progress=task.progress,
        message=task.message,
        trace_id=getattr(task, "trace_id", None),
        result=result,
        error=error,
    )


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


def _enqueue_task(db: Session, task: DeepTask) -> None:
    try:
        task.rq_job_id = enqueue_deep_task(task.id)
        db.commit()
    except Exception as exc:
        task.status = "failed"
        task.message = "심층 작업 대기열을 사용할 수 없습니다."
        task.error_code = "queue_unavailable"
        task.error_detail = "심층 작업 대기열을 사용할 수 없습니다."
        task.finished_at = _utc_now()
        db.commit()
        UsageService().release(db, getattr(task, "cost_reservation_id", None))
        raise HTTPException(status_code=503, detail="Deep task queue is unavailable") from exc


@router.post(
    "/learning-sessions/{session_id}/deep-tasks",
    response_model=DeepTaskResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_deep_task(
    session_id: str,
    payload: DeepTaskCreate,
    db: SessionDep,
    idempotency_key: IdempotencyKey,
):
    try:
        task = create_learning_deep_task(
            db,
            session_id=session_id,
            kind=payload.kind,
            prompt=payload.prompt,
            idempotency_key=idempotency_key,
            modality=payload.modality,
            requested_selection=(payload.selection.model_dump() if payload.selection else None),
            enqueue=enqueue_deep_task,
        )
    except DeepTaskQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        if str(exc) == "Learning session not found":
            status_code = 404
        elif str(exc) in {
            "Idempotency-Key is invalid",
            "Deep task prompt length is invalid",
            "Deep task kind is invalid",
            "Selected file is not in this snapshot",
            "Selected line range is invalid",
        }:
            status_code = 422
        else:
            status_code = 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return _task_response(task)


@router.post(
    "/chat/sessions/{session_id}/deep-tasks",
    response_model=DeepTaskResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_navigation_deep_task(
    session_id: str,
    payload: DeepTaskCreate,
    db: SessionDep,
    idempotency_key: IdempotencyKey,
):
    chat_session = db.get(ChatSession, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if payload.kind != "impact_analysis":
        raise HTTPException(
            status_code=422,
            detail="Navigation deep tasks only support impact_analysis",
        )
    idempotency_key = idempotency_key.strip()
    if not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(status_code=422, detail="Idempotency-Key is invalid")
    existing = db.scalar(
        select(DeepTask).where(
            DeepTask.chat_session_id == chat_session.id,
            DeepTask.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.status == "queued" and not existing.rq_job_id:
            _enqueue_task(db, existing)
        return _task_response(existing)

    navigation_context = (
        payload.navigation_context.model_dump(exclude_none=True)
        if payload.navigation_context
        else {}
    )
    requested_selection = (
        payload.selection.model_dump()
        if payload.selection
        else navigation_context.get("selection") or chat_session.current_selection or {}
    )
    if not requested_selection:
        raise HTTPException(
            status_code=422,
            detail="Change Brief requires a selected code range",
        )
    selection = _validated_selection(db, chat_session.snapshot_id, requested_selection)
    navigation_context["selection"] = selection
    chat_session.navigation_context = navigation_context
    chat_session.current_selection = selection
    task = DeepTask(
        learning_session_id=None,
        user_id=getattr(chat_session, "user_id", None),
        organization_id=getattr(chat_session, "organization_id", None),
        chat_session_id=chat_session.id,
        kind="impact_analysis",
        modality=payload.modality,
        idempotency_key=idempotency_key,
        prompt=payload.prompt.strip(),
        selection=selection,
        context_json={
            "scope": "navigation",
            "navigation_context": navigation_context,
        },
        teaching_style=chat_session.preferred_style,
        status="queued",
        progress=0,
        message="변경 영향 분석이 대기열에 등록되었습니다.",
        trace_id=current_trace_id(),
    )
    if getattr(task, "organization_id", None):
        reservation = UsageService().reserve(
            db,
            context=UsageContext(
                organization_id=getattr(task, "organization_id", None),
                user_id=getattr(task, "user_id", None),
                feature="research_web_search"
                if task.kind == "research_materials"
                else "deep_explanation",
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
                DeepTask.chat_session_id == chat_session.id,
                DeepTask.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        if existing.status == "queued" and not existing.rq_job_id:
            _enqueue_task(db, existing)
        return _task_response(existing)
    db.refresh(task)
    _enqueue_task(db, task)
    return _task_response(task)


@router.get(
    "/deep-tasks/{task_id}",
    response_model=DeepTaskResponse,
    response_model_exclude_none=True,
)
def get_deep_task(task_id: str, db: SessionDep):
    task = db.get(DeepTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Deep task not found")
    return _task_response(task)


@router.post(
    "/deep-tasks/{task_id}/cancel",
    response_model=DeepTaskResponse,
    response_model_exclude_none=True,
)
def cancel_deep_task(task_id: str, db: SessionDep):
    task = db.scalar(select(DeepTask).where(DeepTask.id == task_id).with_for_update())
    if task is None:
        raise HTTPException(status_code=404, detail="Deep task not found")
    if task.status in TERMINAL_STATUSES:
        return _task_response(task)

    task.status = "cancelled"
    task.progress = 100
    task.message = "심층 작업을 취소했습니다."
    task.error_code = None
    task.error_detail = None
    task.finished_at = _utc_now()
    db.commit()
    UsageService().release(db, getattr(task, "cost_reservation_id", None))
    if task.rq_job_id:
        cancel_deep_task_job(task.rq_job_id)
    return _task_response(task)


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def deep_task_event_stream(
    task_id: str,
    *,
    poll_interval: float = 1.0,
    heartbeat_interval: float = 15.0,
) -> Iterator[str]:
    last_version: tuple | None = None
    last_heartbeat = time.monotonic()
    while True:
        with SessionLocal() as db:
            task = db.get(DeepTask, task_id)
            if task is None:
                yield _sse_event(
                    "failed",
                    {
                        "id": task_id,
                        "status": "failed",
                        "kind": "unknown",
                        "progress": 0,
                        "message": "심층 작업을 찾을 수 없습니다.",
                        "error": {
                            "code": "not_found",
                            "message": "Deep task not found",
                        },
                    },
                )
                return
            response = _task_response(task)
            version = (task.status, task.progress, task.updated_at)
            if version != last_version:
                yield _sse_event(task.status, response.model_dump(mode="json", exclude_none=True))
                last_version = version
                last_heartbeat = time.monotonic()
            if task.status in TERMINAL_STATUSES:
                return
            current_status = task.status

        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_interval:
            yield _sse_event(
                "heartbeat",
                {"id": task_id, "status": current_status},
            )
            last_heartbeat = now
        time.sleep(poll_interval)


@router.get(
    "/deep-tasks/{task_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def get_deep_task_events(task_id: str, db: SessionDep) -> StreamingResponse:
    if db.get(DeepTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Deep task not found")
    return StreamingResponse(
        deep_task_event_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
