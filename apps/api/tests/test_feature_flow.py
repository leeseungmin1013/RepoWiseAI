from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import repositories
from app.core.db import get_db
from app.models import (
    FileRecord,
    NavigationArtifact,
    Repository,
    RepositorySnapshot,
    Symbol,
    SymbolEdge,
)
from app.navigation.feature_flow import build_feature_flow, build_feature_flows


def _file(file_id: str, path: str, content: str) -> FileRecord:
    return FileRecord(
        id=file_id,
        snapshot_id="snap_flow",
        path=path,
        language="tsx" if path.endswith(".tsx") else "typescript",
        content=content,
        content_hash=f"sha256:{file_id}",
        byte_size=len(content.encode()),
        line_count=max(1, len(content.splitlines())),
        is_documentation=False,
    )


def _symbol(
    symbol_id: str,
    file_id: str,
    name: str,
    start_line: int,
    end_line: int,
) -> Symbol:
    return Symbol(
        id=symbol_id,
        snapshot_id="snap_flow",
        file_id=file_id,
        qualified_name=name,
        display_name=name,
        kind="function",
        signature=f"function {name}()",
        start_line=start_line,
        end_line=end_line,
        content_hash=f"sha256:{symbol_id}",
    )


def _edge(
    edge_id: str,
    relation: str,
    *,
    source_file_id: str = "file_form",
    source_symbol_id: str | None,
    target_symbol_id: str | None,
    target_path: str | None,
    start_line: int,
    end_line: int,
    metadata: dict,
    confidence: float = 1.0,
) -> SymbolEdge:
    return SymbolEdge(
        id=edge_id,
        snapshot_id="snap_flow",
        source_file_id=source_file_id,
        source_symbol_id=source_symbol_id,
        target_symbol_id=target_symbol_id,
        target_path=target_path,
        relation=relation,
        confidence=confidence,
        analysis_method="semantic-ts-v2",
        source_start_line=start_line,
        source_end_line=end_line,
        metadata_json=metadata,
    )


def _snapshot(status: str = "ready") -> RepositorySnapshot:
    repository = Repository(
        id="repo_flow",
        owner="example",
        name="flow-demo",
        url="https://github.com/example/flow-demo",
    )
    snapshot = RepositorySnapshot(
        id="snap_flow",
        repository_id=repository.id,
        commit_sha="commit-flow-123",
        status=status,
        parser_version="semantic-ts-v2",
        file_count=2,
    )
    snapshot.repository = repository
    snapshot.jobs = []
    return snapshot


def _verified_fixture(
    id_suffix: str = "",
) -> tuple[list[FileRecord], list[Symbol], list[SymbolEdge]]:
    form = _file(
        f"file_form{id_suffix}",
        "src/components/AskForm.tsx",
        """export function AskForm() {
  async function submitQuestion() {
    const response = await fetch("/api/ask", { method: "POST" });
    return response.json();
  }
  return <button onClick={submitQuestion}>Ask</button>;
}
""",
    )
    route = _file(
        f"file_route{id_suffix}",
        "src/app/api/ask/route.ts",
        """export async function POST(request: Request) {
  return Response.json({ ok: true });
}
""",
    )
    component = _symbol(f"sym_form{id_suffix}", form.id, "AskForm", 1, 7)
    handler = _symbol(f"sym_submit{id_suffix}", form.id, "submitQuestion", 2, 5)
    route_handler = _symbol(f"sym_post{id_suffix}", route.id, "POST", 1, 3)
    trigger = _edge(
        f"edge_trigger{id_suffix}",
        "TRIGGERS",
        source_file_id=form.id,
        source_symbol_id=component.id,
        target_symbol_id=handler.id,
        target_path="submitQuestion",
        start_line=6,
        end_line=6,
        metadata={
            "event_name": "onClick",
            "handler_identifier": "submitQuestion",
            "resolution": "local_symbol",
        },
    )
    request = _edge(
        f"edge_request{id_suffix}",
        "REQUESTS",
        source_file_id=form.id,
        source_symbol_id=handler.id,
        target_symbol_id=None,
        target_path="/api/ask",
        start_line=3,
        end_line=3,
        metadata={
            "client": "fetch",
            "http_method": "POST",
            "request_path": "/api/ask",
            "awaited": True,
            "literal": True,
            "resolution": "exact_next_app_route",
        },
    )
    handled = _edge(
        f"edge_handled{id_suffix}",
        "HANDLED_BY",
        source_file_id=form.id,
        source_symbol_id=handler.id,
        target_symbol_id=route_handler.id,
        target_path=route.path,
        start_line=3,
        end_line=3,
        metadata={
            "client": "fetch",
            "http_method": "POST",
            "request_path": "/api/ask",
            "route_file_path": route.path,
            "resolution": "exact_next_app_route",
        },
    )
    return [route, form], [route_handler, handler, component], [handled, request, trigger]


