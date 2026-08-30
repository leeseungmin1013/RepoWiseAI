from __future__ import annotations

from rq import get_current_job

from app.core.logging import replace_log_context


def bind_worker_job_context(*, task_id: str | None = None, snapshot_id: str | None = None) -> None:
    job = get_current_job()
    metadata = job.meta if job is not None else {}
    replace_log_context(
        request_id=metadata.get("request_id"),
        trace_id=metadata.get("trace_id") or metadata.get("request_id"),
        organization_id=metadata.get("organization_id"),
        job_id=job.id if job is not None else None,
        task_id=task_id,
        snapshot_id=snapshot_id,
    )
