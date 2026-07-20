from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import repositories
from app.core.db import get_db
from app.models import FileRecord, Repository, RepositorySnapshot, Symbol, SymbolEdge
from app.navigation.code_focus import build_code_explanation
from app.schemas import CodeSelection, FeatureFlowEvidence, FeatureFlowStep

SOURCE = """export function AskButton() {
  const [answer, setAnswer] = useState('');
  async function submit() {
    const draft = localStorage.getItem('draft');
    await fetch('/api/ask', { method: 'POST' });
    setAnswer(draft ?? '');
  }
  return <button onClick={submit}>{answer}</button>;
}
"""


def _snapshot() -> RepositorySnapshot:
    repository = Repository(
        id="repo_focus",
        owner="example",
        name="focus-demo",
        url="https://github.com/example/focus-demo",
    )
    snapshot = RepositorySnapshot(
        id="snap_focus",
        repository_id=repository.id,
        commit_sha="commit-focus",
        status="ready",
        parser_version="semantic-ts-v2",
    )
    snapshot.repository = repository
    snapshot.jobs = []
    return snapshot


def _file() -> FileRecord:
    return FileRecord(
        id="file_focus",
        snapshot_id="snap_focus",
        path="src/components/AskButton.tsx",
        language="tsx",
        content=SOURCE,
        content_hash="sha256:focus",
        byte_size=len(SOURCE.encode()),
        line_count=len(SOURCE.splitlines()),
        is_documentation=False,
    )


def _symbol() -> Symbol:
    return Symbol(
        id="sym_submit",
        snapshot_id="snap_focus",
        file_id="file_focus",
        qualified_name="src/components/AskButton.tsx::AskButton.submit",
        display_name="submit",
        kind="function",
        signature="async function submit()",
        start_line=3,
        end_line=7,
        content_hash="sha256:submit",
    )


def _edge(
    edge_id: str,
    relation: str,
    target: str,
    line: int,
    metadata: dict | None = None,
) -> SymbolEdge:
    return SymbolEdge(
        id=edge_id,
        snapshot_id="snap_focus",
        source_file_id="file_focus",
        source_symbol_id="sym_submit",
        target_path=target,
        relation=relation,
        confidence=1.0,
        analysis_method="semantic-ts-v2",
        source_start_line=line,
        source_end_line=line,
        metadata_json=metadata or {},
    )


def _edges() -> list[SymbolEdge]:
    return [
        _edge(
            "edge_read",
            "READS",
            "storage:localStorage:draft",
            4,
            {"storage_kind": "localStorage", "storage_key": "draft"},
        ),
        _edge(
            "edge_request",
            "REQUESTS",
            "/api/ask",
            5,
            {"http_method": "POST", "request_path": "/api/ask", "awaited": True},
        ),
        _edge(
            "edge_write",
            "WRITES",
            "state:answer",
            6,
            {"write_kind": "react_state", "state_name": "answer"},
        ),
    ]


def test_builds_minimum_sufficient_explanation_from_symbol_and_edges() -> None:
    explanation = build_code_explanation(
        snapshot=_snapshot(),
        file=_file(),
        selection=CodeSelection(file_id="file_focus", start_line=3, end_line=7),
        depth="minimum",
        symbols=[_symbol()],
        edges=_edges(),
    )

    assert explanation.analysis_version == "minimum-sufficient-v1"
    assert explanation.purpose == "submit 함수 안에서 맡은 동작을 구현합니다."
    assert explanation.executes_when == "상위 핸들러가 서버 요청 코드를 실행할 때 동작합니다."
    assert explanation.input.startswith("POST /api/ask")
    assert "저장된 값을 읽습니다" in explanation.output_or_side_effect
    assert "상태 또는 저장값을 바꿉니다" in explanation.output_or_side_effect
    assert explanation.project_role == (
        "사용자에게 보이는 화면과 상호작용을 구성하는 인터페이스 영역"
    )
    assert set(explanation.required_concepts) >= {
        "비동기 실행과 await",
        "HTTP 요청",
        "React 화면 상태",
        "브라우저 저장소",
    }
    assert [step.relation_type for step in explanation.related_steps] == [
        "READS",
        "REQUESTS",
        "WRITES",
    ]
    assert explanation.confidence == "inferred"
    assert explanation.evidence[0].start_line == 3
    assert explanation.syntax_segments == []


