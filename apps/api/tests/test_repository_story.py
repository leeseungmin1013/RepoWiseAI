from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_architecture_graph import _CacheDb, graph_inputs

from app.api import repositories
from app.core.db import get_db
from app.models import NavigationArtifact
from app.navigation.architecture_graph import build_architecture_graph
from app.navigation.repository_story import build_repository_story
from app.navigation.repository_story_validation import validate_repository_story
from app.schemas import FeatureFlowSummary


def _feature_summary() -> FeatureFlowSummary:
    _, files, _, _, _, _ = graph_inputs()
    return FeatureFlowSummary(
        id="submit-flow",
        title="제출 저장",
        user_goal="입력을 저장합니다.",
        trigger="제출 버튼",
        outcome="저장 완료",
        step_count=3,
        involved_areas=["client", "server", "data"],
        confidence="verified",
        evidence_coverage=1.0,
        entry_evidence={
            "file_id": files[0].id,
            "path": files[0].path,
            "start_line": 1,
            "end_line": 3,
            "reason": "제출 진입점",
        },
    )


def test_builds_plain_language_role_story_with_evidence() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(
        snapshot,
        files,
        symbols,
        edges,
        project_map,
        flows,
    )

    story = build_repository_story(
        snapshot,
        project_map,
        graph,
        [_feature_summary()],
    )
    validation = validate_repository_story(story, files=files)

    assert validation.valid, validation.issues
    assert validation.evidence_validity == 1.0
    assert validation.feature_mapping_coverage == 1.0
    assert validation.generic_responsibility_ratio == 0.0
    assert [role.id for role in story.roles] == [
        "role_experience",
        "role_application",
        "role_persistence",
    ]
    assert all(role.why_it_exists for role in story.roles)
    assert all(role.contribution_to_goal for role in story.roles)
    assert all(role.member_file_ids for role in story.roles)
    assert {connection.label for connection in story.connections} == {
        "요청을 전달합니다",
        "결과를 저장합니다",
    }


def test_repository_story_is_stable_for_reordered_graph_inputs() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    first_graph = build_architecture_graph(
        snapshot,
        files,
        symbols,
        edges,
        project_map,
        flows,
    )
    second_graph = build_architecture_graph(
        snapshot,
        list(reversed(files)),
        list(reversed(symbols)),
        list(reversed(edges)),
        project_map,
        flows,
    )

    first = build_repository_story(
        snapshot,
        project_map,
        first_graph,
        [_feature_summary()],
    )
    second = build_repository_story(
        snapshot,
        project_map,
        second_graph,
        [_feature_summary()],
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_repository_story_api_returns_versioned_cache(monkeypatch) -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(
        snapshot,
        files,
        symbols,
        edges,
        project_map,
        flows,
    )
    story = build_repository_story(
        snapshot,
        project_map,
        graph,
        [_feature_summary()],
    )
    artifact = NavigationArtifact(
        id="navart_story",
        snapshot_id=snapshot.id,
        artifact_type="repository_story",
        artifact_key="overview",
        artifact_version="repository-story-v1",
        status="ready",
        payload_json=story.model_dump(mode="json"),
        generation_metadata={"commit_sha": snapshot.commit_sha},
    )
    db = _CacheDb(artifact)
    monkeypatch.setattr(repositories, "load_snapshot", lambda _db, _id: snapshot)
    app = FastAPI()
    app.include_router(repositories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).get("/api/snapshots/snap_arch/repository-story")

    assert response.status_code == 200
    assert response.json() == story.model_dump(mode="json")
    assert response.headers["x-navigation-cache"] == "HIT"
    assert response.headers["x-navigation-artifact-version"] == "repository-story-v1"
