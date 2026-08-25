from redis import Redis
from rq import Queue
from rq.command import send_stop_job_command
from rq.exceptions import DuplicateJobError, InvalidJobOperation, NoSuchJobError
from rq.job import Job, JobStatus

from app.core.config import get_settings
from app.core.logging import current_log_context


def get_analysis_queue() -> Queue:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    return Queue(settings.queue_name, connection=connection)


def enqueue_repository_analysis(snapshot_id: str, *, queue: Queue | None = None) -> str:
    settings = get_settings()
    job_id = f"repository-analysis-{snapshot_id}"
    context = current_log_context()
    metadata = {
        key: context[key]
        for key in ("request_id", "organization_id")
        if key in context
    }
    try:
        job = (queue or get_analysis_queue()).enqueue(
            "app.workers.repository_analysis.analyze_repository",
            snapshot_id,
            job_id=job_id,
            unique=True,
            job_timeout=settings.analysis_job_timeout_seconds,
            result_ttl=3600,
            failure_ttl=24 * 3600,
            meta=metadata,
        )
    except DuplicateJobError:
        return job_id
    return job.id


def get_deep_task_queue() -> Queue:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    return Queue(settings.deep_queue_name, connection=connection)


def enqueue_deep_task(task_id: str, *, queue: Queue | None = None) -> str:
    settings = get_settings()
    context = current_log_context()
    metadata = {
        key: context[key]
        for key in ("request_id", "organization_id")
        if key in context
    }
    try:
        job = (queue or get_deep_task_queue()).enqueue(
            "app.workers.deep_tasks.run_deep_task",
            task_id,
            job_id=task_id,
            unique=True,
            job_timeout=settings.deep_task_timeout_seconds,
            result_ttl=3600,
            failure_ttl=24 * 3600,
            meta=metadata,
        )
    except DuplicateJobError:
        return task_id
    return job.id


def cancel_deep_task_job(job_id: str) -> bool:
    """Best-effort RQ cancellation; the database status remains authoritative."""
    queue = get_deep_task_queue()
    try:
        job = Job.fetch(job_id, connection=queue.connection)
        job_status = job.get_status(refresh=True)
        if job_status == JobStatus.STARTED:
            send_stop_job_command(queue.connection, job_id)
        elif job_status not in {JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELED}:
            job.cancel(enqueue_dependents=False)
        return True
    except (NoSuchJobError, InvalidJobOperation):
        return False