def test_builds_deterministic_verified_trigger_request_route_flow() -> None:
    files, symbols, edges = _verified_fixture()

    first = build_feature_flows(_snapshot(), files, symbols, edges)
    repeated = build_feature_flows(
        _snapshot(),
        list(reversed(files)),
        list(reversed(symbols)),
        list(reversed(edges)),
    )

    assert first.model_dump() == repeated.model_dump()
    assert first.repository_name == "example/flow-demo"
    assert first.analysis_version == "feature-flow-v2"
    assert len(first.flows) == 1
    summary = first.flows[0]
    assert summary.confidence == "verified"
    assert summary.step_count == 4
    assert summary.evidence_coverage == 1.0
    assert summary.entry_evidence.path == "src/components/AskForm.tsx"
    assert summary.entry_evidence.start_line == 6

    detail = build_feature_flow(_snapshot(), files, symbols, edges, summary.id)

    assert detail is not None
    assert [step.role for step in detail.normal_steps] == [
        "user_trigger",
        "client_handler",
        "request",
        "server_handler",
    ]
    assert [step.relation_type for step in detail.normal_steps] == [
        "TRIGGERS",
        "TRIGGERS",
        "REQUESTS",
        "HANDLED_BY",
    ]
    assert detail.normal_steps[0].previous_step_id is None
    assert detail.normal_steps[0].next_step_id == detail.normal_steps[1].id
    assert detail.normal_steps[-1].previous_step_id == detail.normal_steps[-2].id
    assert detail.normal_steps[-1].next_step_id is None
    assert detail.failure_steps == []
    assert any("failure_steps" in limitation for limitation in detail.limitations)


def test_flow_and_step_ids_are_stable_when_all_database_ids_change() -> None:
    files, symbols, edges = _verified_fixture()
    reindexed_files, reindexed_symbols, reindexed_edges = _verified_fixture("_reindexed")

    original_catalog = build_feature_flows(_snapshot(), files, symbols, edges)
    reindexed_catalog = build_feature_flows(
        _snapshot(), reindexed_files, reindexed_symbols, reindexed_edges
    )
    original = build_feature_flow(
        _snapshot(), files, symbols, edges, original_catalog.flows[0].id
    )
    reindexed = build_feature_flow(
        _snapshot(),
        reindexed_files,
        reindexed_symbols,
        reindexed_edges,
        reindexed_catalog.flows[0].id,
    )

    assert original is not None
    assert reindexed is not None
    assert original.id == reindexed.id
    assert [step.id for step in original.normal_steps] == [
        step.id for step in reindexed.normal_steps
    ]
    assert [step.previous_step_id for step in original.normal_steps] == [
        step.previous_step_id for step in reindexed.normal_steps
    ]
    assert [step.next_step_id for step in original.normal_steps] == [
        step.next_step_id for step in reindexed.normal_steps
    ]


def test_partial_flow_stops_at_known_handler_without_fabricating_request() -> None:
    files, symbols, edges = _verified_fixture()
    trigger_only = [edge for edge in edges if edge.relation == "TRIGGERS"]

    response = build_feature_flows(_snapshot(), files, symbols, trigger_only)
    detail = build_feature_flow(
        _snapshot(), files, symbols, trigger_only, response.flows[0].id
    )

    assert detail is not None
    assert detail.confidence == "inferred"
    assert [step.role for step in detail.normal_steps] == ["user_trigger", "client_handler"]
    assert all(step.relation_type != "REQUESTS" for step in detail.normal_steps)
    assert "이후 연결은 알 수 없습니다" in detail.outcome
    assert any("REQUESTS 관계가 확인되지 않아" in item for item in detail.limitations)


