from __future__ import annotations

import argparse
import json

from redis import Redis
from rq import Queue
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import AnalysisJob, DeepTask
from app.workers.queue_recovery import recover_queue_jobs


def run_redis_recovery_drill() -> dict[str, object]:
    """Flush Redis only when both the database and RQ report no active work."""

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    with SessionLocal() as db:
        active_analysis = int(
            db.scalar(
                select(func.count())
                .select_from(AnalysisJob)
                .where(AnalysisJob.status.in_(("queued", "running")))
            )
            or 0
        )
        active_deep = int(
            db.scalar(
                select(func.count())
                .select_from(DeepTask)
                .where(DeepTask.status.in_(("queued", "running", "reasoning")))
            )
            or 0
        )

    queue_counts = [
        len(Queue(settings.queue_name, connection=redis)),
        len(Queue(settings.deep_queue_name, connection=redis)),
    ]
    if active_analysis or active_deep or sum(queue_counts):
        raise RuntimeError(
            "Redis recovery drill refused: active work exists "
            f"(analysis={active_analysis}, deep={active_deep}, queues={queue_counts})."
        )

    redis_keys_before = redis.dbsize()
    redis.flushdb()
    redis_keys_after = redis.dbsize()
    recovery = recover_queue_jobs()
    return {
        "outcome": "success",
        "active_analysis": active_analysis,
        "active_deep": active_deep,
        "queue_counts_before": queue_counts,
        "redis_keys_before": redis_keys_before,
        "redis_keys_after": redis_keys_after,
        "recovery": recovery,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Destructively verify Redis-loss queue recovery."
    )
    parser.add_argument(
        "--confirm-flushdb",
        action="store_true",
        help="Required acknowledgement that the configured Redis database will be flushed.",
    )
    args = parser.parse_args()
    if not args.confirm_flushdb:
        parser.error("--confirm-flushdb is required")
    print(json.dumps(run_redis_recovery_drill(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
