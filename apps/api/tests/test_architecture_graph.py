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
from app.navigation.architecture_graph import build_architecture_graph
from app.navigation.architecture_validation import validate_architecture_graph
from app.schemas import (
    FeatureFlowDetail,
    FeatureFlowEvidence,
    FeatureFlowStep,
    ProjectMapCapability,
    ProjectMapEvidence,
    ProjectMapResponse,
    ProjectMapSystemArea,
)


def _file(file_id: str, path: str) -> FileRecord:
    return FileRecord(
        id=file_id,
        snapshot_id="snap_arch",
        path=path,
        language="typescript",
        content="\n".join(["export const value = 1;"] * 20),
        content_hash=f"hash-{file_id}",
        byte_size=100,
        line_count=20,
        is_documentation=False,
    )


def _evidence(file: FileRecord, reason: str) -> ProjectMapEvidence:
    return ProjectMapEvidence(
        file_id=file.id,
        path=file.path,
        start_line=1,
        end_line=3,
        reason=reason,
    )


def _flow_evidence(file: FileRecord, reason: str) -> FeatureFlowEvidence:
    return FeatureFlowEvidence(**_evidence(file, reason).model_dump())


def graph_inputs():
    repository = Repository(
        id="repo_arch",
        owner="example",
        name="architecture-demo",
        url="https://github.com/example/architecture-demo",
    )
    snapshot = RepositorySnapshot(
        id="snap_arch",
        repository_id=repository.id,
        commit_sha="abc123",
        status="ready",
        parser_version="semantic-ts-v2",
    )
    snapshot.repository = repository
    client = _file("file_client", "src/components/SubmitButton.tsx")
    server = _file("file_server", "src/app/api/submit/route.ts")
    data = _file("file_data", "src/models/submission.ts")
    symbols = [
        Symbol(
            id="sym_client",
            snapshot_id=snapshot.id,
            file_id=client.id,
            qualified_name="SubmitButton.handleSubmit",
            display_name="handleSubmit",
            kind="function",
            start_line=2,
            end_line=8,
            content_hash="sym-client",
        ),
        Symbol(
            id="sym_server",
            snapshot_id=snapshot.id,
            file_id=server.id,
            qualified_name="POST",
            display_name="POST",
            kind="function",
            start_line=2,
            end_line=10,
            content_hash="sym-server",
        ),
        Symbol(
            id="sym_data",
            snapshot_id=snapshot.id,
            file_id=data.id,
            qualified_name="saveSubmission",
            display_name="saveSubmission",
            kind="function",
            start_line=2,
            end_line=7,
            content_hash="sym-data",
        ),
    ]
    edges = [
        SymbolEdge(
            id="edge_request",
            snapshot_id=snapshot.id,
            source_file_id=client.id,
            source_symbol_id="sym_client",
            target_symbol_id="sym_server",
            target_path=server.path,
            relation="REQUESTS",
            confidence=0.98,
            source_start_line=4,
            source_end_line=5,
        ),
        SymbolEdge(
            id="edge_write",
            snapshot_id=snapshot.id,
            source_file_id=server.id,
            source_symbol_id="sym_server",
            target_symbol_id="sym_data",
            target_path=data.path,
            relation="WRITES",
            confidence=0.92,
            source_start_line=6,
            source_end_line=7,
        ),
    ]
    project_map = ProjectMapResponse(
        repository_name="example/architecture-demo",
        snapshot_id=snapshot.id,
        commit_sha="abc123",
        summary="사용자 제출을 받아 저장하는 예제입니다.",
        summary_confidence="verified",
        tech_stack=[],
        capabilities=[
            ProjectMapCapability(
                id="submit",
                name="제출",
                description="사용자 입력을 서버로 전송해 저장합니다.",
                confidence="verified",
                evidence=[_evidence(client, "제출 진입점")],
            )
        ],
        system_areas=[
            ProjectMapSystemArea(
                id="server",
                name="서버",
                description="제출 요청을 검증하고 저장합니다.",
                confidence="verified",
                evidence=[_evidence(server, "API handler")],
            )
        ],
        external_services=[],
        environment_variables=[],
        read_first=[],
        limitations=[],
    )
    flow = FeatureFlowDetail(
        id="submit-flow",
        title="제출 저장",
        user_goal="입력을 저장합니다.",
        trigger="제출 버튼",
        outcome="저장 완료",
        normal_steps=[
            FeatureFlowStep(
                id="step-client",
                ordinal=1,
                title="제출 요청",
                role="client_handler",
                executes_when="버튼 클릭",
                input="폼 값",
                output_or_side_effect="POST 요청",
                relation_type="REQUESTS",
                confidence="verified",
                evidence=[_flow_evidence(client, "client handler")],
            ),
            FeatureFlowStep(
                id="step-server",
                ordinal=2,
                title="요청 처리",
                role="server_handler",
                executes_when="POST 요청 수신",
                input="요청 본문",
                output_or_side_effect="저장 호출",
                relation_type="HANDLED_BY",
                confidence="verified",
                evidence=[_flow_evidence(server, "server handler")],
            ),
            FeatureFlowStep(
                id="step-data",
                ordinal=3,
                title="저장",
                role="effect",
                executes_when="검증 완료",
                input="submission",
                output_or_side_effect="데이터 저장",
                relation_type="WRITES",
                confidence="verified",
                evidence=[_flow_evidence(data, "data write")],
            ),
        ],
        failure_steps=[],
        involved_areas=["client", "server", "data"],
        confidence="verified",
        limitations=[],
    )
    return snapshot, [client, server, data], symbols, edges, project_map, [flow]


