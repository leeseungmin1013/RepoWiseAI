from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.workers import queue_recovery


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


def test_recovery_requeues_db_state_and_resets_only_stale_running_jobs(monkeypatch):
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    snapshot = SimpleNamespace(status="analyzing", error_message="old")
    analysis = SimpleNamespace(
        status="running",
        stage="embedding",
        started_at=now - timedelta(minutes=20),
        finished_at=now - timedelta(minutes=1),
        retry_count=1,
        error_code="old",
        error_detail="old",
        snapshot_id="snap-1",
    )
    deep = SimpleNamespace(
        id="deep-1",
        status="reasoning",
        progress=70,
        message="working",
        started_at=now - timedelta(minutes=20),
        finished_at=None,
        updated_at=now - timedelta(minutes=20),
        error_code="old",
        error_detail="old",
        rq_job_id="lost-job",
    )
    calls = []

    class SessionStub:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=None):
            sql = str(statement)
            calls.append(sql)
            return _Result(True)

        def scalars(self, _statement):
            return [analysis] if calls.count("scalars") == 0 else [deep]

        def get(self, _model, object_id):
            assert object_id == "snap-1"
            return snapshot

        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    session = SessionStub()

    def tracked_scalars(statement):
        calls.append("scalars")
        return [analysis] if calls.count("scalars") == 1 else [deep]

    session.scalars = tracked_scalars
    settings = SimpleNamespace(
        queue_recovery_stale_seconds=900,
        analysis_job_timeout_seconds=600,
        deep_task_timeout_seconds=180,
        queue_recovery_batch_size=500,
    )
    monkeypatch.setattr(queue_recovery, "get_settings", lambda: settings)
    monkeypatch.setattr(queue_recovery, "SessionLocal", lambda: session)
    analysis_queue = object()
    deep_queue = object()
    monkeypatch.setattr(queue_recovery, "get_analysis_queue", lambda: analysis_queue)
    monkeypatch.setattr(queue_recovery, "get_deep_task_queue", lambda: deep_queue)
    monkeypatch.setattr(
        queue_recovery,
        "enqueue_repository_analysis",
        lambda snapshot_id, *, queue: calls.append(
            ("analysis", snapshot_id, queue is analysis_queue)) or "job-1",
    )
    monkeypatch.setattr(
        queue_recovery,
        "enqueue_deep_task",
        lambda task_id, *, queue: calls.append(
            ("deep", task_id, queue is deep_queue)) or task_id,
    )

    summary = queue_recovery.recover_queue_jobs(now=now)

    assert summary == {
        "analysis_requeued": 1,
        "analysis_stale_reset": 1,
        "deep_requeued": 1,
        "deep_stale_reset": 1,
        "outcome": "success",
    }
    assert analysis.status == "queued"
    assert analysis.stage == "pending"
    assert analysis.retry_count == 2
    assert analysis.started_at is None
    assert snapshot.status == "pending"
    assert deep.status == "queued"
    assert deep.progress == 0
    assert deep.rq_job_id == "deep-1"
    assert ("analysis", "snap-1", True) in calls
    assert ("deep", "deep-1", True) in calls
    assert calls.count("commit") == 1
    assert "rollback" not in calls


def test_recovery_skips_when_another_worker_holds_the_lock(monkeypatch):
    class SessionStub:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement, _params=None):
            return _Result(False)

    settings = SimpleNamespace(
        queue_recovery_stale_seconds=900,
        analysis_job_timeout_seconds=600,
        deep_task_timeout_seconds=180,
        queue_recovery_batch_size=500,
    )
    monkeypatch.setattr(queue_recovery, "get_settings", lambda: settings)
    monkeypatch.setattr(queue_recovery, "SessionLocal", SessionStub)

    summary = queue_recovery.recover_queue_jobs()

    assert summary["outcome"] == "skipped_concurrent_run"
    assert summary["analysis_requeued"] == 0
    assert summary["deep_requeued"] == 0
