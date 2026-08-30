from datetime import UTC, datetime
from types import SimpleNamespace

from app.api import chat, learning


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


def _answer(message_id: str, answer: str, created_at: datetime) -> dict:
    return {
        "id": message_id,
        "session_id": "chat_1",
        "question": "질문",
        "answer": answer,
        "status": "answered",
        "intent": "code_explanation",
        "retrieval_run_id": "run_1",
        "citations": [],
        "follow_up": None,
        "voice_summary": None,
        "generation_mode": "fallback",
        "model_name": None,
        "created_at": created_at.isoformat(),
    }


def test_lists_recent_grounded_answers_in_chronological_order(monkeypatch):
    now = datetime(2026, 8, 30, tzinfo=UTC)
    session = SimpleNamespace(id="chat_1")
    messages = [
        SimpleNamespace(structured_payload=_answer("msg_2", "두 번째", now)),
        SimpleNamespace(structured_payload=_answer("msg_1", "첫 번째", now)),
    ]

    class Db:
        def get(self, _model, identifier):
            assert identifier == "chat_1"
            return session

        def scalars(self, _statement):
            return _ScalarResult(messages)

    authorized = []
    monkeypatch.setattr(
        chat,
        "ensure_chat_access",
        lambda _db, _auth, value: authorized.append(value.id),
    )

    result = chat.list_session_answers("chat_1", Db(), object(), limit=8)

    assert [item.id for item in result] == ["msg_1", "msg_2"]
    assert [item.answer for item in result] == ["첫 번째", "두 번째"]
    assert authorized == ["chat_1"]


def test_returns_latest_active_remediation_for_session(monkeypatch):
    now = datetime(2026, 8, 30, tzinfo=UTC)
    session = SimpleNamespace(id="learnses_1")
    branch = SimpleNamespace(
        id="branch_1",
        learning_session_id=session.id,
        source_lesson_id="lesson_1",
        source_step_id="step_1",
        mode="prerequisite",
        status="active",
        concept_ids=["function"],
        content={"type": "prerequisite"},
        return_lesson_id="lesson_1",
        return_step_id="step_1",
        created_at=now,
        completed_at=None,
    )

    class Db:
        def scalar(self, _statement):
            return branch

    monkeypatch.setattr(learning, "_load_learning_session", lambda _db, _id: session)

    result = learning.get_active_remediation(session.id, Db())

    assert result is not None
    assert result.id == "branch_1"
    assert result.status == "active"
    assert result.return_step_id == "step_1"


def test_returns_none_when_session_has_no_active_remediation(monkeypatch):
    session = SimpleNamespace(id="learnses_1")

    class Db:
        def scalar(self, _statement):
            return None

    monkeypatch.setattr(learning, "_load_learning_session", lambda _db, _id: session)

    assert learning.get_active_remediation(session.id, Db()) is None