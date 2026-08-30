import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.ai.answers import GroundedAnswerGenerator, OpenAIAnswerPayload
from app.core.config import Settings
from app.retrieval.evidence import ResolvedEvidence


def _evidence(evidence_id: str) -> ResolvedEvidence:
    return ResolvedEvidence(
        evidence_id=evidence_id,
        snapshot_id="snap_1",
        file_id="file_1",
        path="src/auth.ts",
        language="typescript",
        title="src/auth.ts#login",
        chunk_type="symbol",
        start_line=10,
        end_line=20,
        preview="export async function login() {}",
        score=0.1,
        retrievers=["exact"],
        content="export async function login() {}",
        symbol_name="login",
    )


def test_openai_answer_keeps_only_evidence_ids_returned_by_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_parsed=OpenAIAnswerPayload(
                    answer="로그인 함수는 비동기 작업을 시작합니다.",
                    evidence_ids=["ev_allowed", "ev_invented"],
                    follow_up="await는 왜 필요한가요?",
                    voice_summary="로그인 함수는 비동기 작업을 시작해요.",
                )
            )

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "test-key"
            self.responses = FakeResponses()

    module = ModuleType("openai")
    module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)

    answer = GroundedAnswerGenerator(
        Settings(openai_api_key="test-key", generation_provider="openai")
    ).generate("login 함수는 무슨 일을 해?", [_evidence("ev_allowed")], "beginner")

    assert answer.mode == "openai"
    assert answer.evidence_ids == ["ev_allowed"]
    assert answer.follow_up == "await는 왜 필요한가요?"
    assert answer.voice_summary == "로그인 함수는 비동기 작업을 시작해요."
    assert captured["text_format"] is OpenAIAnswerPayload
    assert "Start with unfamiliar syntax" in captured["input"][0]["content"]


def test_regular_answer_records_provider_fallback_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingResponses:
        def parse(self, **_kwargs):
            raise TimeoutError("provider timeout")

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.responses = FailingResponses()

    module = ModuleType("openai")
    module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)

    answer = GroundedAnswerGenerator(
        Settings(openai_api_key="test-key", generation_provider="openai")
    ).generate("login 함수를 설명해줘", [_evidence("ev_allowed")])

    assert answer.mode == "retrieval_only"
    assert answer.fallback_reason == "provider_error:TimeoutError"


def test_deep_answer_does_not_hide_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingResponses:
        def parse(self, **_kwargs):
            raise RuntimeError("provider failed")

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "test-key"
            self.responses = FailingResponses()

    module = ModuleType("openai")
    module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)
    generator = GroundedAnswerGenerator(
        Settings(openai_api_key="test-key", generation_provider="openai")
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        generator.generate(
            "login 함수를 설명해줘",
            [_evidence("ev_allowed")],
            allow_retrieval_fallback=False,
        )


def test_deep_answer_requires_evidence_and_openai_configuration() -> None:
    generator = GroundedAnswerGenerator(Settings(openai_api_key=None))

    with pytest.raises(ValueError, match="verified repository evidence"):
        generator.generate(
            "전체 흐름을 깊게 설명해줘",
            [],
            allow_retrieval_fallback=False,
        )

    with pytest.raises(RuntimeError, match="OpenAI generation is unavailable"):
        generator.generate(
            "전체 흐름을 깊게 설명해줘",
            [_evidence("ev_allowed")],
            allow_retrieval_fallback=False,
        )


def test_deep_answer_passes_model_reasoning_and_privacy_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_parsed=OpenAIAnswerPayload(
                    answer="심층 설명",
                    evidence_ids=["ev_allowed"],
                    follow_up=None,
                )
            )

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "test-key"
            self.responses = FakeResponses()

    module = ModuleType("openai")
    module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)
    generator = GroundedAnswerGenerator(
        Settings(openai_api_key="test-key", generation_provider="openai")
    )

    answer = generator.generate(
        "login 함수를 깊게 설명해줘",
        [_evidence("ev_allowed")],
        model_name="terra-test",
        reasoning_effort="medium",
        allow_retrieval_fallback=False,
    )

    assert answer.model_name == "terra-test"
    assert captured["model"] == "terra-test"
    assert captured["reasoning"] == {"effort": "medium"}
    assert captured["background"] is False
    assert captured["store"] is False
