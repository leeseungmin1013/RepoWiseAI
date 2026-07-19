from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services import research_materials


class FakeResponse:
    output_parsed = research_materials._ResearchPayload(
        answer="공식 문서를 학습 순서에 맞춰 골랐습니다.",
        voice_summary="공식 문서를 찾았습니다.",
        sources=[
            {
                "title": "FastAPI Tutorial",
                "publisher": "FastAPI",
                "url": "https://fastapi.tiangolo.com/tutorial/",
                "difficulty": "beginner",
                "estimated_minutes": 30,
                "recommendation_reason": "현재 API 구조를 이해하기 좋습니다.",
            },
            {
                "title": "Invented page",
                "publisher": "FastAPI",
                "url": "https://fastapi.tiangolo.com/not-in-search",
                "difficulty": "intermediate",
                "estimated_minutes": 20,
                "recommendation_reason": "검색 근거가 없는 주소입니다.",
            },
            {
                "title": "Unofficial blog",
                "publisher": "Blog",
                "url": "https://example.com/fastapi",
                "difficulty": "beginner",
                "estimated_minutes": 10,
                "recommendation_reason": "공식 도메인이 아닙니다.",
            },
        ],
    )

    def model_dump(self, **_kwargs):
        return {
            "output": [{"type": "web_search_call", "action": {"sources": [
                {"type": "url_citation", "url": "https://fastapi.tiangolo.com/tutorial/"},
                {"type": "source", "url": "https://example.com/fastapi"},
            ]}}]
        }


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch, response: FakeResponse, captured: dict):
    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return response

    monkeypatch.setitem(
        __import__("sys").modules,
        "openai",
        SimpleNamespace(OpenAI=lambda **_kwargs: SimpleNamespace(responses=FakeResponses())),
    )


def test_research_keeps_only_cited_official_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    _install_fake_openai(monkeypatch, FakeResponse(), captured)
    result = research_materials.research_official_materials(
        "FastAPI 공식 학습자료를 찾아줘",
        settings=Settings(
            openai_api_key="test-key",
            research_allowed_domains="fastapi.tiangolo.com",
            research_max_sources=3,
        ),
        preferred_style="beginner",
    )

    assert [str(source.url) for source in result.sources] == [
        "https://fastapi.tiangolo.com/tutorial"
    ]
    assert captured["tools"][0]["filters"]["allowed_domains"] == [
        "fastapi.tiangolo.com"
    ]
    assert captured["store"] is False
    assert captured["background"] is False


def test_research_fails_closed_without_a_cited_official_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse()
    response.output_parsed = research_materials._ResearchPayload(
        answer="자료",
        sources=[{
            "title": "Bad", "publisher": "Bad", "url": "https://example.com/bad",
            "difficulty": "beginner", "estimated_minutes": 5,
            "recommendation_reason": "Bad",
        }],
    )
    _install_fake_openai(monkeypatch, response, {})

    with pytest.raises(ValueError, match="no cited official-domain"):
        research_materials.research_official_materials(
            "자료",
            settings=Settings(
                openai_api_key="test-key",
                research_allowed_domains="fastapi.tiangolo.com",
            ),
            preferred_style="beginner",
        )