def test_unresolved_handler_is_an_explicit_unknown_boundary() -> None:
    files, symbols, _ = _verified_fixture()
    unresolved = _edge(
        "edge_unresolved",
        "TRIGGERS",
        source_symbol_id="sym_form",
        target_symbol_id=None,
        target_path="dynamicHandler",
        start_line=6,
        end_line=6,
        metadata={
            "event_name": "onClick",
            "handler_identifier": "dynamicHandler",
            "resolution": "unresolved",
        },
        confidence=0.55,
    )

    response = build_feature_flows(_snapshot(), files, symbols, [unresolved])
    detail = build_feature_flow(
        _snapshot(), files, symbols, [unresolved], response.flows[0].id
    )

    assert detail is not None
    assert detail.confidence == "unknown"
    assert len(detail.normal_steps) == 1
    assert detail.normal_steps[0].output_or_side_effect.endswith("확인하지 못함")
    assert any("대상 핸들러 심볼이 해석되지 않아" in item for item in detail.limitations)


def test_request_does_not_connect_to_route_with_a_different_http_method() -> None:
    files, symbols, edges = _verified_fixture()
    handled = next(edge for edge in edges if edge.relation == "HANDLED_BY")
    handled.metadata_json = {**handled.metadata_json, "http_method": "GET"}

    response = build_feature_flows(_snapshot(), files, symbols, edges)
    detail = build_feature_flow(
        _snapshot(), files, symbols, edges, response.flows[0].id
    )

    assert detail is not None
    assert [step.role for step in detail.normal_steps] == [
        "user_trigger",
        "client_handler",
        "request",
    ]
    assert all(step.relation_type != "HANDLED_BY" for step in detail.normal_steps)
    assert any("일치하는 서버 라우트 핸들러" in item for item in detail.limitations)


def test_dynamic_request_method_is_shown_as_an_unknown_boundary() -> None:
    files, symbols, edges = _verified_fixture()
    request = next(edge for edge in edges if edge.relation == "REQUESTS")
    request.metadata_json = {**request.metadata_json, "http_method": "UNKNOWN"}

    response = build_feature_flows(_snapshot(), files, symbols, edges)
    detail = build_feature_flow(
        _snapshot(), files, symbols, edges, response.flows[0].id
    )

    assert detail is not None
    assert [step.role for step in detail.normal_steps][-1] == "request"
    assert detail.normal_steps[-1].input == "메서드 미확인 /api/ask"
    assert any("HTTP 메서드가 동적으로 결정되어" in item for item in detail.limitations)


def test_request_labels_strip_query_fragment_and_url_credentials() -> None:
    files, symbols, edges = _verified_fixture()
    unsafe_url = (
        "https://alice:password@example.com/api/ask"
        "?token=query-secret&email=private@example.com#debug"
    )
    request = next(edge for edge in edges if edge.relation == "REQUESTS")
    request.target_path = unsafe_url
    request.metadata_json = {**request.metadata_json, "request_path": unsafe_url}
    handled = next(edge for edge in edges if edge.relation == "HANDLED_BY")
    handled.metadata_json = {**handled.metadata_json, "request_path": unsafe_url}

    catalog = build_feature_flows(_snapshot(), files, symbols, edges)
    detail = build_feature_flow(
        _snapshot(), files, symbols, edges, catalog.flows[0].id
    )

    assert detail is not None
    serialized = catalog.model_dump_json() + detail.model_dump_json()
    assert "https://example.com/api/ask" in serialized
    assert "alice" not in serialized
    assert "password" not in serialized
    assert "query-secret" not in serialized
    assert "private@example.com" not in serialized
    assert "#debug" not in serialized


def test_catalog_is_bounded_to_three_representative_flows() -> None:
    files, symbols, _ = _verified_fixture()
    triggers = [
        _edge(
            f"edge_trigger_{index}",
            "TRIGGERS",
            source_symbol_id="sym_form",
            target_symbol_id=None,
            target_path=f"dynamicHandler{index}",
            start_line=index,
            end_line=index,
            metadata={
                "event_name": "onClick",
                "handler_identifier": f"dynamicHandler{index}",
                "resolution": "unresolved",
            },
            confidence=0.55,
        )
        for index in range(1, 5)
    ]

    response = build_feature_flows(_snapshot(), files, symbols, triggers)

    assert len(response.flows) == 3
    assert len({flow.id for flow in response.flows}) == 3
    assert any("나머지 1개 흐름" in limitation for limitation in response.limitations)


def test_test_file_triggers_are_excluded_from_representative_catalog() -> None:
    files, symbols, edges = _verified_fixture()
    form = next(file for file in files if file.id == "file_form")
    form.path = "src/components/__tests__/AskForm.test.tsx"

    response = build_feature_flows(_snapshot(), files, symbols, edges)

    assert response.flows == []
    assert any(
        "테스트·스토리·fixture 파일의 trigger 1개" in limitation
        for limitation in response.limitations
    )


