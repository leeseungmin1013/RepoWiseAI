from app.workers import repository_analysis


def test_heartbeat_loop_writes_until_stopped(monkeypatch):
    waits = iter([False, False, True])
    writes: list[str] = []

    class StopStub:
        def wait(self, interval_seconds: int) -> bool:
            assert interval_seconds == 15
            return next(waits)

    monkeypatch.setattr(
        repository_analysis,
        "_write_job_heartbeat",
        lambda snapshot_id: writes.append(snapshot_id),
    )

    repository_analysis._heartbeat_loop("snap-heartbeat", StopStub(), 15)

    assert writes == ["snap-heartbeat", "snap-heartbeat"]
