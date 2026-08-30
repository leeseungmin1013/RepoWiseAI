from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, text

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.models import AnalysisJob, DeepTask, RepositorySnapshot
from app.queue import (
    cancel_repository_analysis_job,
    enqueue_deep_task,
    enqueue_repository_analysis,
    get_analysis_queue,
    get_deep_task_queue,
)
from app.services.usage import UsageService

logger = logging.getLogger(__name__)
_QUEUE_RECOVERY_LOCK_ID = 1_380_275_024


def _utc_now() -> datetime:
    return datetime.now(UTC)


def recover_queue_jobs(*, now: datetime | None = None) -> dict[str, object]:
    """Rebuild missing RQ jobs from authoritative database state.

    Render's free Key Value instance is intentionally non-persistent. Enqueue uses
    deterministic RQ job IDs, so calling this while jobs still exist is idempotent.
    Running jobs are only reset after a timeout-sized stale window.
    """

    settings = get_settings()
    current_time = now or _utc_now()
    analysis_stale_before = current_time - timedelta(
        seconds=max(settings.queue_recovery_stale_seconds, settings.analysis_job_timeout_seconds)
    )
    deep_stale_before = current_time - timedelta(
        seconds=max(settings.queue_recovery_stale_seconds, settings.deep_task_timeout_seconds)
    )
    summary: dict[str, object] = {
        "analysis_requeued": 0,
        "analysis_stale_reset": 0,
        "deep_requeued": 0,
        "deep_stale_reset": 0,
        "outcome": "success",
    }

    with SessionLocal() as db:
        lock_acquired = bool(
            db.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": _QUEUE_RECOVERY_LOCK_ID},
            ).scalar()
        )
        if not lock_acquired:
            summary["outcome"] = "skipped_concurrent_run"
            return summary
        try:
            analysis_jobs = list(
                db.scalars(
                    select(AnalysisJob)
                    .where(
                        or_(
                            AnalysisJob.status == "queued",
                            (
                                (AnalysisJob.status == "running")
                                & (AnalysisJob.started_at.is_not(None))
                                & (
                                    func.coalesce(
                                        AnalysisJob.last_progress_at,
                                        AnalysisJob.heartbeat_at,
                                        AnalysisJob.started_at,
                                    )
                                    < analysis_stale_before
                                )
                            ),
                        )
                    )
                    .order_by(AnalysisJob.created_at)
                    .limit(settings.queue_recovery_batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            analysis_queue = get_analysis_queue() if analysis_jobs else None
            for job in analysis_jobs:
                if job.status == "running":
                    if job.retry_count >= settings.analysis_max_retries:
                        job.status = "failed"
                        job.error_code = "analysis_retry_exhausted"
                        job.error_detail = "Analysis stopped making progress after retry limit."
                        job.finished_at = current_time
                        snapshot = db.get(RepositorySnapshot, job.snapshot_id)
                        if snapshot is not None:
                            snapshot.status = "failed"
                            snapshot.error_message = job.error_detail
                        UsageService(settings).release(
                            db, job.cost_reservation_id, commit=False
                        )
                        continue
                    cancel_repository_analysis_job(
                        job.snapshot_id, attempt=job.retry_count
                    )
                    job.status = "queued"
                    job.stage = "pending"
                    job.started_at = None
                    job.heartbeat_at = None
                    job.last_progress_at = current_time
                    job.finished_at = None
                    job.retry_count += 1
                    job.error_code = None
                    job.error_detail = None
                    snapshot = db.get(RepositorySnapshot, job.snapshot_id)
                    if snapshot is not None:
                        snapshot.status = "pending"
                        snapshot.error_message = None
                    summary["analysis_stale_reset"] = int(
                        summary["analysis_stale_reset"]
                    ) + 1
                enqueue_repository_analysis(
                    job.snapshot_id,
                    queue=analysis_queue,
                    trace_id=job.trace_id,
                    attempt=job.retry_count,
                )
                summary["analysis_requeued"] = int(summary["analysis_requeued"]) + 1

            deep_tasks = list(
                db.scalars(
                    select(DeepTask)
                    .where(
                        or_(
                            DeepTask.status == "queued",
                            (
                                DeepTask.status.in_({"running", "reasoning"})
                                & (DeepTask.updated_at < deep_stale_before)
                            ),
                        )
                    )
                    .order_by(DeepTask.created_at)
                    .limit(settings.queue_recovery_batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            deep_queue = get_deep_task_queue() if deep_tasks else None
            for task in deep_tasks:
                if task.status != "queued":
                    task.status = "queued"
                    task.progress = 0
                    task.message = "Requeued after queue recovery."
                    task.started_at = None
                    task.finished_at = None
                    task.error_code = None
                    task.error_detail = None
                    summary["deep_stale_reset"] = int(summary["deep_stale_reset"]) + 1
                task.rq_job_id = enqueue_deep_task(
                    task.id, queue=deep_queue, trace_id=task.trace_id
                )
                summary["deep_requeued"] = int(summary["deep_requeued"]) + 1

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _QUEUE_RECOVERY_LOCK_ID},
            )

    logger.info("queue_recovery_completed", extra={"outcome": summary["outcome"]})
    return summary


def main() -> int:
    configure_logging()
    try:
        print(json.dumps(recover_queue_jobs(), ensure_ascii=False))
        return 0
    except Exception:
        logger.exception(
            "queue_recovery_failed",
            extra={"error_code": "queue_recovery_failed", "outcome": "failed"},
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