def test_syntax_depth_reuses_verified_statement_segmentation_without_source_text() -> None:
    explanation = build_code_explanation(
        snapshot=_snapshot(),
        file=_file(),
        selection=CodeSelection(file_id="file_focus", start_line=3, end_line=7),
        depth="syntax",
        symbols=[_symbol()],
        edges=_edges(),
    )

    assert explanation.syntax_segments
    assert any(
        segment.node_type == "function_declaration"
        for segment in explanation.syntax_segments
    )
    assert all(
        3 <= segment.start_line <= segment.end_line <= 7
        for segment in explanation.syntax_segments
    )
    assert "localStorage.getItem('draft')" not in explanation.model_dump_json()


def test_verified_feature_step_overrides_generic_copy_only_for_matching_context() -> None:
    flow_step = FeatureFlowStep(
        id="step-request",
        ordinal=3,
        title="POST /api/ask 전송",
        role="request",
        executes_when="submit 핸들러가 요청 코드를 실행할 때",
        input="POST /api/ask",
        output_or_side_effect="서버 라우트로 전달",
        relation_type="REQUESTS",
        confidence="verified",
        evidence=[
            FeatureFlowEvidence(
                file_id="file_focus",
                path="src/components/AskButton.tsx",
                start_line=5,
                end_line=5,
                reason="request evidence",
            )
        ],
    )
    explanation = build_code_explanation(
        snapshot=_snapshot(),
        file=_file(),
        selection=CodeSelection(file_id="file_focus", start_line=5, end_line=5),
        depth="minimum",
        symbols=[_symbol()],
        edges=_edges(),
        flow_step=flow_step,
    )

    assert explanation.purpose == flow_step.title
    assert explanation.project_role == "화면과 서버를 잇는 네트워크 경계"
    assert explanation.confidence == "verified"
    assert not any("직접 연결되지 않아" in item for item in explanation.limitations)


class _ScalarResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _CodeFocusDb:
    def __init__(self) -> None:
        self.scalar_values = [None, _file()]
        self.scalar_calls = 0
        self.scalars_values = [[_symbol()], _edges()]
        self.scalars_calls = 0
        self.execute_calls = 0

    def scalar(self, _statement: object) -> object | None:
        value = self.scalar_values[self.scalar_calls]
        self.scalar_calls += 1
        return value

    def scalars(self, _statement: object) -> _ScalarResult:
        value = self.scalars_values[self.scalars_calls]
        self.scalars_calls += 1
        return _ScalarResult(value)

    def execute(self, _statement: object) -> None:
        self.execute_calls += 1

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def test_code_focus_endpoint_validates_selection_and_persists_versioned_result(
    monkeypatch,
) -> None:
    db = _CodeFocusDb()
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: _snapshot())
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).post(
        "/api/snapshots/snap_focus/code-explanations",
        json={
            "selection": {"file_id": "file_focus", "start_line": 3, "end_line": 7},
            "depth": "minimum",
        },
    )

    assert response.status_code == 200
    assert response.json()["analysis_version"] == "minimum-sufficient-v1"
    assert response.headers["x-navigation-cache"] == "MISS"
    assert response.headers["x-navigation-cache-write"] == "STORED"
    assert db.scalars_calls == 2
    assert db.execute_calls == 1


def test_code_focus_endpoint_rejects_oversized_selection_before_file_queries(
    monkeypatch,
) -> None:
    db = SimpleNamespace()
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: _snapshot())
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).post(
        "/api/snapshots/snap_focus/code-explanations",
        json={
            "selection": {"file_id": "file_focus", "start_line": 1, "end_line": 81},
            "depth": "minimum",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Code Focus supports at most 80 selected lines"}
