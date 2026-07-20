from types import SimpleNamespace

import pytest

from app.navigation import change_brief as change_brief_module
from app.navigation.change_brief import build_change_brief, generate_change_brief
from app.schemas import CodeSelection


def _snapshot():
    return SimpleNamespace(
        id="snap_1",
        commit_sha="abc123",
        parser_version="semantic-ts-v2",
        status="ready",
    )


def _file(file_id: str, path: str):
    return SimpleNamespace(id=file_id, path=path, line_count=80)


def _symbol(symbol_id: str, file_id: str, name: str, start: int, end: int):
    return SimpleNamespace(
        id=symbol_id,
        file_id=file_id,
        display_name=name,
        start_line=start,
        end_line=end,
    )


def _edge(**overrides):
    values = {
        "id": "edge_1",
        "source_file_id": "file_route",
        "source_symbol_id": "sym_route",
        "target_symbol_id": "sym_store",
        "target_path": "src/store.ts",
        "relation": "WRITES",
        "confidence": 0.97,
        "source_start_line": 12,
        "source_end_line": 14,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_change_brief_separates_confirmed_effects_and_assigns_high_risk() -> None:
    route = _file("file_route", "src/route.ts")
    store = _file("file_store", "src/store.ts")
    route_symbol = _symbol("sym_route", route.id, "updateUser", 8, 24)
    store_symbol = _symbol("sym_store", store.id, "saveUser", 20, 35)

    brief = build_change_brief(
        snapshot=_snapshot(),
        prompt="사용자 저장 결과를 바꾸면 어디가 달라질까?",
        selection=CodeSelection(file_id=route.id, start_line=12, end_line=14),
        selected_file=route,
        files=[route, store],
        symbols=[route_symbol, store_symbol],
        edges=[_edge()],
    )

    assert brief.risk_level == "high"
    assert [impact.relation_type for impact in brief.confirmed_direct_impacts] == ["WRITES"]
    assert brief.possible_impacts_to_verify == []
    assert [item.evidence.path for item in brief.candidate_locations] == [
        "src/route.ts",
        "src/store.ts",
    ]
    assert all(item.evidence for item in brief.candidate_locations)
    assert "실제 패치는 적용하지 않았습니다" in brief.limitations[0]


def test_change_brief_does_not_claim_low_risk_when_relations_are_missing() -> None:
    route = _file("file_route", "src/route.ts")

    brief = build_change_brief(
        snapshot=_snapshot(),
        prompt="이 코드를 바꾸고 싶어",
        selection=CodeSelection(file_id=route.id, start_line=1, end_line=3),
        selected_file=route,
        files=[route],
        symbols=[],
        edges=[],
    )

    assert brief.risk_level == "unknown"
    assert brief.confirmed_direct_impacts == []
    assert brief.possible_impacts_to_verify[0].confidence == "unknown"
    assert "낮다고 단정할 수 없습니다" in brief.risk_rationale


def test_change_brief_reuses_valid_versioned_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()
    route = _file("file_route", "src/route.ts")
    selection = CodeSelection(file_id=route.id, start_line=1, end_line=3)
    cached = build_change_brief(
        snapshot=snapshot,
        prompt="이 코드를 바꾸고 싶어",
        selection=selection,
        selected_file=route,
        files=[route],
        symbols=[],
        edges=[],
    )
    session = SimpleNamespace(id="ses_1", snapshot_id=snapshot.id)
    task = SimpleNamespace(
        chat_session_id=session.id,
        prompt=cached.request_summary,
        selection=selection.model_dump(),
        context_json={"navigation_context": {}},
    )

    class CacheDb:
        def get(self, model, _identifier):
            return session if model.__name__ == "ChatSession" else snapshot

        def scalars(self, _statement):
            pytest.fail("cache hit must not query files, symbols, or edges")

    monkeypatch.setattr(
        change_brief_module,
        "load_navigation_artifact",
        lambda *_args, **_kwargs: cached,
    )
    monkeypatch.setattr(
        change_brief_module,
        "write_navigation_artifacts",
        lambda *_args, **_kwargs: pytest.fail("cache hit must not write"),
    )

    assert generate_change_brief(CacheDb(), task) == cached
