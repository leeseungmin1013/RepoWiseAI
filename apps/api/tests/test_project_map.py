from __future__ import annotations

import json
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
    SymbolEdge,
)
from app.navigation.project_map import build_project_map


def _file(
    file_id: str,
    path: str,
    content: str,
    language: str,
    *,
    documentation: bool = False,
) -> FileRecord:
    return FileRecord(
        id=file_id,
        snapshot_id="snap_map",
        path=path,
        language=language,
        content=content,
        content_hash=f"sha256:{file_id}",
        byte_size=len(content.encode()),
        line_count=max(1, len(content.splitlines())),
        is_documentation=documentation,
    )


def _snapshot(status: str = "ready") -> RepositorySnapshot:
    repository = Repository(
        id="repo_map",
        owner="example",
        name="map-demo",
        url="https://github.com/example/map-demo",
    )
    snapshot = RepositorySnapshot(
        id="snap_map",
        repository_id=repository.id,
        commit_sha="abc123",
        status=status,
        file_count=4,
    )
    snapshot.repository = repository
    snapshot.jobs = []
    return snapshot


def _fixture() -> tuple[list[FileRecord], list[SymbolEdge]]:
    readme = _file(
        "file_readme",
        "README.md",
        """# Map Demo

사용자가 질문을 보내고 저장된 답변을 다시 확인하는 AI 도우미입니다.

## Features

- AI에게 질문 보내기
- 이전 답변 다시 확인하기

## Setup

```env
OPENAI_API_KEY=sk-test-secret
DATABASE_URL=postgresql://user:secret@host/database
```
""",
        "markdown",
        documentation=True,
    )
    package_content = json.dumps(
        {
            "name": "map-demo",
            "dependencies": {
                "next": "16.0.0",
                "react": "19.0.0",
                "openai": "6.0.0",
                "@prisma/client": "6.0.0",
            },
            "devDependencies": {"typescript": "5.9.0"},
        },
        indent=2,
    )
    package = _file("file_package", "package.json", package_content, "json")
    page = _file(
        "file_page",
        "src/app/page.tsx",
        """export default function Home() {
  const title = process.env.NEXT_PUBLIC_APP_NAME;
  return <main>{title}</main>;
}
""",
        "tsx",
    )
    route = _file(
        "file_route",
        "src/app/api/ask/route.ts",
        """import OpenAI from "openai";

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
export async function POST() { return Response.json({ ok: true }); }
""",
        "typescript",
    )
    edge = SymbolEdge(
        id="edge_openai",
        snapshot_id="snap_map",
        source_file_id=route.id,
        target_path="openai",
        relation="IMPORTS",
        confidence=1.0,
        source_start_line=1,
        source_end_line=1,
    )
    return [route, package, page, readme], [edge]


def test_builds_deterministic_evidence_grounded_project_map_without_secret_values() -> None:
    files, edges = _fixture()

    first = build_project_map(_snapshot(), files, edges)
    repeated = build_project_map(_snapshot(), list(reversed(files)), list(reversed(edges)))

    assert first.model_dump() == repeated.model_dump()
    assert first.repository_name == "example/map-demo"
    assert first.summary == "사용자가 질문을 보내고 저장된 답변을 다시 확인하는 AI 도우미입니다."
    assert first.summary_confidence == "inferred"
    assert {item.name for item in first.tech_stack} >= {
        "TypeScript",
        "Next.js",
        "React",
        "OpenAI SDK",
    }
    assert [item.name for item in first.capabilities] == [
        "AI에게 질문 보내기",
        "이전 답변 다시 확인하기",
        "홈 화면 사용",
        "ask 요청 처리",
    ]
    assert {item.id for item in first.system_areas} >= {"interface", "api", "configuration"}

    openai = next(item for item in first.external_services if item.name == "OpenAI")
    assert openai.confidence == "verified"
    assert any(evidence.path == "src/app/api/ask/route.ts" for evidence in openai.evidence)
    assert {item.name for item in first.environment_variables} == {
        "DATABASE_URL",
        "NEXT_PUBLIC_APP_NAME",
        "OPENAI_API_KEY",
    }
    assert [item.path for item in first.read_first] == [
        "README.md",
        "package.json",
        "src/app/page.tsx",
        "src/app/api/ask/route.ts",
    ]

    evidence_backed_items = [
        *first.tech_stack,
        *first.capabilities,
        *first.system_areas,
        *first.external_services,
        *first.environment_variables,
    ]
    assert all(item.evidence for item in evidence_backed_items)
    assert all(
        evidence.start_line >= 1 and evidence.end_line >= evidence.start_line
        for item in evidence_backed_items
        for evidence in item.evidence
    )
    serialized = first.model_dump_json()
    assert "sk-test-secret" not in serialized
    assert "postgresql://user:secret" not in serialized


class _ScalarResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _ProjectMapDb:
    def __init__(
        self,
        files: list[FileRecord],
        edges: list[SymbolEdge],
        artifact: object | None = None,
    ) -> None:
        self.results = [files, edges]
        self.calls = 0
        self.artifact = artifact
        self.execute_calls = 0

    def scalar(self, _statement: object) -> object | None:
        return self.artifact

    def scalars(self, _statement: object) -> _ScalarResult:
        values = self.results[self.calls]
        self.calls += 1
        return _ScalarResult(values)

    def execute(self, _statement: object) -> None:
        self.execute_calls += 1

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def test_project_map_api_exposes_contract_for_ready_snapshot(monkeypatch) -> None:
    files, edges = _fixture()
    snapshot = _snapshot()
    db = _ProjectMapDb(files, edges)
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _snapshot_id: snapshot)
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).get("/api/snapshots/snap_map/project-map")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "repository_name",
        "snapshot_id",
        "commit_sha",
        "summary",
        "summary_confidence",
        "tech_stack",
        "capabilities",
        "system_areas",
        "external_services",
        "environment_variables",
        "read_first",
        "limitations",
    }
    assert payload["snapshot_id"] == "snap_map"
    assert payload["external_services"][1]["name"] == "OpenAI"
    assert response.headers["x-navigation-cache"] == "MISS"
    assert response.headers["x-navigation-cache-write"] == "STORED"
    assert db.calls == 2
    assert db.execute_calls == 1


def test_project_map_api_returns_a_valid_versioned_cache_without_context_queries(
    monkeypatch,
) -> None:
    files, edges = _fixture()
    snapshot = _snapshot()
    project_map = build_project_map(snapshot, files, edges)
    artifact = NavigationArtifact(
        id="navart_map",
        snapshot_id=snapshot.id,
        artifact_type="project_map",
        artifact_key="default",
        artifact_version="project-map-v2",
        status="ready",
        payload_json=project_map.model_dump(mode="json"),
        generation_metadata={"commit_sha": snapshot.commit_sha},
    )
    db = _ProjectMapDb(files, edges, artifact)
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: snapshot)
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).get("/api/snapshots/snap_map/project-map")

    assert response.status_code == 200
    assert response.json() == project_map.model_dump(mode="json")
    assert response.headers["x-navigation-cache"] == "HIT"
    assert response.headers["x-navigation-artifact-version"] == "project-map-v2"
    assert db.calls == 0
    assert db.execute_calls == 0


def test_project_map_api_rejects_snapshot_that_is_not_ready(monkeypatch) -> None:
    snapshot = _snapshot(status="analyzing")
    db = SimpleNamespace(
        scalars=lambda _statement: (_ for _ in ()).throw(AssertionError("must not query files"))
    )
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _snapshot_id: snapshot)
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).get("/api/snapshots/snap_map/project-map")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Snapshot is analyzing; analysis must be ready",
    }
