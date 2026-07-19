import os

from redis import Redis
from rq import Queue, SimpleWorker, Worker

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    analysis_queue = Queue(settings.queue_name, connection=connection)
    deep_queue = Queue(settings.deep_queue_name, connection=connection)
    worker_class = SimpleWorker if os.name == "nt" else Worker
    worker = worker_class([deep_queue, analysis_queue], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