def test_catalog_requests_reanalysis_for_an_old_semantic_graph_version() -> None:
    files, symbols, edges = _verified_fixture()
    snapshot = _snapshot()
    snapshot.parser_version = "tree-sitter-v1"

    response = build_feature_flows(snapshot, files, symbols, edges)

    assert any(
        "semantic-ts-v2 의미 관계를 얻으려면 저장소를 다시 분석해야 합니다"
        in limitation
        for limitation in response.limitations
    )


def test_extends_flow_through_read_external_service_and_navigation() -> None:
    files, symbols, edges = _verified_fixture()
    form = next(file for file in files if file.id == "file_form")
    route = next(file for file in files if file.id == "file_route")
    handler = next(symbol for symbol in symbols if symbol.id == "sym_submit")
    route_handler = next(symbol for symbol in symbols if symbol.id == "sym_post")
    effects = [
        _edge(
            "edge_read",
            "READS",
            source_file_id=form.id,
            source_symbol_id=handler.id,
            target_symbol_id=None,
            target_path="storage:localStorage:draft",
            start_line=2,
            end_line=2,
            metadata={
                "storage_kind": "localStorage",
                "storage_operation": "getItem",
                "storage_key": "draft",
            },
        ),
        _edge(
            "edge_external",
            "USES_EXTERNAL",
            source_file_id=route.id,
            source_symbol_id=route_handler.id,
            target_symbol_id=None,
            target_path="external:OpenAI",
            start_line=2,
            end_line=2,
            metadata={
                "service": "OpenAI",
                "package": "openai",
                "operation": "responses.create",
            },
            confidence=0.95,
        ),
        _edge(
            "edge_navigation",
            "NAVIGATES_TO",
            source_file_id=form.id,
            source_symbol_id=handler.id,
            target_symbol_id=None,
            target_path="/answer",
            start_line=4,
            end_line=4,
            metadata={
                "navigation_kind": "router.push",
                "destination": "/answer?token=redacted",
            },
        ),
    ]

    catalog = build_feature_flows(_snapshot(), files, symbols, [*edges, *effects])
    detail = build_feature_flow(
        _snapshot(), files, symbols, [*edges, *effects], catalog.flows[0].id
    )

    assert detail is not None
    assert [step.role for step in detail.normal_steps] == [
        "user_trigger",
        "client_handler",
        "storage_read",
        "request",
        "server_handler",
        "external_service",
        "navigation",
    ]
    assert [step.relation_type for step in detail.normal_steps][-3:] == [
        "HANDLED_BY",
        "USES_EXTERNAL",
        "NAVIGATES_TO",
    ]
    assert detail.outcome == "사용자 화면이 /answer(으)로 이동합니다."
    assert detail.involved_areas[-3:] == [
        "서버 라우트",
        "외부 서비스",
        "화면 이동",
    ]
    assert all(step.evidence for step in detail.normal_steps)


def test_requestless_flow_can_end_with_a_verified_state_write() -> None:
    files, symbols, edges = _verified_fixture()
    trigger = next(edge for edge in edges if edge.relation == "TRIGGERS")
    handler = next(symbol for symbol in symbols if symbol.id == "sym_submit")
    state_write = _edge(
        "edge_state_write",
        "WRITES",
        source_symbol_id=handler.id,
        target_symbol_id=None,
        target_path="state:answer",
        start_line=3,
        end_line=3,
        metadata={
            "write_kind": "react_state",
            "state_name": "answer",
            "setter": "setAnswer",
        },
    )

    catalog = build_feature_flows(_snapshot(), files, symbols, [trigger, state_write])
    detail = build_feature_flow(
        _snapshot(), files, symbols, [trigger, state_write], catalog.flows[0].id
    )

    assert detail is not None
    assert [step.role for step in detail.normal_steps] == [
        "user_trigger",
        "client_handler",
        "state_write",
    ]
    assert detail.outcome == "answer 화면 상태가 갱신됩니다."


def test_every_exposed_step_has_valid_snapshot_evidence() -> None:
    files, symbols, edges = _verified_fixture()
    file_by_id = {file.id: file for file in files}
    response = build_feature_flows(_snapshot(), files, symbols, edges)
    detail = build_feature_flow(
        _snapshot(), files, symbols, edges, response.flows[0].id
    )

    assert detail is not None
    for step in detail.normal_steps:
        assert step.evidence
        for evidence in step.evidence:
            file = file_by_id[evidence.file_id]
            assert evidence.path == file.path
            assert 1 <= evidence.start_line <= evidence.end_line <= file.line_count


