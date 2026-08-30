import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.voice import sideband
from app.voice.commands import (
    VoiceCommandContext,
    normalize_korean_command,
    parse_deterministic_command,
)
from app.voice.realtime import build_realtime_session_config
from app.voice.schemas import realtime_tool_names
from app.voice.sideband import extract_function_call


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("멈춰!", "stop"),
        ("말 그만", "stop"),
        ("음소거", "mute"),
        ("다음", "next"),
        ("이전 레슨", "previous"),
        ("원래 레슨으로 돌아가", "return"),
        ("이해했어요", "understood"),
        ("아직 어려워", "needs_help"),
        ("건너뛸래", "skip"),
        ("다시 읽어줘", "repeat"),
        ("짧게 말해줘", "concise"),
    ],
)
def test_deterministic_korean_commands(transcript, expected):
    context = VoiceCommandContext(
        has_current_lesson=True,
        has_previous_lesson=True,
        has_return_target=True,
    )

    command = parse_deterministic_command(transcript, context)

    assert command.action == expected
    assert command.is_confident is True
    assert command.allowed is True


def test_choice_command_uses_server_allowed_choice_ids():
    context = VoiceCommandContext(
        choice_ids=("choice_a", "choice_b"),
        choice_labels={"choice_a": "첫 호출", "choice_b": "두 번째 호출"},
    )

    by_number = parse_deterministic_command("2번", context)
    by_label = parse_deterministic_command("첫 호출", context)

    assert by_number.action == "submit_choice"
    assert by_number.choice_id == "choice_b"
    assert by_label.choice_id == "choice_a"


def test_stateful_command_is_rejected_when_context_does_not_allow_it():
    command = parse_deterministic_command(
        "원래 레슨으로 돌아가",
        VoiceCommandContext(has_return_target=False),
    )

    assert command.is_confident is True
    assert command.allowed is False
    assert command.reason == "no remediation return target"


def test_command_normalization_is_unicode_and_punctuation_stable():
    assert normalize_korean_command("  Ａ. 다시-읽어줘! ") == "a다시읽어줘"


def test_realtime_config_exposes_only_three_tools_and_opt_in_vad():
    manual = build_realtime_session_config(Settings(), vad_enabled=False)
    vad = build_realtime_session_config(Settings(), vad_enabled=True)

    assert realtime_tool_names() == {
        "answer_with_repository_evidence",
        "start_deep_learning_task",
        "apply_learning_action",
    }
    assert len(manual["tools"]) == 3
    assert manual["audio"]["input"]["turn_detection"] is None
    assert vad["audio"]["input"]["turn_detection"] == {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500,
        "create_response": True,
        "interrupt_response": True,
    }


def test_extracts_function_call_from_argument_done_and_response_done():
    direct = extract_function_call(
        {
            "type": "response.function_call_arguments.done",
            "name": "apply_learning_action",
            "call_id": "call_1",
            "arguments": '{"action":"next"}',
        }
    )
    completed = extract_function_call(
        {
            "type": "response.done",
            "response": {
                "output": [
                    {
                        "type": "function_call",
                        "name": "answer_with_repository_evidence",
                        "call_id": "call_2",
                        "arguments": '{"question":"이 함수는?"}',
                    }
                ]
            },
        }
    )

    assert direct == {
        "name": "apply_learning_action",
        "call_id": "call_1",
        "arguments": '{"action":"next"}',
    }
    assert completed and completed["call_id"] == "call_2"


