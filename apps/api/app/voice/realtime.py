from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.model_routing import ModelRoutingPolicy
from app.voice.schemas import REALTIME_FUNCTION_TOOLS

REALTIME_TUTOR_INSTRUCTIONS = """You are the voice renderer for RepoWise AI.
The application uses your input transcription events to retrieve verified repository evidence.
Never answer the learner's microphone input on your own.
Only speak when response-specific instructions provide verified Korean text to render.
Use the provided function tools for repository facts, deep work, and learning state changes.
Never put learning_session_id, lesson_id, file_id, or mastery values in tool arguments.
Keep the supplied meaning, do not invent code facts, file paths, URLs, or citations.
"""


class RealtimeUnavailable(RuntimeError):
    """Raised when a Realtime session cannot be initialized."""


@dataclass(frozen=True)
class RealtimeCallAnswer:
    sdp: str
    call_id: str | None
    location: str | None


def build_realtime_session_config(
    settings: Settings,
    *,
    vad_enabled: bool = False,
) -> dict:
    route = ModelRoutingPolicy.from_settings(settings).for_role("realtime")
    return {
        "type": "realtime",
        "model": route.model,
        "output_modalities": ["audio"],
        "instructions": REALTIME_TUTOR_INSTRUCTIONS,
        "tools": REALTIME_FUNCTION_TOOLS,
        "tool_choice": "auto",
        "reasoning": {"effort": route.reasoning_effort},
        "audio": {
            "input": {
                "transcription": {
                    "model": settings.realtime_transcription_model,
                    "language": settings.realtime_language,
                    "delay": settings.realtime_transcription_delay,
                },
                "turn_detection": (
                    {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                        "create_response": True,
                        "interrupt_response": True,
                    }
                    if vad_enabled
                    else None
                ),
            },
            "output": {"voice": settings.realtime_voice},
        },
    }


class OpenAIRealtimeClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    async def create_call(
        self,
        *,
        sdp_offer: str,
        safety_identifier: str,
        vad_enabled: bool = False,
    ) -> RealtimeCallAnswer:
        if not self.settings.openai_api_key:
            raise RealtimeUnavailable("OPENAI_API_KEY is required for realtime voice")

        timeout = httpx.Timeout(
            self.settings.realtime_request_timeout_seconds,
            connect=self.settings.realtime_connect_timeout_seconds,
        )
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Accept": "application/sdp",
            "OpenAI-Safety-Identifier": safety_identifier,
        }
        files = {
            "sdp": (None, sdp_offer, "application/sdp"),
            "session": (
                None,
                json.dumps(
                    build_realtime_session_config(self.settings, vad_enabled=vad_enabled),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "application/json",
            ),
        }
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    self.settings.realtime_api_url,
                    headers=headers,
                    files=files,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RealtimeUnavailable(
                f"OpenAI Realtime returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RealtimeUnavailable("OpenAI Realtime connection failed") from exc

        location = response.headers.get("location")
        call_id = _call_id_from_location(location)
        return RealtimeCallAnswer(sdp=response.text, call_id=call_id, location=location)

    async def hangup_call(self, call_id: str) -> None:
        if not self.settings.openai_api_key:
            raise RealtimeUnavailable("OPENAI_API_KEY is required for realtime voice")
        url = self.settings.realtime_api_url.rstrip("/") + f"/{call_id}/hangup"
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.realtime_request_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key}",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise RealtimeUnavailable(
                    f"OpenAI Realtime hangup returned HTTP {exc.response.status_code}"
                ) from exc
        except httpx.HTTPError as exc:
            raise RealtimeUnavailable("OpenAI Realtime hangup failed") from exc


def _call_id_from_location(location: str | None) -> str | None:
    if not location:
        return None
    return location.rstrip("/").rsplit("/", 1)[-1] or None
