import asyncio
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
from starlette.requests import Request

from app.api import voice
from app.api.voice import create_voice_offer
from app.core.config import Settings
from app.voice.realtime import (
    OpenAIRealtimeClient,
    RealtimeCallAnswer,
    RealtimeUnavailable,
    build_realtime_session_config,
)


def test_realtime_session_is_manual_push_to_talk_with_korean_transcription() -> None:
    config = build_realtime_session_config(Settings())

    assert config["type"] == "realtime"
    assert config["model"] == "gpt-realtime-2.1-mini"
    assert config["output_modalities"] == ["audio"]
    assert config["reasoning"] == {"effort": "minimal"}
    assert config["audio"]["input"]["turn_detection"] is None
    assert config["audio"]["input"]["transcription"] == {
        "model": "gpt-realtime-whisper",
        "language": "ko",
        "delay": "low",
    }
    assert config["audio"]["output"]["voice"] == "marin"
    assert "Never answer" in config["instructions"]


def test_realtime_client_sends_unified_multipart_offer() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["safety_identifier"] = request.headers["OpenAI-Safety-Identifier"]
        body = await request.aread()
        captured["body"] = body.decode()
        return httpx.Response(
            201,
            text="v=0\r\no=answer",
            headers={"Location": "/v1/realtime/calls/call_123"},
        )

    client = OpenAIRealtimeClient(
        Settings(openai_api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )
    answer = asyncio.run(
        client.create_call(
            sdp_offer="v=0\r\no=offer",
            safety_identifier="safe-user",
        )
    )

    assert captured["authorization"] == "Bearer test-key"
    assert captured["safety_identifier"] == "safe-user"
    assert 'name="sdp"' in captured["body"]
    assert "v=0\r\no=offer" in captured["body"]
    assert 'name="session"' in captured["body"]
    assert json.dumps("gpt-realtime-2.1-mini")[1:-1] in captured["body"]
    assert answer.sdp == "v=0\r\no=answer"
    assert answer.call_id == "call_123"
    assert answer.location == "/v1/realtime/calls/call_123"


def test_realtime_client_requires_api_key() -> None:
    client = OpenAIRealtimeClient(Settings(openai_api_key=""))

    with pytest.raises(RealtimeUnavailable, match="OPENAI_API_KEY"):
        asyncio.run(client.create_call(sdp_offer="v=0", safety_identifier="safe-user"))


def test_voice_offer_proxies_sdp_for_linked_learning_session(monkeypatch) -> None:
    captured: dict = {}

    class FakeDb:
        scalar_calls = 0

        def get(self, _model, session_id):
            assert session_id == "learnses_1"
            return SimpleNamespace(id=session_id, learner_profile_id="learner_1")

        def scalar(self, _statement):
            self.scalar_calls += 1
            return "ses_1" if self.scalar_calls == 1 else None

        def commit(self):
            pass

        def refresh(self, _value):
            pass

    class FakeRealtime:
        async def create_call(self, **kwargs):
            captured.update(kwargs)
            return RealtimeCallAnswer(
                sdp="v=0\r\no=answer",
                call_id="rtc_123",
                location="/v1/realtime/calls/rtc_123",
            )

    monkeypatch.setattr(
        voice,
        "create_voice_session",
        lambda *_args, **_kwargs: SimpleNamespace(id="voiceses_1"),
    )
    monkeypatch.setattr(voice.sideband_session_manager, "start", lambda **_kwargs: None)
    body = b"v=0\r\no=offer"
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/voice/offer",
            "headers": [(b"content-type", b"application/sdp")],
        },
        receive,
    )
    response = asyncio.run(
        create_voice_offer(
            "learnses_1",
            request,
            FakeDb(),
            Settings(openai_api_key="test-key"),
            FakeRealtime(),
        )
    )

    assert response.status_code == 201
    assert response.media_type == "application/sdp"
    assert response.body == b"v=0\r\no=answer"
    assert response.headers["location"] == "/v1/realtime/calls/rtc_123"
    assert response.headers["x-openai-realtime-call-id"] == "rtc_123"
    assert response.headers["x-repowise-voice-session-id"] == "voiceses_1"
    assert captured["sdp_offer"] == body.decode()
    assert captured["vad_enabled"] is False
    assert captured["safety_identifier"] == hashlib.sha256(b"repowise:learner_1").hexdigest()