def test_sideband_reconnects_same_call_after_transient_failures(monkeypatch):
    attempts = []
    statuses = []

    class Socket:
        async def send(self, _message):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class Connection:
        async def __aenter__(self):
            attempts.append("connect")
            if len(attempts) < 3:
                raise OSError("injected disconnect")
            return Socket()

        async def __aexit__(self, *_args):
            return False

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(sideband.websockets, "connect", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr(sideband.asyncio, "sleep", no_wait)
    monkeypatch.setattr(
        sideband,
        "_mark_status",
        lambda session_id, status, reason=None: statuses.append((session_id, status, reason)),
    )

    asyncio.run(
        sideband.SidebandSessionManager()._run(
            voice_session_id="voiceses_1",
            provider_call_id="call_1",
            settings=Settings(
                openai_api_key="test-key",
                realtime_sideband_reconnect_attempts=3,
            ),
        )
    )

    assert attempts == ["connect", "connect", "connect"]
    assert statuses == [
        ("voiceses_1", "reconnecting", None),
        ("voiceses_1", "reconnecting", None),
        ("voiceses_1", "active", None),
    ]


def test_sideband_marks_session_failed_when_reconnect_budget_is_exhausted(monkeypatch):
    attempts = []
    statuses = []

    class Connection:
        async def __aenter__(self):
            attempts.append("connect")
            raise OSError("injected outage")

        async def __aexit__(self, *_args):
            return False

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(sideband.websockets, "connect", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr(sideband.asyncio, "sleep", no_wait)
    monkeypatch.setattr(
        sideband,
        "_mark_status",
        lambda session_id, status, reason=None: statuses.append((session_id, status, reason)),
    )

    asyncio.run(
        sideband.SidebandSessionManager()._run(
            voice_session_id="voiceses_2",
            provider_call_id="call_2",
            settings=Settings(
                openai_api_key="test-key",
                realtime_sideband_reconnect_attempts=2,
            ),
        )
    )

    assert attempts == ["connect", "connect"]
    assert statuses[-1] == (
        "voiceses_2",
        "failed",
        "sideband_reconnect_exhausted",
    )


def test_grounded_tool_passes_voice_turn_metadata(monkeypatch):
    captured = {}
    answer = SimpleNamespace(
        id="msg_1",
        status="grounded",
        voice_summary="검증된 요약",
        answer="전체 답변",
        citations=[SimpleNamespace(evidence_id="ev_1")],
    )

    def fake_create(_db, **kwargs):
        captured.update(kwargs)
        return answer

    monkeypatch.setattr(sideband, "create_grounded_message", fake_create)
    output = sideband._dispatch_tool(
        object(),
        SimpleNamespace(
            id="voiceses_1",
            learning_session_id="learnses_1",
            chat_session_id="chat_1",
        ),
        name="answer_with_repository_evidence",
        call_id="call_3",
        turn_id="vturn_3",
        payload={"question": "이 함수는?", "answer_depth": "beginner"},
    )

    assert captured["metadata_overrides"] == {
        "modality": "voice",
        "voice_session_id": "voiceses_1",
        "voice_turn_id": "vturn_3",
        "route": "grounded_answer",
    }
    assert output["message_id"] == "msg_1"
    assert output["evidence_ids"] == ["ev_1"]


def test_deep_learning_tool_uses_shared_service_with_voice_idempotency(monkeypatch):
    voice_session = SimpleNamespace(
        id="voiceses_1",
        learning_session_id="learnses_1",
    )
    captured = {}

    def fake_create(db, **kwargs):
        captured["db"] = db
        captured.update(kwargs)
        return SimpleNamespace(
            id="dtask_1",
            status="queued",
            kind="impact_analysis",
        )

    monkeypatch.setattr(sideband, "create_learning_deep_task", fake_create)
    db = object()

    output = sideband._dispatch_tool(
        db,
        voice_session,
        name="start_deep_learning_task",
        call_id="call_7",
        payload={
            "task_type": "impact_analysis",
            "request": "이 변경의 영향 범위를 분석해줘",
            "source_policy": "repository_only",
        },
    )

    assert captured == {
        "db": db,
        "session_id": "learnses_1",
        "kind": "impact_analysis",
        "prompt": "이 변경의 영향 범위를 분석해줘",
        "idempotency_key": "voice:voiceses_1:call_7",
        "modality": "voice",
        "source_policy": "repository_only",
    }
    assert output == {
        "task_id": "dtask_1",
        "status": "queued",
        "task_type": "impact_analysis",
        "acknowledgement": "심층 작업을 시작했어요. 진행 중에도 계속 질문할 수 있어요.",
    }


def test_duplicate_sideband_tool_call_returns_cached_duplicate_without_execution(
    monkeypatch,
):
    voice_session = SimpleNamespace(
        id="voiceses_1",
        status="active",
        learning_session_id="learnses_1",
        chat_session_id="chat_1",
    )
    existing = SimpleNamespace(id="turn_1")

    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _model, _identifier):
            return voice_session

        def scalar(self, _statement):
            return existing

    monkeypatch.setattr(sideband, "SessionLocal", lambda: Db())
    monkeypatch.setattr(
        sideband,
        "_dispatch_tool",
        lambda *_args, **_kwargs: pytest.fail("duplicate tool was executed"),
    )

    events = sideband._process_function_call(
        "voiceses_1",
        name="apply_learning_action",
        call_id="call_duplicate",
        arguments='{"action":"next"}',
    )

    output = json.loads(events[0]["item"]["output"])
    assert output["status"] == "duplicate"
    assert events[1] == {"type": "response.create"}
