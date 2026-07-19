from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.models import DeepTask
from app.services.grounded_chat import GroundedGenerationCancelled, create_grounded_message
from app.services.research_materials import research_official_materials


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _generation_route(task: DeepTask, settings: Settings) -> tuple[str, str]:
    if task.kind == "roadmap_proposal":
        return settings.deep_escalation_model, settings.deep_escalation_reasoning_effort
    return settings.deep_model, settings.deep_reasoning_effort


def _task_should_continue(task_id: str) -> bool:
    with SessionLocal() as db:
        task = db.get(DeepTask, task_id)
        return task is not None and task.status != "cancelled"


def run_deep_task(task_id: str) -> None:
    settings = get_settings()
    try:
        with SessionLocal() as db:
            task = db.scalar(select(DeepTask).where(DeepTask.id == task_id).with_for_update())
            if task is None:
                raise RuntimeError("Deep task not found")
            if task.status != "queued":
                return

            model, reasoning_effort = _generation_route(task, settings)
            task.status = "running"
            task.progress = 15
            task.message = "저장소 근거를 검색하고 심층 답변을 생성하고 있습니다."
            task.started_at = task.started_at or _utc_now()
            task.error_code = None
            task.error_detail = None
            task.model_metadata = {
                "route": task.kind,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "prompt_version": "deep-tutor-v1",
                "modality": task.modality,
            }
            db.commit()

            if task.kind == "research_materials":
                research = research_official_materials(
                    task.prompt,
                    settings=settings,
                    preferred_style=task.teaching_style,
                )
                db.refresh(task)
                if task.status == "cancelled":
                    return
                task.status = "completed"
                task.progress = 100
                task.message = "검증된 공식 학습자료를 찾았습니다."
                task.result_payload = research.model_dump(mode="json")
                task.model_metadata = {
                    **task.model_metadata,
                    "model": settings.research_model,
                    "source_count": len(research.sources),
                    "prompt_version": "official-research-v1",
                }
                task.finished_at = _utc_now()
                db.commit()
                return

            response = create_grounded_message(
                db,
                session_id=task.chat_session_id,
                content=task.prompt,
                requested_selection=task.selection or None,
                preferred_style_override=task.teaching_style,
                generation_model_override=model,
                reasoning_effort=reasoning_effort,
                allow_retrieval_fallback=False,
                task_kind=task.kind,
                metadata_overrides={
                    **task.model_metadata,
                    "deep_task_id": task.id,
                },
                should_continue=lambda: _task_should_continue(task.id),
            )
            if (
                response.status != "grounded"
                or response.generation_mode != "openai"
                or response.model_name != model
                or not response.citations
            ):
                raise RuntimeError("Deep task did not return a verified OpenAI answer")

            task.status = "completed"
            task.progress = 100
            task.message = "심층 답변이 준비되었습니다."
            task.result_message_id = response.id
            task.result_payload = response.model_dump(mode="json")
            task.finished_at = _utc_now()
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            task = db.get(DeepTask, task_id)
            if task is not None and task.status not in {"completed", "cancelled"}:
                task.status = "failed"
                task.message = "심층 작업을 완료하지 못했습니다."
                task.error_code = "generation_failed"
                task.error_detail = "심층 모델 응답을 생성하지 못했습니다."
                task.finished_at = _utc_now()
                db.commit()
        if isinstance(exc, GroundedGenerationCancelled):
            return
        raise
