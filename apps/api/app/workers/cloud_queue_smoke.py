from __future__ import annotations

import json
import time
import uuid

from redis import Redis
from rq import Queue
from rq.job import Job

from app.core.config import get_settings
from app.workers.queue_recovery import recover_queue_jobs


def _wait_for_finished(jobs: list[Job], timeout_seconds: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        statuses = []
        for job in jobs:
            job.refresh()
            statuses.append(job.get_status(refresh=False))
        if all(status == "finished" for status in statuses):
            return
        if any(status in {"failed", "stopped", "canceled"} for status in statuses):
            raise RuntimeError(f"Cloud queue smoke failed with statuses: {statuses}")
        time.sleep(0.5)
    raise TimeoutError("Cloud queue smoke did not finish before the deadline.")


def main() -> int:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    smoke_id = uuid.uuid4().hex
    jobs = [
        Queue(settings.queue_name, connection=connection).enqueue(
            recover_queue_jobs,
            job_id=f"phase3-smoke-analysis-{smoke_id}",
            result_ttl=300,
            failure_ttl=300,
        ),
        Queue(settings.deep_queue_name, connection=connection).enqueue(
            recover_queue_jobs,
            job_id=f"phase3-smoke-deep-{smoke_id}",
            result_ttl=300,
            failure_ttl=300,
        ),
    ]
    _wait_for_finished(jobs)
    print(
        json.dumps(
            {
                "outcome": "success",
                "queues": [settings.queue_name, settings.deep_queue_name],
                "statuses": [job.get_status(refresh=True) for job in jobs],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
