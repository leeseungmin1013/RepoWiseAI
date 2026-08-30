from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.api import chat
from app.retrieval.evidence import ResolvedEvidence
from app.schemas import ChatMessageCreate
from app.services import grounded_chat


class FakeSession:
    def __init__(self, scalar_results: list[object]) -> None:
        self.scalar_results = iter(scalar_results)
        self.added: list[object] = []
        self.commits = 0

    def scalar(self, _statement):
        return next(self.scalar_results)

    def get(self, _model, _identifier):
        raise AssertionError("No learning session lookup was expected")

    def add(self, instance) -> None:
        self.added.append(instance)
        if len(self.added) == 1:
            instance.id = "msg_user"
        else:
            instance.id = "msg_assistant"
            instance.created_at = datetime(2026, 7, 13, tzinfo=UTC)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1


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
        score=0.4,
        retrievers=["exact"],
        content="export async function login() {}",
        symbol_name="login",
    )


def test_create_grounded_message_persists_the_existing_response_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = SimpleNamespace(
        id="snap_1", status="ready", chunk_count=3, index_version="structure-v1"
    )
    session = SimpleNamespace(
        id="ses_1",
        snapshot=snapshot,
        learning_session_id=None,
        current_selection={},
        preferred_style="beginner",
        teaching_state={},
    )
    selected_file = SimpleNamespace(id="file_1", line_count=30)
    db = FakeSession([session, selected_file])
    evidence = [_evidence("ev_used"), _evidence("ev_unused")]
    retrieval_kwargs: dict = {}

    class FakeRetriever:
        def __init__(self, _settings) -> None:
            pass

        def retrieve(self, _db, **kwargs):
            retrieval_kwargs.update(kwargs)
            return SimpleNamespace(
                hits=["hit_1"],
                analysis=SimpleNamespace(intent="code_explanation"),
                run=SimpleNamespace(id="run_1"),
            )

    class FakeRegistry:
        def resolve(self, _db, hits):
            assert hits == ["hit_1"]
            return evidence

    class FakeGenerator:
        def __init__(self, _settings) -> None:
            pass

        def generate(self, question, resolved, **kwargs):
            assert question == "로그인 함수를 설명해줘"
            assert resolved == evidence
            assert kwargs == {"preferred_style": "beginner", "learning_context": {}}
            return SimpleNamespace(
                answer="로그인 함수 설명",
                status="answered",
                mode="openai",
                model_name="test-model",
                evidence_ids=["ev_used", "ev_unknown"],
                follow_up="호출부도 볼까요?",
                voice_summary="로그인 함수의 핵심 흐름을 설명했어요.",
            )

    monkeypatch.setattr(grounded_chat, "get_settings", lambda: object())
    monkeypatch.setattr(grounded_chat, "HybridRetriever", FakeRetriever)
    monkeypatch.setattr(grounded_chat, "EvidenceRegistry", FakeRegistry)
    monkeypatch.setattr(grounded_chat, "GroundedAnswerGenerator", FakeGenerator)

    response = grounded_chat.create_grounded_message(
        db,
        session_id="ses_1",
        content="  로그인 함수를 설명해줘  ",
        requested_selection={"file_id": "file_1", "start_line": 10, "end_line": 20},
        metadata_overrides={"modality": "voice", "voice_turn_id": "vturn_1"},
    )

    assert response.model_dump(mode="json") == {
        "id": "msg_assistant",
        "session_id": "ses_1",
        "question": "로그인 함수를 설명해줘",
        "answer": "로그인 함수 설명",
        "status": "answered",
        "intent": "code_explanation",
        "retrieval_run_id": "run_1",
        "citations": [
            {
                "evidence_id": "ev_used",
                "source_type": "repository_code",
                "snapshot_id": "snap_1",
                "file_id": "file_1",
                "path": "src/auth.ts",
                "language": "typescript",
                "title": "src/auth.ts#login",
                "chunk_type": "symbol",
                "start_line": 10,
                "end_line": 20,
                "preview": "export async function login() {}",
                "score": 0.4,
                "retrievers": ["exact"],
            }
        ],
        "follow_up": "호출부도 볼까요?",
        "voice_summary": "로그인 함수의 핵심 흐름을 설명했어요.",
        "generation_mode": "openai",
        "model_name": "test-model",
        "created_at": "2026-07-13T00:00:00Z",
    }
    assert retrieval_kwargs["message_id"] == "msg_user"
    assert retrieval_kwargs["query"] == "로그인 함수를 설명해줘"
    assert retrieval_kwargs["selection"] == {
        "file_id": "file_1",
        "start_line": 10,
        "end_line": 20,
    }
    assert db.added[0].structured_payload == {
        "selection": retrieval_kwargs["selection"],
        "learning_context": {},
    }
    assert db.added[1].model_metadata == {
        "mode": "openai",
        "model": "test-model",
        "preferred_style": "beginner",
        "index_version": "structure-v1",
        "learning_context": {},
        "generation_latency_ms": 0,
        "retrieval_latency_ms": 0,
        "modality": "voice",
        "voice_turn_id": "vturn_1",
    }
    assert db.added[1].structured_payload == response.model_dump(mode="json")
    assert db.commits == 1


