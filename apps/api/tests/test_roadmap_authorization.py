from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import authorization
from app.models import LearningSession, RoadmapProposal, VoiceSession


class Db:
    def __init__(self, proposal=None, session=None):
        self.proposal = proposal
        self.session = session

    def get(self, model, identifier):
        if model is RoadmapProposal:
            assert identifier == "proposal_1"
            return self.proposal
        if model is LearningSession:
            assert identifier == "session_1"
            return self.session
        raise AssertionError(model)


def test_roadmap_proposal_authorization_delegates_to_learning_session(monkeypatch):
    proposal = SimpleNamespace(learning_session_id="session_1")
    session = SimpleNamespace(id="session_1")
    checked = []
    monkeypatch.setattr(
        authorization,
        "ensure_learning_access",
        lambda _db, context, value: checked.append((context, value)),
    )
    context = object()

    authorization.ensure_roadmap_proposal_access(
        Db(proposal=proposal, session=session),
        context,
        "proposal_1",
    )

    assert checked == [(context, session)]


def test_roadmap_proposal_authorization_hides_unknown_proposal():
    with pytest.raises(HTTPException) as exc:
        authorization.ensure_roadmap_proposal_access(Db(), object(), "proposal_1")

    assert exc.value.status_code == 404


class VoiceDb:
    def __init__(self, voice_session=None, learning_session=None):
        self.voice_session = voice_session
        self.learning_session = learning_session

    def get(self, model, identifier):
        if model is VoiceSession:
            assert identifier == "voice_1"
            return self.voice_session
        if model is LearningSession:
            assert identifier == "session_1"
            return self.learning_session
        raise AssertionError(model)


def test_voice_session_authorization_delegates_to_learning_session(monkeypatch):
    voice_session = SimpleNamespace(learning_session_id="session_1")
    learning_session = SimpleNamespace(id="session_1")
    checked = []
    monkeypatch.setattr(
        authorization,
        "ensure_learning_access",
        lambda _db, context, value: checked.append((context, value)),
    )
    context = object()

    authorization.ensure_voice_session_access(
        VoiceDb(voice_session=voice_session, learning_session=learning_session),
        context,
        "voice_1",
    )

    assert checked == [(context, learning_session)]


def test_voice_session_authorization_hides_unknown_session():
    with pytest.raises(HTTPException) as exc:
        authorization.ensure_voice_session_access(VoiceDb(), object(), "voice_1")

    assert exc.value.status_code == 404
