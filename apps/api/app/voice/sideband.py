from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from time import perf_counter
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from app.core.config import Settings
from app.core.db import SessionLocal
from app.models import LearningSession, VoiceSession, VoiceTurn, utc_now
from app.services.deep_tasks import create_learning_deep_task
from app.services.grounded_chat import create_grounded_message
from app.services.learning_actions import apply_learning_action, command_context_state
from app.voice.commands import (
    VoiceCommandContext,
    parse_deterministic_command,
)
from app.voice.schemas import REALTIME_FUNCTION_TOOLS, realtime_tool_names
from app.voice.session_manager import context_snapshot, record_final_transcript

_ACKNOWLEDGEMENTS = {
    "understood": "이해한 것으로 기록하고 다음 학습으로 이동했어요.",
    "needs_help": "어려운 부분으로 기록했어요. 더 작은 단계로 설명할게요.",
    "skip": "현재 레슨을 건너뛰고 다음 학습으로 이동했어요.",
    "next": "다음 레슨으로 이동했어요.",
    "previous": "이전 레슨으로 이동했어요.",
    "return": "원래 레슨으로 돌아왔어요.",
    "submit_choice": "선택지 답변을 기록했어요.",
    "repeat": "방금 설명을 다시 읽을게요.",
    "concise": "앞으로 더 짧게 설명할게요.",
}


class SidebandSessionManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(
        self,
        *,
        voice_session_id: str,
        provider_call_id: str,
        settings: Settings,
    ) -> None:
        previous = self._tasks.get(voice_session_id)
        if previous is not None and not previous.done():
            return
        task = asyncio.create_task(
            self._run(
                voice_session_id=voice_session_id,
                provider_call_id=provider_call_id,
                settings=settings,
            ),
            name=f"voice-sideband:{voice_session_id}",
        )
        self._tasks[voice_session_id] = task
        task.add_done_callback(
            lambda _task, session_id=voice_session_id: self._tasks.pop(session_id, None)
        )

    def stop(self, voice_session_id: str) -> None:
        task = self._tasks.pop(voice_session_id, None)
        if task is not None:
            task.cancel()

    async def _run(
        self,
        *,
        voice_session_id: str,
        provider_call_id: str,
        settings: Settings,
    ) -> None:
        url = settings.realtime_sideband_url.rstrip("/") + (f"?call_id={provider_call_id}")
        attempts = max(1, settings.realtime_sideband_reconnect_attempts)
        for attempt in range(attempts):
            try:
                if attempt:
                    _mark_status(voice_session_id, "reconnecting")
                    await asyncio.sleep(min(2**attempt, 5))
                async with websockets.connect(
                    url,
                    additional_headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                    },
                    open_timeout=settings.realtime_connect_timeout_seconds,
                    close_timeout=5,
                    max_size=1_048_576,
                ) as socket:
                    _mark_status(voice_session_id, "active")
                    await socket.send(
                        json.dumps(
                            {
                                "type": "session.update",
                                "session": {
                                    "type": "realtime",
                                    "tools": REALTIME_FUNCTION_TOOLS,
                                    "tool_choice": "auto",
                                },
                            },
                            ensure_ascii=False,
                        )
                    )
                    async for raw_message in socket:
                        if not isinstance(raw_message, str):
                            continue
                        try:
                            event = json.loads(raw_message)
                        except json.JSONDecodeError:
                            continue
                        outbound = await asyncio.to_thread(
                            process_sideband_event,
                            voice_session_id,
                            event,
                        )
                        for item in outbound:
                            await socket.send(json.dumps(item, ensure_ascii=False))
                return
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, TimeoutError):
                if attempt + 1 >= attempts:
                    _mark_status(
                        voice_session_id,
                        "failed",
                        reason="sideband_reconnect_exhausted",
                    )
                    return
            except Exception:
                _mark_status(
                    voice_session_id,
                    "failed",
                    reason="sideband_unhandled_error",
                )
                return

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


