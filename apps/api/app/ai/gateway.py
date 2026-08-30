from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services.usage import UsageContext, UsageService


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    embedding_tokens: int = 0
    audio_input_tokens: int = 0
    audio_output_tokens: int = 0
    transcription_seconds: int = 0
    tool_calls: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def extract_usage(response: Any, *, embedding: bool = False) -> ProviderUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return ProviderUsage()
    input_tokens = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(
        getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
    )
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    return ProviderUsage(
        input_tokens=0 if embedding else input_tokens,
        embedding_tokens=input_tokens if embedding else 0,
        cached_input_tokens=int(getattr(input_details, "cached_tokens", 0) or 0),
        output_tokens=output_tokens,
        reasoning_tokens=int(getattr(output_details, "reasoning_tokens", 0) or 0),
    )


class UsageRecorder:
    def __init__(
        self,
        db: Session,
        *,
        context: UsageContext,
        reservation_id: str | None,
        provider: str,
        model: str,
    ) -> None:
        self.db = db
        self.context = context
        self.reservation_id = reservation_id
        self.provider = provider
        self.model = model

    def __call__(self, response: Any, *, embedding: bool = False) -> None:
        usage = extract_usage(response, embedding=embedding)
        UsageService().settle(
            self.db,
            reservation_id=self.reservation_id,
            context=self.context,
            provider=self.provider,
            model=self.model,
            usage=usage.as_dict(),
            provider_request_id=getattr(response, "id", None),
        )


class MeteredOpenAIClient:
    """The only synchronous OpenAI SDK construction point in the application."""

    def __init__(
        self,
        api_key: str,
        recorder: Callable[..., None] | None = None,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        from openai import OpenAI

        options: dict[str, Any] = {"api_key": api_key}
        if timeout is not None:
            options["timeout"] = timeout
        if max_retries is not None:
            options["max_retries"] = max_retries
        self._client = OpenAI(**options)
        self._recorder = recorder

    def embeddings_create(self, **request: Any) -> Any:
        response = self._client.embeddings.create(**request)
        if self._recorder:
            self._recorder(response, embedding=True)
        return response

    def responses_parse(self, **request: Any) -> Any:
        response = self._client.responses.parse(**request)
        if self._recorder:
            self._recorder(response, embedding=False)
        return response
