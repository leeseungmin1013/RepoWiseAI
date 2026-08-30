from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import assessment
from app.schemas import AssessmentAnswerCreate


class _Db:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_expiration_projects_partial_answers_and_marks_audit_time(monkeypatch):
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    session = SimpleNamespace(
        id="asm_1",
        status="active",
        expires_at=now - timedelta(seconds=1),
        timed_out_at=None,
    )
    projected = []
    monkeypatch.setattr(assessment, "utc_now", lambda: now)
    monkeypatch.setattr(
        assessment,
        "_project_assessment_profile",
        lambda _db, value, *, event_type: projected.append((value.id, event_type)),
    )

    assert assessment._expire_assessment(object(), session) is True
    assert session.status == "timed_out"
    assert session.timed_out_at == now
    assert projected == [("asm_1", "assessment_timeout")]


def test_expiration_is_idempotent_and_ignores_future_deadline(monkeypatch):
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(assessment, "utc_now", lambda: now)
    future = SimpleNamespace(status="active", expires_at=now + timedelta(seconds=1))
    finished = SimpleNamespace(status="timed_out", expires_at=now - timedelta(seconds=1))

    assert assessment._expire_assessment(object(), future) is False
    assert assessment._expire_assessment(object(), finished) is False


def test_late_submit_returns_timed_out_result_instead_of_error(monkeypatch):
    db = _Db()
    session = SimpleNamespace(status="active", profile=object())
    expected = object()
    monkeypatch.setattr(assessment, "_load_assessment", lambda _db, _id: session)

    def expire(_db, value):
        value.status = "timed_out"
        return True

    monkeypatch.setattr(assessment, "_expire_assessment", expire)
    monkeypatch.setattr(assessment, "_assessment_response", lambda *_args: expected)

    assert assessment.submit_assessment("asm_1", db) is expected
    assert db.commits == 1


def test_late_answer_is_rejected_with_stable_error_code(monkeypatch):
    db = _Db()
    session = SimpleNamespace(status="active")
    monkeypatch.setattr(assessment, "_load_assessment", lambda _db, _id: session)

    def refresh(_db, value):
        value.status = "timed_out"
        return True

    monkeypatch.setattr(assessment, "_refresh_assessment", refresh)

    with pytest.raises(HTTPException) as caught:
        assessment.answer_assessment(
            "asm_1",
            AssessmentAnswerCreate(item_id="goal", answer="learn"),
            db,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "assessment_timed_out"
    assert db.commits == 1