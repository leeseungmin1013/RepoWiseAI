from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.core.config import Settings

REALTIME_TUTOR_INSTRUCTIONS = """You are the voice renderer for RepoWise AI.
The application uses your input transcription events to retrieve verified repository evidence.
Never answer the learner's microphone input on your own.
Only speak when response-specific instructions provide verified Korean text to render.
Keep the supplied meaning, do not invent code facts, file paths, URLs, or citations.
"""


class RealtimeUnavailable(RuntimeError):
    """Raised when a Realtime session cannot be initialized."""


@dataclass(frozen=True)
class RealtimeCallAnswer:
    sdp: str
    call_id: str | None
    location: str | None


def build_realtime_session_config(settings: Settings) -> dict:
    return {
        "type": "realtime",
        "model": settings.realtime_model,
        "output_modalities": ["audio"],
        "instructions": REALTIME_TUTOR_INSTRUCTIONS,
        "reasoning": {"effort": settings.realtime_reasoning_effort},
        "audio": {
            "input": {
                "transcription": {
                    "model": settings.realtime_transcription_model,
                    "language": settings.realtime_language,
                    "delay": settings.realtime_transcription_delay,
                },
                "turn_detection": None,
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
                    build_realtime_session_config(self.settings),
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


def _call_id_from_location(location: str | None) -> str | None:
    if not location:
        return None
    return location.rstrip("/").rsplit("/", 1)[-1] or None