def process_sideband_event(
    voice_session_id: str,
    event: dict[str, Any],
) -> list[dict]:
    event_type = str(event.get("type", ""))
    if event_type == "conversation.item.input_audio_transcription.completed":
        transcript = str(event.get("transcript", "")).strip()
        if transcript:
            return _process_final_transcript(
                voice_session_id,
                transcript=transcript,
                provider_item_id=_optional_str(event.get("item_id")),
            )
        return []

    function_call = extract_function_call(event)
    if function_call is not None:
        return _process_function_call(voice_session_id, **function_call)
    return []


def extract_function_call(event: dict[str, Any]) -> dict[str, str] | None:
    if event.get("type") == "response.function_call_arguments.done":
        name = _optional_str(event.get("name"))
        call_id = _optional_str(event.get("call_id"))
        arguments = _optional_str(event.get("arguments")) or "{}"
        if name and call_id:
            return {"name": name, "call_id": call_id, "arguments": arguments}
    if event.get("type") != "response.done":
        return None
    response = event.get("response")
    if not isinstance(response, dict):
        return None
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        name = _optional_str(item.get("name"))
        call_id = _optional_str(item.get("call_id"))
        arguments = _optional_str(item.get("arguments")) or "{}"
        if name and call_id:
            return {"name": name, "call_id": call_id, "arguments": arguments}
    return None


def _process_final_transcript(
    voice_session_id: str,
    *,
    transcript: str,
    provider_item_id: str | None,
) -> list[dict]:
    started = perf_counter()
    with SessionLocal() as db:
        voice_session = db.get(VoiceSession, voice_session_id)
        if voice_session is None or voice_session.status not in {
            "active",
            "reconnecting",
        }:
            return []
        state = command_context_state(
            db,
            session_id=voice_session.learning_session_id,
        )
        command = parse_deterministic_command(
            transcript,
            VoiceCommandContext(**state),
        )
        route = "deterministic_command" if command.is_confident else "realtime_tool"
        turn = record_final_transcript(
            db,
            voice_session=voice_session,
            transcript=transcript,
            provider_item_id=provider_item_id,
            route=route,
            intent=command.action,
            tool_name="apply_learning_action" if command.is_confident else None,
        )
        if not command.is_confident:
            _record_processing_latency(turn, started)
            db.commit()
            return []
        if not command.allowed:
            _record_processing_latency(turn, started)
            db.commit()
            return [_speak_event(f"지금은 그 동작을 할 수 없어요. {command.reason}.")]
        if command.action in {"stop", "mute"}:
            turn.interrupted = True
            _record_processing_latency(turn, started)
            db.commit()
            return [
                {"type": "response.cancel"},
                {"type": "output_audio_buffer.clear"},
            ]
        if command.action in {"repeat", "concise"}:
            _record_processing_latency(turn, started)
            db.commit()
            return [_speak_event(_ACKNOWLEDGEMENTS[command.action])]
        result = apply_learning_action(
            db,
            session_id=voice_session.learning_session_id,
            action=str(command.action),
            choice_id=command.choice_id,
            source="voice_deterministic",
        )
        turn.tool_name = "apply_learning_action"
        _record_processing_latency(turn, started)
        db.commit()
        return [
            _speak_event(
                _ACKNOWLEDGEMENTS.get(
                    str(command.action),
                    f"{result['action']} 동작을 적용했어요.",
                )
            )
        ]


def _process_function_call(
    voice_session_id: str,
    *,
    name: str,
    call_id: str,
    arguments: str,
) -> list[dict]:
    with SessionLocal() as db:
        voice_session = db.get(VoiceSession, voice_session_id)
        if voice_session is None or voice_session.status not in {
            "active",
            "reconnecting",
        }:
            return []
        existing = db.scalar(select_voice_turn(voice_session.id, call_id))
        if existing is not None:
            output = {
                "status": "duplicate",
                "message": "This tool call was already processed.",
            }
            return _function_output_events(call_id, output)
        try:
            payload = json.loads(arguments)
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict):
            output = {"status": "rejected", "message": "Tool arguments must be an object."}
        elif name not in realtime_tool_names():
            output = {"status": "rejected", "message": "Unknown tool."}
        else:
            turn = VoiceTurn(
                voice_session_id=voice_session.id,
                role="assistant",
                transcript=None,
                transcript_status="tool_call",
                route="realtime_tool",
                tool_name=name,
                provider_call_id=call_id,
                context_snapshot=context_snapshot(
                    db,
                    db.get(LearningSession, voice_session.learning_session_id),
                ),
            )
            db.add(turn)
            db.flush()
            tool_started = perf_counter()
            try:
                output = _dispatch_tool(
                    db,
                    voice_session,
                    name=name,
                    payload=payload,
                    call_id=call_id,
                    turn_id=turn.id,
                )
            except ValueError as exc:
                output = {"status": "rejected", "message": str(exc)}
            if name == "answer_with_repository_evidence" and output.get("message_id"):
                turn.chat_message_id = str(output["message_id"])
            _record_processing_latency(turn, tool_started)
            db.commit()
        return _function_output_events(call_id, output)