def test_builds_bounded_evidence_backed_architecture_graph() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()

    graph = build_architecture_graph(snapshot, files, symbols, edges, project_map, flows)
    validation = validate_architecture_graph(
        graph,
        files=files,
        project_map=project_map,
        feature_flows=flows,
    )

    assert validation.valid, validation.issues
    assert validation.flow_mapping_coverage == {"submit-flow": 1.0}
    assert len(graph.nodes) == 3
    assert {group.layer for group in graph.groups} == {"client", "server", "data"}
    assert {edge.relation for edge in graph.edges} == {"REQUESTS", "WRITES"}
    assert all(node.evidence for node in graph.nodes)
    assert all("submit-flow" in node.feature_flow_ids for node in graph.nodes)


def test_architecture_graph_is_stable_for_reordered_inputs() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()

    first = build_architecture_graph(snapshot, files, symbols, edges, project_map, flows)
    second = build_architecture_graph(
        snapshot,
        list(reversed(files)),
        list(reversed(symbols)),
        list(reversed(edges)),
        project_map,
        flows,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


class _CacheDb:
    def __init__(self, artifact: NavigationArtifact):
        self.artifact = artifact

    def scalar(self, _statement: object):
        return self.artifact

    def rollback(self) -> None:
        return None


def test_architecture_graph_api_returns_a_versioned_cache(monkeypatch) -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(snapshot, files, symbols, edges, project_map, flows)
    artifact = NavigationArtifact(
        id="navart_arch",
        snapshot_id=snapshot.id,
        artifact_type="architecture_graph",
        artifact_key="overview",
        artifact_version="architecture-graph-v2",
        status="ready",
        payload_json=graph.model_dump(mode="json"),
        generation_metadata={"commit_sha": snapshot.commit_sha},
    )
    db = _CacheDb(artifact)
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: snapshot)
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).get("/api/snapshots/snap_arch/architecture-graph")

    assert response.status_code == 200
    assert response.json() == graph.model_dump(mode="json")
    assert response.headers["x-navigation-cache"] == "HIT"
    assert response.headers["x-navigation-artifact-version"] == "architecture-graph-v2"


def test_architecture_graph_api_requires_semantic_v2(monkeypatch) -> None:
    snapshot, *_ = graph_inputs()
    snapshot.parser_version = "tree-sitter-v1"
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: snapshot)
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: object()

    response = TestClient(app).get("/api/snapshots/snap_arch/architecture-graph")

    assert response.status_code == 409
    assert "semantic-ts-v2" in response.json()["detail"]


def test_architecture_graph_export_diff_and_disabled_label_endpoints(monkeypatch) -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(
        snapshot, files, symbols, edges, project_map, flows
    )
    artifact = NavigationArtifact(
        id="navart_arch_exports",
        snapshot_id=snapshot.id,
        artifact_type="architecture_graph",
        artifact_key="overview",
        artifact_version="architecture-graph-v2",
        status="ready",
        payload_json=graph.model_dump(mode="json"),
        generation_metadata={"commit_sha": snapshot.commit_sha},
    )
    db = _CacheDb(artifact)
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: snapshot)
    monkeypatch.setattr(
        repositories.settings, "navigation_llm_labels_enabled", False
    )
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    mermaid = client.get("/api/snapshots/snap_arch/architecture-graph/mermaid")
    diff = client.get(
        "/api/snapshots/snap_arch/architecture-graph/diff"
        "?base_snapshot_id=snap_arch"
    )
    labels = client.post(
        "/api/snapshots/snap_arch/architecture-graph/enhance-labels"
    )

    assert mermaid.status_code == 200
    assert mermaid.text.startswith("flowchart LR")
    assert "attachment;" in mermaid.headers["content-disposition"]
    assert diff.status_code == 200
    assert diff.json()["summary"] == {
        "nodes_added": 0,
        "nodes_removed": 0,
        "nodes_changed": 0,
        "edges_added": 0,
        "edges_removed": 0,
    }
    assert labels.status_code == 404
