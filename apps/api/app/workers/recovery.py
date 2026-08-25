from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import TracebackType

from rq.job import Job
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import AnalysisJob, DeepTask, RepositorySnapshot
from app.services.usage import UsageService

logger = logging.getLogger(__name__)


def _mark_failed(job: Job, error_code: str) -> None:
    argument_id = str(job.args[0]) if job.args else ""
    with SessionLocal() as db:
        if job.func_name == "app.workers.repository_analysis.analyze_repository":
            analysis_job = db.scalar(
                select(AnalysisJob)
                .where(AnalysisJob.snapshot_id == argument_id)
                .order_by(AnalysisJob.created_at.desc())
            )
            if analysis_job is None or analysis_job.status in {"finished", "failed"}:
                return
            snapshot = db.get(RepositorySnapshot, argument_id)
            analysis_job.status = "failed"
            analysis_job.error_code = error_code
            analysis_job.error_detail = "Worker terminated before analysis completed."
            analysis_job.finished_at = datetime.now(UTC)
            if snapshot is not None:
                snapshot.status = "failed"
                snapshot.error_message = "Worker terminated before analysis completed."
            UsageService().release(db, analysis_job.cost_reservation_id, commit=False)
        elif job.func_name == "app.workers.deep_tasks.run_deep_task":
            task = db.get(DeepTask, argument_id)
            if task is None or task.status in {"completed", "failed", "cancelled"}:
                return
            task.status = "failed"
            task.message = "작업 worker가 종료되어 심층 작업을 완료하지 못했습니다."
            task.error_code = error_code
            task.error_detail = "Worker terminated before deep task completed."
            task.finished_at = datetime.now(UTC)
            UsageService().release(db, task.cost_reservation_id, commit=False)
        else:
            return
        db.commit()
    logger.error(
        "orphaned_job_reconciled",
        extra={"job_id": job.id, "error_code": error_code, "outcome": "failed"},
    )


def handle_job_failure(
    job: Job,
    exception_type: type[BaseException],
    _exception_value: BaseException,
    _traceback: TracebackType | None,
) -> bool:
    _mark_failed(job, f"worker_{exception_type.__name__.lower()}")
    return True


def handle_work_horse_killed(
    job: Job,
    _retpid: int,
    _ret_val: int,
    _rusage,
) -> None:
    _mark_failed(job, "worker_terminated")
