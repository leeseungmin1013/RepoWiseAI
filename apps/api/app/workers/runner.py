import logging
import os

from redis import Redis
from rq import Queue, SimpleWorker, Worker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.queue_recovery import recover_queue_jobs
from app.workers.recovery import handle_job_failure, handle_work_horse_killed

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging()
    recovery_summary = recover_queue_jobs()
    logger.info(
        "queue_recovery_at_worker_start",
        extra={"outcome": recovery_summary["outcome"]},
    )
    connection = Redis.from_url(settings.redis_url)
    analysis_queue = Queue(settings.queue_name, connection=connection)
    deep_queue = Queue(settings.deep_queue_name, connection=connection)
    worker_class = SimpleWorker if os.name == "nt" else Worker
    worker = worker_class(
        [deep_queue, analysis_queue],
        connection=connection,
        worker_ttl=settings.worker_heartbeat_stale_seconds,
        exception_handlers=[handle_job_failure],
        work_horse_killed_handler=handle_work_horse_killed,
    )
    logger.info("worker_started", extra={"outcome": "ready"})
    try:
        worker.work(with_scheduler=False)
    finally:
        logger.info("worker_stopped", extra={"outcome": "stopped"})


if __name__ == "__main__":
    main()
