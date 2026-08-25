from types import SimpleNamespace

import pytest

from app.workers import redis_recovery_drill


class _SessionStub:
    def __init__(self, values):
        self.values = iter(values)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalar(self, _statement):
        return next(self.values)


class _RedisStub:
    def __init__(self, key_count=4):
        self.key_count = key_count
        self.flushed = False

    def dbsize(self):
        return 0 if self.flushed else self.key_count

    def flushdb(self):
        self.flushed = True


def _settings():
    return SimpleNamespace(
        redis_url="redis://test",
        queue_name="analysis",
        deep_queue_name="deep",
    )


def test_drill_flushes_only_after_empty_preflight(monkeypatch):
    redis = _RedisStub()
    queues = iter([[], []])
    monkeypatch.setattr(redis_recovery_drill, "get_settings", _settings)
    monkeypatch.setattr(redis_recovery_drill, "SessionLocal", lambda: _SessionStub([0, 0]))
    monkeypatch.setattr(redis_recovery_drill.Redis, "from_url", lambda _url: redis)
    monkeypatch.setattr(redis_recovery_drill, "Queue", lambda *_args, **_kwargs: next(queues))
    monkeypatch.setattr(
        redis_recovery_drill,
        "recover_queue_jobs",
        lambda: {"outcome": "success", "analysis_requeued": 0, "deep_requeued": 0},
    )

    result = redis_recovery_drill.run_redis_recovery_drill()

    assert redis.flushed is True
    assert result["redis_keys_before"] == 4
    assert result["redis_keys_after"] == 0
    assert result["queue_counts_before"] == [0, 0]


def test_drill_refuses_to_flush_when_active_work_exists(monkeypatch):
    redis = _RedisStub()
    queues = iter([[], []])
    monkeypatch.setattr(redis_recovery_drill, "get_settings", _settings)
    monkeypatch.setattr(redis_recovery_drill, "SessionLocal", lambda: _SessionStub([1, 0]))
    monkeypatch.setattr(redis_recovery_drill.Redis, "from_url", lambda _url: redis)
    monkeypatch.setattr(redis_recovery_drill, "Queue", lambda *_args, **_kwargs: next(queues))

    with pytest.raises(RuntimeError, match="active work exists"):
        redis_recovery_drill.run_redis_recovery_drill()

    assert redis.flushed is False