def _record_processing_latency(turn: VoiceTurn, started: float) -> None:
    elapsed_ms = max(1, round((perf_counter() - started) * 1_000))
    turn.speech_end_to_ack_ms = elapsed_ms
    turn.completed_ms = elapsed_ms


def _dispatch_tool(
    db,
    voice_session: VoiceSession,
    *,
    name: str,
    payload: dict,
    call_id: str,
    turn_id: str | None = None,
) -> dict:
    if name == "apply_learning_action":
        return apply_learning_action(
            db,
            session_id=voice_session.learning_session_id,
            action=str(payload.get("action", "")),
            choice_id=_optional_str(payload.get("choice_id")),
            source="voice_tool",
        )
    if name == "answer_with_repository_evidence":
        question = str(payload.get("question", "")).strip()
        if not question:
            raise ValueError("A question is required")
        answer = create_grounded_message(
            db,
            session_id=voice_session.chat_session_id,
            content=question,
            preferred_style_override=_optional_str(payload.get("answer_depth")),
            metadata_overrides={
                "modality": "voice",
                "voice_session_id": voice_session.id,
                "voice_turn_id": turn_id,
                "route": "grounded_answer",
            },
        )
        return {
            "status": answer.status,
            "message_id": answer.id,
            "voice_summary": answer.voice_summary or answer.answer[:400],
            "evidence_ids": [citation.evidence_id for citation in answer.citations],
        }
    if name == "start_deep_learning_task":
        task_type = str(payload.get("task_type", ""))
        request = str(payload.get("request", "")).strip()
        if not request:
            raise ValueError("A deep task request is required")
        task = create_learning_deep_task(
            db,
            session_id=voice_session.learning_session_id,
            kind=task_type,
            prompt=request,
            idempotency_key=f"voice:{voice_session.id}:{call_id}",
            modality="voice",
            source_policy=_optional_str(payload.get("source_policy")),
        )
        return {
            "task_id": task.id,
            "status": task.status,
            "task_type": task.kind,
            "acknowledgement": "심층 작업을 시작했어요. 진행 중에도 계속 질문할 수 있어요.",
        }
    raise ValueError("Unknown tool")


def select_voice_turn(voice_session_id: str, provider_call_id: str):
    from sqlalchemy import select

    return select(VoiceTurn).where(
        VoiceTurn.voice_session_id == voice_session_id,
        VoiceTurn.provider_call_id == provider_call_id,
    )


def _function_output_events(call_id: str, output: dict) -> list[dict]:
    return [
        {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(output, ensure_ascii=False),
            },
        },
        {"type": "response.create"},
    ]


def _speak_event(text: str) -> dict:
    return {
        "type": "response.create",
        "response": {
            "conversation": "none",
            "output_modalities": ["audio"],
            "instructions": (
                "다음 확인 문장만 한국어로 읽고 새로운 사실을 추가하지 마세요.\n\n" + text
            ),
        },
    }


def _mark_status(
    voice_session_id: str,
    status: str,
    *,
    reason: str | None = None,
) -> None:
    with SessionLocal() as db:
        voice_session = db.get(VoiceSession, voice_session_id)
        if voice_session is None or voice_session.status == "ended":
            return
        voice_session.status = status
        voice_session.last_event_at = utc_now()
        if status == "failed":
            voice_session.ended_at = voice_session.last_event_at
            voice_session.disconnect_reason = reason
        db.commit()


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


sideband_session_manager = SidebandSessionManager()
