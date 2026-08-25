from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.ai.gateway import MeteredOpenAIClient
from app.core.config import Settings
from app.schemas import ResearchMaterialsResponse, ResearchSourceResponse


class _ProposedSource(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    publisher: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=2_048)
    difficulty: Literal["beginner", "intermediate", "advanced"]
    estimated_minutes: int = Field(ge=1, le=240)
    recommendation_reason: str = Field(min_length=1, max_length=500)


class _ResearchPayload(BaseModel):
    answer: str = Field(min_length=1, max_length=8_000)
    voice_summary: str | None = Field(default=None, max_length=600)
    sources: list[_ProposedSource] = Field(min_length=1, max_length=8)


def _normalized_url(value: str) -> str:
    parsed = urlparse(value)
    return parsed._replace(fragment="").geturl().rstrip("/")


def _is_allowed_url(value: str, allowed_domains: set[str]) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme == "https"
        and bool(host)
        and any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)
    )


def _all_urls(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str):
            found.add(_normalized_url(url))
        for child in value.values():
            found.update(_all_urls(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_all_urls(child))
    return found


def _citation_urls(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        annotations = value.get("annotations")
        if annotations is not None:
            found.update(_all_urls(annotations))
        action = value.get("action")
        if isinstance(action, dict) and action.get("sources") is not None:
            found.update(_all_urls(action["sources"]))
        for child in value.values():
            found.update(_citation_urls(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_citation_urls(child))
    return found


def research_official_materials(
    prompt: str,
    *,
    settings: Settings,
    preferred_style: str,
    recorder: Callable[..., None] | None = None,
) -> ResearchMaterialsResponse:
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API key is required for verified material research")

    allowed_domains = set(settings.research_allowed_domain_list)
    if not allowed_domains:
        raise RuntimeError("No official research domains are configured")

    client = MeteredOpenAIClient(settings.openai_api_key, recorder=recorder)
    response = client.responses_parse(
        model=settings.research_model,
        reasoning={"effort": settings.research_reasoning_effort},
        background=False,
        store=False,
        tools=[
            {
                "type": "web_search",
                "filters": {"allowed_domains": sorted(allowed_domains)},
                "search_context_size": "medium",
            }
        ],
        tool_choice="auto",
        include=["web_search_call.action.sources"],
        input=[
            {
                "role": "system",
                "content": (
                    "You are RepoWise AI's learning-material researcher. Search the web and "
                    "recommend only official documentation or official learning resources. "
                    "Return Korean explanations. Every source URL must come directly from the "
                    "web-search results. Prefer focused pages over home pages. Do not invent URLs. "
                    f"Adapt difficulty for a {preferred_style} learner and return at most "
                    f"{settings.research_max_sources} sources. voice_summary must be one or two "
                    "short Korean sentences without URLs."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        text_format=_ResearchPayload,
    )
    payload = response.output_parsed
    if payload is None:
        raise ValueError("Research response did not contain structured output")

    cited_urls = _citation_urls(response.model_dump(mode="json"))
    checked_at = datetime.now(UTC)
    verified: list[ResearchSourceResponse] = []
    seen: set[str] = set()
    for source in payload.sources:
        url = _normalized_url(str(source.url))
        if url in seen or not _is_allowed_url(url, allowed_domains) or url not in cited_urls:
            continue
        seen.add(url)
        verified.append(
            ResearchSourceResponse(
                **source.model_dump(exclude={"url"}),
                url=url,
                checked_at=checked_at,
            )
        )
        if len(verified) >= settings.research_max_sources:
            break
    if not verified:
        raise ValueError("Research returned no cited official-domain sources")

    return ResearchMaterialsResponse(
        answer=payload.answer.strip(),
        voice_summary=payload.voice_summary.strip() if payload.voice_summary else None,
        sources=verified,
        model_name=settings.research_model,
    )
