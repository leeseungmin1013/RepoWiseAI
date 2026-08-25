from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from fastapi import Response

from app import queue
from app.api import health
from app.core.config import Settings
from app.core.logging import JsonFormatter, bind_log_context, redact, reset_log_context
from app.workers import maintenance, recovery, runner


class _Result:
    def __init__(self, scalar_value=None, rowcount=0):
        self.scalar_value = scalar_value
        self.rowcount = rowcount

    def scalar(self):
        return self.scalar_value


def test_liveness_does_not_check_dependencies(monkeypatch):
    monkeypatch.setattr(health, "get_settings", lambda: Settings(release_sha="release-1"))

    assert health.liveness() == {
        "status": "alive",
        "version": "0.1.0",
        "release": "release-1",
    }


def test_readiness_returns_503_when_a_dependency_is_unavailable(monkeypatch):
    class BrokenSession:
        def __enter__(self):
            raise RuntimeError("database unavailable")

        def __exit__(self, *_args):
            return False

    class BrokenRedis:
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            return cls()

        def ping(self):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(health, "SessionLocal", BrokenSession)
    monkeypatch.setattr(health, "Redis", BrokenRedis)
    response = Response()

    payload = health.readiness(response)

    assert response.status_code == 503
    assert payload["status"] == "unavailable"
    assert payload["checks"] == {
        "database": "unavailable",
        "migration": "incompatible",
        "queue": "unavailable",
    }


def test_json_logging_redacts_credentials_and_includes_context():
    token = bind_log_context(request_id="request-1")
    try:
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "database_url=postgresql://user:password@example/db",
            (),
            None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_log_context(token)

    assert payload["request_id"] == "request-1"
    assert payload["message"] == "database_url=[REDACTED]"
    assert "password" not in json.dumps(payload)
    assert redact("Authorization: Bearer top-secret") == "Authorization=[REDACTED]"
    assert redact("redis://internal-host:6379/0") == "redis://[REDACTED]"


def test_enqueue_propagates_request_metadata(monkeypatch):
    captured = {}

    class QueueStub:
        def enqueue(self, *_args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id=kwargs["job_id"])

    monkeypatch.setattr(queue, "get_analysis_queue", QueueStub)
    token = bind_log_context(request_id="request-1", organization_id="org-1")
    try:
        queue.enqueue_repository_analysis("snap-1")
    finally:
        reset_log_context(token)

    assert captured["meta"] == {"request_id": "request-1", "organization_id": "org-1"}


def test_worker_subscribes_deep_queue_before_analysis(monkeypatch):
    captured = {}

    class WorkerStub:
        def __init__(self, queues, connection, **kwargs):
            captured["queues"] = [item.name for item in queues]
            captured["connection"] = connection
            captured["handlers"] = kwargs

        def work(self, **kwargs):
            captured["work"] = kwargs

    monkeypatch.setattr(runner, "recover_queue_jobs", lambda: {"outcome": "success"})
    monkeypatch.setattr(runner, "Redis", SimpleNamespace(from_url=lambda _url: "redis"))
    monkeypatch.setattr(runner, "Worker", WorkerStub)
    monkeypatch.setattr(runner.os, "name", "posix")
    monkeypatch.setattr(runner, "get_settings", lambda: Settings())

    runner.main()

    assert captured["handlers"]["exception_handlers"]
    assert captured["handlers"]["work_horse_killed_handler"]
    assert captured["queues"] == ["repowise-deep-learning", "repowise-analysis"]
    assert captured["work"] == {"with_scheduler": False}


def test_maintenance_uses_lock_and_commits_once(monkeypatch):
    calls = []

    class SessionStub:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=None):
            sql = str(statement)
            calls.append(sql)
            if "pg_try_advisory_lock" in sql:
                return _Result(True)
            if "pg_advisory_unlock" in sql:
                return _Result(True)
            return _Result(rowcount=3)

        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class UsageStub:
        def __init__(self, _settings):
            pass

        def release_stale(self, _db, *, commit):
            assert commit is False
            return 2

    monkeypatch.setattr(maintenance, "SessionLocal", SessionStub)
    monkeypatch.setattr(maintenance, "UsageService", UsageStub)

    summary = maintenance.run_maintenance()

    assert summary["semantic_cache_deleted"] == 3
    assert summary["stale_reservations_released"] == 2
    assert summary["outcome"] == "success"
    assert calls.count("commit") == 1
    assert "rollback" not in calls


def test_maintenance_main_returns_nonzero_on_error(monkeypatch):
    monkeypatch.setattr(
        maintenance,
        "run_maintenance",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert maintenance.main() == 1



def test_abandoned_deep_job_is_failed_and_reservation_released(monkeypatch):
    task = SimpleNamespace(
        status="running",
        message="running",
        error_code=None,
        error_detail=None,
        finished_at=None,
        cost_reservation_id="reservation-1",
    )
    calls = []

    class SessionStub:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _model, task_id):
            assert task_id == "task-1"
            return task

        def commit(self):
            calls.append("commit")

    class UsageStub:
        def release(self, _db, reservation_id, *, commit):
            calls.append((reservation_id, commit))

    monkeypatch.setattr(recovery, "SessionLocal", SessionStub)
    monkeypatch.setattr(recovery, "UsageService", UsageStub)
    job = SimpleNamespace(
        id="task-1",
        args=("task-1",),
        func_name="app.workers.deep_tasks.run_deep_task",
    )

    assert recovery.handle_job_failure(job, RuntimeError, RuntimeError("boom"), None)
    assert task.status == "failed"
    assert task.error_code == "worker_runtimeerror"
    assert calls == [("reservation-1", False), "commit"]
