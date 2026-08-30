from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.api.repositories import analysis_runtime_state


def _job(now: datetime, **overrides):
    values = {
        "status": "queued",
        "created_at": now,
        "started_at": None,
        "heartbeat_at": None,
        "last_progress_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_analysis_runtime_state_detects_queue_and_worker_stalls() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    assert analysis_runtime_state(_job(now), now=now) == ("queued", None)
    assert analysis_runtime_state(
        _job(now, last_progress_at=now - timedelta(minutes=3)), now=now
    ) == ("stalled", "worker_unavailable")
    assert analysis_runtime_state(
        _job(
            now,
            status="running",
            started_at=now - timedelta(minutes=5),
            heartbeat_at=now,
            last_progress_at=now - timedelta(minutes=4),
        ),
        now=now,
    ) == ("running", None)
    assert analysis_runtime_state(
        _job(
            now,
            status="running",
            started_at=now - timedelta(minutes=5),
            heartbeat_at=now - timedelta(minutes=4),
            last_progress_at=now,
        ),
        now=now,
    ) == ("stalled", "worker_unavailable")


def test_analysis_runtime_state_prioritizes_overall_deadline() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    state = analysis_runtime_state(
        _job(
            now,
            status="running",
            started_at=now - timedelta(minutes=31),
            heartbeat_at=now,
            last_progress_at=now,
        ),
        now=now,
    )

    assert state == ("stalled", "analysis_deadline_exceeded")