class _ScalarResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _FeatureFlowDb:
    def __init__(
        self, results: list[list[object]], artifacts: list[object | None] | None = None
    ) -> None:
        self.results = results
        self.artifacts = artifacts or []
        self.calls = 0
        self.scalar_calls = 0
        self.execute_calls = 0
        self.statements: list[object] = []

    def scalar(self, _statement: object) -> object | None:
        value = (
            self.artifacts[self.scalar_calls]
            if self.scalar_calls < len(self.artifacts)
            else None
        )
        self.scalar_calls += 1
        return value

    def scalars(self, statement: object) -> _ScalarResult:
        self.statements.append(statement)
        values = self.results[self.calls]
        self.calls += 1
        return _ScalarResult(values)

    def execute(self, _statement: object) -> None:
        self.execute_calls += 1

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _api_app(db: object) -> FastAPI:
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return app


def test_feature_flow_endpoints_list_ready_snapshot_and_load_detail(monkeypatch) -> None:
    files, symbols, edges = _verified_fixture()
    flow_id = build_feature_flows(_snapshot(), files, symbols, edges).flows[0].id
    db = _FeatureFlowDb([files, symbols, edges, files, symbols, edges])
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _snapshot_id: _snapshot())
    client = TestClient(_api_app(db))

    list_response = client.get("/api/snapshots/snap_flow/feature-flows")
    detail_response = client.get(f"/api/snapshots/snap_flow/feature-flows/{flow_id}")

    assert list_response.status_code == 200
    assert set(list_response.json()) == {
        "repository_name",
        "snapshot_id",
        "commit_sha",
        "analysis_version",
        "flows",
        "limitations",
    }
    assert list_response.json()["flows"][0]["id"] == flow_id
    assert detail_response.status_code == 200
    assert detail_response.json()["normal_steps"][-1]["role"] == "server_handler"
    assert list_response.headers["x-navigation-cache"] == "MISS"
    assert detail_response.headers["x-navigation-cache"] == "MISS"
    assert db.calls == 6
    assert db.execute_calls == 2
    file_query = str(db.statements[0]).casefold()
    symbol_query = str(db.statements[1]).casefold()
    assert "files.content" not in file_query
    assert "files.byte_size" not in file_query
    assert "symbols.signature" not in symbol_query
    assert "symbols.content_hash" not in symbol_query


def test_feature_flow_catalog_cache_skips_all_navigation_context_queries(
    monkeypatch,
) -> None:
    files, symbols, edges = _verified_fixture()
    snapshot = _snapshot()
    catalog = build_feature_flows(snapshot, files, symbols, edges)
    artifact = NavigationArtifact(
        id="navart_catalog",
        snapshot_id=snapshot.id,
        artifact_type="feature_flow_catalog",
        artifact_key="representative",
        artifact_version="feature-flow-v2",
        status="ready",
        payload_json=catalog.model_dump(mode="json"),
        generation_metadata={"commit_sha": snapshot.commit_sha},
    )
    db = _FeatureFlowDb([], [artifact])
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: snapshot)

    response = TestClient(_api_app(db)).get(
        "/api/snapshots/snap_flow/feature-flows"
    )

    assert response.status_code == 200
    assert response.json() == catalog.model_dump(mode="json")
    assert response.headers["x-navigation-cache"] == "HIT"
    assert response.headers["x-navigation-artifact-version"] == "feature-flow-v2"
    assert db.calls == 0
    assert db.execute_calls == 0


def test_feature_flow_detail_returns_404_for_unknown_or_unlisted_flow(monkeypatch) -> None:
    files, symbols, edges = _verified_fixture()
    db = _FeatureFlowDb([files, symbols, edges])
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _snapshot_id: _snapshot())

    response = TestClient(_api_app(db)).get(
        "/api/snapshots/snap_flow/feature-flows/flow_missing"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Feature flow not found"}


def test_feature_flow_api_rejects_snapshot_that_is_not_ready(monkeypatch) -> None:
    db = SimpleNamespace(
        scalars=lambda _statement: (_ for _ in ()).throw(
            AssertionError("must not query navigation context")
        )
    )
    monkeypatch.setattr(
        repositories,
        "load_snapshot",
        lambda _db, _snapshot_id: _snapshot(status="analyzing"),
    )

    response = TestClient(_api_app(db)).get("/api/snapshots/snap_flow/feature-flows")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Snapshot is analyzing; analysis must be ready",
    }