def test_semantic_cache_shadow_records_candidates_without_replacing_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = SimpleNamespace(
        id="snap_1", status="ready", chunk_count=3, index_version="structure-v1"
    )
    session = SimpleNamespace(
        id="ses_1",
        snapshot=snapshot,
        learning_session_id=None,
        current_selection={},
        preferred_style="beginner",
        teaching_state={},
        organization_id="org_1",
        user_id="user_1",
    )
    db = FakeSession([session])
    evidence = [_evidence("ev_live")]
    live_hit = SimpleNamespace(evidence_id="ev_live")

    cached_retrieval = SimpleNamespace(
        status="exact_hit",
        similarity=1.0,
        entry=SimpleNamespace(source_run_id="run_cached"),
        hits=["cached_hit"],
    )
    cached_generation = SimpleNamespace(
        status="semantic_hit",
        similarity=0.99,
    )

    class FakeCacheService:
        def __init__(self, _settings) -> None:
            self.lookups = 0

        def context_fingerprint(self, *_args, **_kwargs) -> str:
            return "context"

        def lookup(self, _db, *, kind, **_kwargs):
            self.lookups += 1
            return cached_retrieval if kind == "retrieval" else cached_generation

        def store(self, *_args, **_kwargs) -> None:
            pass

    class FakeRetriever:
        def __init__(self, _settings) -> None:
            pass

        def retrieve(self, _db, **_kwargs):
            return SimpleNamespace(
                hits=[live_hit],
                analysis=SimpleNamespace(intent="code_explanation"),
                run=SimpleNamespace(id="run_live", cache_status=None, cache_similarity=None),
                query_embedding=[0.1],
            )

    class FakeRegistry:
        def resolve(self, _db, hits):
            assert hits == [live_hit]
            return evidence

    class FakeGenerator:
        def __init__(self, _settings) -> None:
            pass

        def generate(self, *_args, **_kwargs):
            return SimpleNamespace(
                answer="실시간 생성 답변",
                status="answered",
                mode="openai",
                model_name="test-model",
                evidence_ids=["ev_live"],
                follow_up=None,
                voice_summary=None,
                usage={},
            )

    class FakeUsageService:
        def __init__(self, _settings) -> None:
            pass

        def reserve(self, *_args, **_kwargs):
            return SimpleNamespace(id="reserve_1")

        def settle(self, *_args, **_kwargs) -> None:
            pass

        def current_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(
                period_end=datetime(2026, 8, 31, tzinfo=UTC),
                remaining_micro_usd=200_000,
                reserved_micro_usd=0,
            )

    settings = SimpleNamespace(
        semantic_cache_shadow_mode=True,
        generation_model="test-model",
        chat_generation_reservation_micro_usd=100_000,
    )
    monkeypatch.setattr(grounded_chat, "get_settings", lambda: settings)
    monkeypatch.setattr(grounded_chat, "SemanticCacheService", FakeCacheService)
    monkeypatch.setattr(grounded_chat, "HybridRetriever", FakeRetriever)
    monkeypatch.setattr(grounded_chat, "EvidenceRegistry", FakeRegistry)
    monkeypatch.setattr(grounded_chat, "GroundedAnswerGenerator", FakeGenerator)
    monkeypatch.setattr(grounded_chat, "UsageService", FakeUsageService)

    response = grounded_chat.create_grounded_message(
        db,
        session_id="ses_1",
        content="로그인 함수를 설명해줘",
    )

    assert response.answer == "실시간 생성 답변"
    assert response.retrieval_run_id == "run_live"
    assert response.cache is not None
    assert response.cache.retrieval == "miss"
    assert response.cache.generation == "miss"
    assert db.added[1].model_metadata["shadow_cache"] == {
        "retrieval": "exact_hit",
        "generation": "semantic_hit",
    }


def test_rest_create_message_delegates_to_grounded_chat_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()
    expected = object()
    captured: dict = {}

    def fake_create_grounded_message(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(chat, "create_grounded_message", fake_create_grounded_message)
    payload = ChatMessageCreate(
        content="이 코드를 설명해줘",
        selection={"file_id": "file_1", "start_line": 4, "end_line": 8},
    )

    result = chat.create_message("ses_1", payload, db)

    assert result is expected
    assert captured == {
        "args": (db,),
        "kwargs": {
            "session_id": "ses_1",
            "content": "이 코드를 설명해줘",
            "requested_selection": {"file_id": "file_1", "start_line": 4, "end_line": 8},
            "metadata_overrides": {"modality": "text"},
        },
    }
