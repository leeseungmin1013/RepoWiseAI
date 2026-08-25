import json
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, load_only, selectinload

from app.ai.gateway import extract_usage
from app.analysis.tree import build_file_tree
from app.core.auth import AuthDep
from app.core.config import get_settings
from app.core.db import get_db
from app.models import (
    FileRecord,
    OrganizationRepository,
    RepositorySnapshot,
    Symbol,
    SymbolEdge,
)
from app.navigation.architecture_diff import (
    architecture_graph_to_mermaid,
    diff_architecture_graphs,
)
from app.navigation.architecture_graph import IMPORTANT_RELATIONS, build_architecture_graph
from app.navigation.architecture_labels import enhance_architecture_graph_labels
from app.navigation.architecture_validation import validate_architecture_graph
from app.navigation.artifacts import (
    ArtifactWrite,
    load_navigation_artifact,
    write_navigation_artifacts,
)
from app.navigation.code_focus import SEMANTIC_FOCUS_RELATIONS, build_code_explanation
from app.navigation.feature_flow import build_feature_flow, build_feature_flows
from app.navigation.project_map import build_project_map
from app.navigation.repository_story import build_repository_story
from app.navigation.repository_story_validation import validate_repository_story
from app.navigation.versions import (
    ARCHITECTURE_GRAPH_VERSION,
    ARCHITECTURE_LABEL_VERSION,
    CODE_EXPLANATION_VERSION,
    FEATURE_FLOW_VERSION,
    PROJECT_MAP_VERSION,
    REPOSITORY_STORY_VERSION,
)
from app.queue import enqueue_repository_analysis
from app.schemas import (
    AnalysisJobResponse,
    ArchitectureGraphDiffResponse,
    ArchitectureGraphResponse,
    CodeExplanationCreate,
    CodeExplanationResponse,
    EntryPoint,
    FeatureFlowDetail,
    FeatureFlowListResponse,
    FileResponse,
    GraphEdge,
    GraphNode,
    GraphResponse,
    ProjectMapResponse,
    RepositoryCreate,
    RepositoryCreateResponse,
    RepositoryStoryResponse,
    RepositorySummary,
    ReuseSummary,
    SnapshotResponse,
    StartHereResponse,
    SymbolResponse,
    TreeNode,
)
from app.services.github import GitHubError, parse_github_url
from app.services.snapshot_resolver import resolve_snapshot_request
from app.services.usage import UsageContext, UsageService

router = APIRouter(tags=["repositories"])
settings = get_settings()
SessionDep = Annotated[Session, Depends(get_db)]
SnapshotLimit = Annotated[int, Query(ge=1, le=50)]
SymbolLimit = Annotated[int, Query(ge=1, le=500)]


def to_snapshot_response(snapshot: RepositorySnapshot) -> SnapshotResponse:
    latest_job = max(snapshot.jobs, key=lambda item: item.created_at) if snapshot.jobs else None
    response = SnapshotResponse.model_validate(snapshot)
    return response.model_copy(
        update={"job": AnalysisJobResponse.model_validate(latest_job) if latest_job else None}
    )


def load_snapshot(db: Session, snapshot_id: str) -> RepositorySnapshot:
    snapshot = db.scalar(
        select(RepositorySnapshot)
        .where(RepositorySnapshot.id == snapshot_id)
        .options(selectinload(RepositorySnapshot.jobs), selectinload(RepositorySnapshot.repository))
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


def require_ready(snapshot: RepositorySnapshot) -> None:
    if snapshot.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Snapshot is {snapshot.status}; analysis must be ready",
        )


@router.post(
    "/repositories",
    response_model=RepositoryCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_repository(
    payload: RepositoryCreate,
    db: SessionDep,
    auth: AuthDep,
    http_response: Response,
):
    try:
        owner, name, canonical_url = parse_github_url(str(payload.url))
        resolution = resolve_snapshot_request(
            db,
            settings=settings,
            context=auth,
            owner=owner,
            name=name,
            canonical_url=canonical_url,
            requested_branch=payload.branch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    analysis_job = resolution.job
    reservation = None
    if resolution.should_enqueue and auth.authenticated and analysis_job is not None:
        feature = (
            "repository_analysis_incremental"
            if resolution.mode == "incremental"
            else "repository_analysis_full"
        )
        reservation = UsageService(settings).reserve(
            db,
            context=UsageContext(
                organization_id=auth.organization_id,
                user_id=auth.user_id,
                feature=feature,
                request_id=analysis_job.id,
                idempotency_key=f"{analysis_job.id}:{feature}",
            ),
            estimated_cost_micro_usd=settings.repository_analysis_reservation_micro_usd,
        )
        if reservation is not None:
            analysis_job.cost_reservation_id = reservation.id
            db.commit()
    if resolution.should_enqueue:
        if analysis_job is None:
            raise HTTPException(status_code=500, detail="Analysis job was not created")
        try:
            enqueue_repository_analysis(resolution.snapshot.id)
        except Exception as exc:
            if reservation is not None:
                UsageService(settings).release(db, reservation.id)
            resolution.snapshot.status = "failed"
            resolution.snapshot.error_message = "Analysis queue is unavailable"
            analysis_job.status = "failed"
            analysis_job.error_code = "queue_unavailable"
            analysis_job.error_detail = str(exc)
            db.commit()
            raise HTTPException(status_code=503, detail="Analysis queue is unavailable") from exc

    resolution.snapshot.jobs = [analysis_job] if analysis_job else []
    http_response.headers["X-Analysis-Reuse"] = resolution.mode
    return RepositoryCreateResponse(
        repository=RepositorySummary.model_validate(resolution.repository),
        snapshot=to_snapshot_response(resolution.snapshot),
        reuse=ReuseSummary(
            mode=resolution.mode,
            cache_hit=resolution.cache_hit,
            base_snapshot_id=resolution.base_snapshot_id,
            reason=resolution.reason,
        ),
    )


@router.get("/snapshots", response_model=list[SnapshotResponse])
def list_snapshots(db: SessionDep, auth: AuthDep, limit: SnapshotLimit = 10):
    statement = select(RepositorySnapshot).options(selectinload(RepositorySnapshot.jobs))
    if auth.authenticated:
        statement = statement.join(
            OrganizationRepository,
            OrganizationRepository.repository_id == RepositorySnapshot.repository_id,
        ).where(OrganizationRepository.organization_id == auth.organization_id)
    snapshots = db.scalars(
        statement.order_by(RepositorySnapshot.created_at.desc()).limit(limit)
    ).all()
    return [to_snapshot_response(snapshot) for snapshot in snapshots]


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotResponse)
def get_snapshot(snapshot_id: str, db: SessionDep):
    return to_snapshot_response(load_snapshot(db, snapshot_id))


@router.get("/snapshots/{snapshot_id}/tree", response_model=list[TreeNode])
def get_tree(snapshot_id: str, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    files = db.scalars(
        select(FileRecord).where(FileRecord.snapshot_id == snapshot_id).order_by(FileRecord.path)
    ).all()
    return build_file_tree(files)


@router.get("/snapshots/{snapshot_id}/files/{file_id}", response_model=FileResponse)
def get_file(snapshot_id: str, file_id: str, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    file = db.scalar(
        select(FileRecord).where(FileRecord.id == file_id, FileRecord.snapshot_id == snapshot_id)
    )
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return file


@router.get("/snapshots/{snapshot_id}/symbols", response_model=list[SymbolResponse])
def get_symbols(
    snapshot_id: str,
    db: SessionDep,
    file_id: str | None = None,
    query: str | None = None,
    limit: SymbolLimit = 200,
):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    statement = select(Symbol).where(Symbol.snapshot_id == snapshot_id)
    if file_id:
        statement = statement.where(Symbol.file_id == file_id)
    if query:
        statement = statement.where(Symbol.display_name.ilike(f"%{query}%"))
    return db.scalars(statement.order_by(Symbol.file_id, Symbol.start_line).limit(limit)).all()


@router.get("/snapshots/{snapshot_id}/graph", response_model=GraphResponse)
def get_graph(snapshot_id: str, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    files = db.scalars(select(FileRecord).where(FileRecord.snapshot_id == snapshot_id)).all()
    file_by_id = {file.id: file for file in files}
    file_by_path = {file.path: file for file in files}
    edges = db.scalars(
        select(SymbolEdge)
        .where(SymbolEdge.snapshot_id == snapshot_id, SymbolEdge.relation == "IMPORTS")
        .limit(300)
    ).all()

    graph_nodes: dict[str, GraphNode] = {}
    graph_edges: list[GraphEdge] = []
    for edge in edges:
        source_file = file_by_id.get(edge.source_file_id)
        if source_file is None:
            continue
        source_id = f"file:{source_file.id}"
        graph_nodes[source_id] = GraphNode(
            id=source_id,
            label=source_file.path.rsplit("/", 1)[-1],
            kind="file",
            file_id=source_file.id,
            path=source_file.path,
        )

        target_file = file_by_path.get(edge.target_path or "")
        if target_file:
            target_id = f"file:{target_file.id}"
            graph_nodes[target_id] = GraphNode(
                id=target_id,
                label=target_file.path.rsplit("/", 1)[-1],
                kind="file",
                file_id=target_file.id,
                path=target_file.path,
            )
        else:
            target_label = edge.target_path or "unknown"
            target_id = f"external:{target_label}"
            graph_nodes[target_id] = GraphNode(
                id=target_id, label=target_label, kind="external", path=target_label
            )
        graph_edges.append(
            GraphEdge(
                id=edge.id,
                source=source_id,
                target=target_id,
                relation=edge.relation,
                confidence=edge.confidence,
            )
        )

    return GraphResponse(nodes=list(graph_nodes.values()), edges=graph_edges)


@router.get(
    "/snapshots/{snapshot_id}/architecture-graph",
    response_model=ArchitectureGraphResponse,
)
def get_architecture_graph(
    snapshot_id: str,
    response: Response,
    db: SessionDep,
    feature_flow_id: str | None = None,
):
    if not settings.navigation_architecture_graph_enabled:
        raise HTTPException(status_code=404, detail="Architecture graph is disabled")
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    if snapshot.parser_version != "semantic-ts-v2":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Architecture graph requires a semantic-ts-v2 repository analysis",
        )
    commit_sha = snapshot.commit_sha or ""
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot_id,
        artifact_type="architecture_graph",
        artifact_key="overview",
        artifact_version=ARCHITECTURE_GRAPH_VERSION,
        payload_model=ArchitectureGraphResponse,
        commit_sha=commit_sha,
    )
    if cached is not None and cached.snapshot_id == snapshot_id:
        if feature_flow_id and not any(
            feature_flow_id in node.feature_flow_ids for node in cached.nodes
        ):
            raise HTTPException(
                status_code=404,
                detail="Feature flow not found in architecture graph",
            )
        response.headers["X-Navigation-Cache"] = "HIT"
        response.headers["X-Navigation-Artifact-Version"] = ARCHITECTURE_GRAPH_VERSION
        return cached

    files = db.scalars(
        select(FileRecord).where(FileRecord.snapshot_id == snapshot_id).order_by(FileRecord.path)
    ).all()
    symbols = db.scalars(
        select(Symbol)
        .where(Symbol.snapshot_id == snapshot_id)
        .order_by(Symbol.file_id, Symbol.start_line)
    ).all()
    semantic_edges = db.scalars(
        select(SymbolEdge).where(
            SymbolEdge.snapshot_id == snapshot_id,
            SymbolEdge.relation.in_(IMPORTANT_RELATIONS),
        )
    ).all()
    import_edges = [edge for edge in semantic_edges if edge.relation == "IMPORTS"]
    project_map = build_project_map(snapshot, files, import_edges)
    catalog = build_feature_flows(snapshot, files, symbols, semantic_edges)
    feature_flows = [
        detail
        for summary in catalog.flows
        if (detail := build_feature_flow(snapshot, files, symbols, semantic_edges, summary.id))
        is not None
    ]
    if feature_flow_id and not any(flow.id == feature_flow_id for flow in feature_flows):
        raise HTTPException(status_code=404, detail="Feature flow not found")

    graph = build_architecture_graph(
        snapshot,
        files,
        symbols,
        semantic_edges,
        project_map,
        feature_flows,
    )
    validation = validate_architecture_graph(
        graph,
        files=list(files),
        project_map=project_map,
        feature_flows=feature_flows,
    )
    if not validation.valid:
        graph = graph.model_copy(
            update={
                "limitations": [
                    *graph.limitations,
                    *[f"구조도 검증: {issue}" for issue in validation.issues],
                ]
            }
        )
    stored = write_navigation_artifacts(
        db,
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        artifacts=[
            ArtifactWrite(
                artifact_type="architecture_graph",
                artifact_key="overview",
                artifact_version=ARCHITECTURE_GRAPH_VERSION,
                payload=graph,
                generation_metadata={
                    "semantic_graph_version": snapshot.parser_version,
                    "project_map_version": PROJECT_MAP_VERSION,
                    "feature_flow_version": FEATURE_FLOW_VERSION,
                    "validation_valid": validation.valid,
                    "flow_mapping_coverage": validation.flow_mapping_coverage,
                },
            )
        ],
    )
    response.headers["X-Navigation-Cache"] = "MISS"
    response.headers["X-Navigation-Cache-Write"] = "STORED" if stored else "SKIPPED"
    response.headers["X-Navigation-Artifact-Version"] = ARCHITECTURE_GRAPH_VERSION
    return graph


@router.get(
    "/snapshots/{snapshot_id}/architecture-graph/mermaid",
    response_class=PlainTextResponse,
)
def export_architecture_graph_mermaid(snapshot_id: str, db: SessionDep):
    graph = get_architecture_graph(snapshot_id, Response(), db)
    return PlainTextResponse(
        architecture_graph_to_mermaid(graph),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": (f'attachment; filename="{snapshot_id}-architecture.mmd"')},
    )


@router.get(
    "/snapshots/{snapshot_id}/architecture-graph/diff",
    response_model=ArchitectureGraphDiffResponse,
)
def get_architecture_graph_diff(
    snapshot_id: str,
    base_snapshot_id: str,
    db: SessionDep,
):
    target_snapshot = load_snapshot(db, snapshot_id)
    base_snapshot = load_snapshot(db, base_snapshot_id)
    require_ready(target_snapshot)
    require_ready(base_snapshot)
    if target_snapshot.repository_id != base_snapshot.repository_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Architecture diff snapshots must belong to the same repository",
        )
    if {
        target_snapshot.parser_version,
        base_snapshot.parser_version,
    } != {"semantic-ts-v2"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Architecture diff requires semantic-ts-v2 snapshots",
        )
    target_graph = get_architecture_graph(snapshot_id, Response(), db)
    base_graph = get_architecture_graph(base_snapshot_id, Response(), db)
    return diff_architecture_graphs(base_graph, target_graph)


@router.post(
    "/snapshots/{snapshot_id}/architecture-graph/enhance-labels",
    response_model=ArchitectureGraphResponse,
)
def enhance_architecture_graph(
    snapshot_id: str,
    response: Response,
    db: SessionDep,
    auth: AuthDep,
):
    if not settings.navigation_llm_labels_enabled:
        raise HTTPException(
            status_code=404,
            detail="Architecture label enhancement is disabled",
        )
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    commit_sha = snapshot.commit_sha or ""
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot_id,
        artifact_type="architecture_graph_labels",
        artifact_key="overview",
        artifact_version=ARCHITECTURE_LABEL_VERSION,
        payload_model=ArchitectureGraphResponse,
        commit_sha=commit_sha,
    )
    if cached is not None:
        response.headers["X-Navigation-Cache"] = "HIT"
        response.headers["X-Navigation-Artifact-Version"] = ARCHITECTURE_LABEL_VERSION
        return cached
    graph = get_architecture_graph(snapshot_id, Response(), db)
    usage: dict[str, int] = {}

    def record(provider_response, *, embedding: bool = False) -> None:
        measured = extract_usage(provider_response, embedding=embedding).as_dict()
        for key, value in measured.items():
            usage[key] = usage.get(key, 0) + value

    usage_context = (
        UsageContext(
            organization_id=auth.organization_id,
            user_id=auth.user_id,
            feature="architecture_label_generation",
            request_id=f"architecture-label:{snapshot_id}",
            idempotency_key=f"architecture-label:{snapshot_id}:{ARCHITECTURE_LABEL_VERSION}",
        )
        if auth.authenticated
        else None
    )
    reservation = (
        UsageService(settings).reserve(
            db,
            context=usage_context,
            estimated_cost_micro_usd=settings.chat_generation_reservation_micro_usd,
        )
        if usage_context
        else None
    )
    try:
        enhanced = enhance_architecture_graph_labels(graph, settings, recorder=record)
    except Exception as exc:
        if reservation is not None:
            UsageService(settings).release(db, reservation.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Architecture label enhancement is unavailable",
        ) from exc
    if usage_context:
        UsageService(settings).settle(
            db,
            reservation_id=reservation.id if reservation else None,
            context=usage_context,
            provider="openai",
            model=settings.generation_model,
            usage=usage,
        )
    stored = write_navigation_artifacts(
        db,
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        artifacts=[
            ArtifactWrite(
                artifact_type="architecture_graph_labels",
                artifact_key="overview",
                artifact_version=ARCHITECTURE_LABEL_VERSION,
                payload=enhanced,
                generation_metadata={
                    "base_architecture_version": ARCHITECTURE_GRAPH_VERSION,
                    "model": settings.generation_model,
                    "constrained_node_ids": True,
                },
            )
        ],
    )
    response.headers["X-Navigation-Cache"] = "MISS"
    response.headers["X-Navigation-Cache-Write"] = "STORED" if stored else "SKIPPED"
    response.headers["X-Navigation-Artifact-Version"] = ARCHITECTURE_LABEL_VERSION
    return enhanced


@router.get("/snapshots/{snapshot_id}/project-map", response_model=ProjectMapResponse)
def get_project_map(snapshot_id: str, response: Response, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    commit_sha = snapshot.commit_sha or ""
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot_id,
        artifact_type="project_map",
        artifact_key="default",
        artifact_version=PROJECT_MAP_VERSION,
        payload_model=ProjectMapResponse,
        commit_sha=commit_sha,
    )
    if cached is not None and cached.snapshot_id == snapshot_id:
        response.headers["X-Navigation-Cache"] = "HIT"
        response.headers["X-Navigation-Artifact-Version"] = PROJECT_MAP_VERSION
        return cached
    files = db.scalars(
        select(FileRecord).where(FileRecord.snapshot_id == snapshot_id).order_by(FileRecord.path)
    ).all()
    import_edges = db.scalars(
        select(SymbolEdge).where(
            SymbolEdge.snapshot_id == snapshot_id,
            SymbolEdge.relation == "IMPORTS",
        )
    ).all()
    project_map = build_project_map(snapshot, files, import_edges)
    stored = write_navigation_artifacts(
        db,
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        artifacts=[
            ArtifactWrite(
                artifact_type="project_map",
                artifact_key="default",
                artifact_version=PROJECT_MAP_VERSION,
                payload=project_map,
                generation_metadata={"semantic_graph_version": snapshot.parser_version},
            )
        ],
    )
    response.headers["X-Navigation-Cache"] = "MISS"
    response.headers["X-Navigation-Cache-Write"] = "STORED" if stored else "SKIPPED"
    response.headers["X-Navigation-Artifact-Version"] = PROJECT_MAP_VERSION
    return project_map


def load_feature_flow_context(snapshot_id: str, db: Session):
    files = db.scalars(
        select(FileRecord)
        .where(FileRecord.snapshot_id == snapshot_id)
        .options(load_only(FileRecord.id, FileRecord.path, FileRecord.line_count))
        .order_by(FileRecord.path)
    ).all()
    symbols = db.scalars(
        select(Symbol)
        .where(Symbol.snapshot_id == snapshot_id)
        .options(
            load_only(
                Symbol.id,
                Symbol.file_id,
                Symbol.qualified_name,
                Symbol.display_name,
                Symbol.kind,
                Symbol.start_line,
                Symbol.end_line,
            )
        )
        .order_by(Symbol.file_id, Symbol.start_line, Symbol.id)
    ).all()
    semantic_edges = db.scalars(
        select(SymbolEdge)
        .where(
            SymbolEdge.snapshot_id == snapshot_id,
            SymbolEdge.relation.in_(
                (
                    "TRIGGERS",
                    "REQUESTS",
                    "HANDLED_BY",
                    "READS",
                    "WRITES",
                    "NAVIGATES_TO",
                    "USES_EXTERNAL",
                    "CALLS",
                    "RAISES",
                )
            ),
        )
        .options(
            load_only(
                SymbolEdge.id,
                SymbolEdge.source_file_id,
                SymbolEdge.source_symbol_id,
                SymbolEdge.target_symbol_id,
                SymbolEdge.target_path,
                SymbolEdge.relation,
                SymbolEdge.confidence,
                SymbolEdge.source_start_line,
                SymbolEdge.source_end_line,
                SymbolEdge.metadata_json,
            )
        )
    ).all()
    return files, symbols, semantic_edges


@router.get("/snapshots/{snapshot_id}/feature-flows", response_model=FeatureFlowListResponse)
def get_feature_flows(snapshot_id: str, response: Response, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    commit_sha = snapshot.commit_sha or ""
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot_id,
        artifact_type="feature_flow_catalog",
        artifact_key="representative",
        artifact_version=FEATURE_FLOW_VERSION,
        payload_model=FeatureFlowListResponse,
        commit_sha=commit_sha,
    )
    if cached is not None and cached.snapshot_id == snapshot_id:
        response.headers["X-Navigation-Cache"] = "HIT"
        response.headers["X-Navigation-Artifact-Version"] = FEATURE_FLOW_VERSION
        return cached
    files, symbols, semantic_edges = load_feature_flow_context(snapshot_id, db)
    catalog = build_feature_flows(snapshot, files, symbols, semantic_edges)
    writes = [
        ArtifactWrite(
            artifact_type="feature_flow_catalog",
            artifact_key="representative",
            artifact_version=FEATURE_FLOW_VERSION,
            payload=catalog,
            generation_metadata={"semantic_graph_version": snapshot.parser_version},
        )
    ]
    for summary in catalog.flows:
        detail = build_feature_flow(snapshot, files, symbols, semantic_edges, summary.id)
        if detail is not None:
            writes.append(
                ArtifactWrite(
                    artifact_type="feature_flow_detail",
                    artifact_key=summary.id,
                    artifact_version=FEATURE_FLOW_VERSION,
                    payload=detail,
                    generation_metadata={"semantic_graph_version": snapshot.parser_version},
                )
            )
    stored = write_navigation_artifacts(
        db,
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        artifacts=writes,
    )
    response.headers["X-Navigation-Cache"] = "MISS"
    response.headers["X-Navigation-Cache-Write"] = "STORED" if stored else "SKIPPED"
    response.headers["X-Navigation-Artifact-Version"] = FEATURE_FLOW_VERSION
    return catalog


@router.get(
    "/snapshots/{snapshot_id}/feature-flows/{flow_id}",
    response_model=FeatureFlowDetail,
)
def get_feature_flow(snapshot_id: str, flow_id: str, response: Response, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    commit_sha = snapshot.commit_sha or ""
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot_id,
        artifact_type="feature_flow_detail",
        artifact_key=flow_id,
        artifact_version=FEATURE_FLOW_VERSION,
        payload_model=FeatureFlowDetail,
        commit_sha=commit_sha,
    )
    if cached is not None and cached.id == flow_id:
        response.headers["X-Navigation-Cache"] = "HIT"
        response.headers["X-Navigation-Artifact-Version"] = FEATURE_FLOW_VERSION
        return cached
    files, symbols, semantic_edges = load_feature_flow_context(snapshot_id, db)
    flow = build_feature_flow(snapshot, files, symbols, semantic_edges, flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Feature flow not found")
    stored = write_navigation_artifacts(
        db,
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        artifacts=[
            ArtifactWrite(
                artifact_type="feature_flow_detail",
                artifact_key=flow_id,
                artifact_version=FEATURE_FLOW_VERSION,
                payload=flow,
                generation_metadata={"semantic_graph_version": snapshot.parser_version},
            )
        ],
    )
    response.headers["X-Navigation-Cache"] = "MISS"
    response.headers["X-Navigation-Cache-Write"] = "STORED" if stored else "SKIPPED"
    response.headers["X-Navigation-Artifact-Version"] = FEATURE_FLOW_VERSION
    return flow


@router.get(
    "/snapshots/{snapshot_id}/repository-story",
    response_model=RepositoryStoryResponse,
)
def get_repository_story(snapshot_id: str, response: Response, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    commit_sha = snapshot.commit_sha or ""
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot_id,
        artifact_type="repository_story",
        artifact_key="overview",
        artifact_version=REPOSITORY_STORY_VERSION,
        payload_model=RepositoryStoryResponse,
        commit_sha=commit_sha,
    )
    if cached is not None and cached.snapshot_id == snapshot_id:
        response.headers["X-Navigation-Cache"] = "HIT"
        response.headers["X-Navigation-Artifact-Version"] = REPOSITORY_STORY_VERSION
        return cached

    project_map = get_project_map(snapshot_id, Response(), db)
    implementation_graph = get_architecture_graph(snapshot_id, Response(), db)
    feature_catalog = get_feature_flows(snapshot_id, Response(), db)
    story = build_repository_story(
        snapshot,
        project_map,
        implementation_graph,
        feature_catalog.flows,
    )
    files = list(
        db.scalars(
            select(FileRecord)
            .where(FileRecord.snapshot_id == snapshot_id)
            .order_by(FileRecord.path)
        ).all()
    )
    validation = validate_repository_story(story, files=files)
    if not validation.valid:
        story = story.model_copy(
            update={
                "limitations": [
                    *story.limitations,
                    *[f"Repository Story 검증: {issue}" for issue in validation.issues],
                ]
            }
        )
    stored = write_navigation_artifacts(
        db,
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        artifacts=[
            ArtifactWrite(
                artifact_type="repository_story",
                artifact_key="overview",
                artifact_version=REPOSITORY_STORY_VERSION,
                payload=story,
                generation_metadata={
                    "architecture_graph_version": ARCHITECTURE_GRAPH_VERSION,
                    "project_map_version": PROJECT_MAP_VERSION,
                    "feature_flow_version": FEATURE_FLOW_VERSION,
                    "validation_valid": validation.valid,
                    "evidence_validity": validation.evidence_validity,
                    "feature_mapping_coverage": validation.feature_mapping_coverage,
                    "generic_responsibility_ratio": (validation.generic_responsibility_ratio),
                },
            )
        ],
    )
    response.headers["X-Navigation-Cache"] = "MISS"
    response.headers["X-Navigation-Cache-Write"] = "STORED" if stored else "SKIPPED"
    response.headers["X-Navigation-Artifact-Version"] = REPOSITORY_STORY_VERSION
    return story


@router.post(
    "/snapshots/{snapshot_id}/code-explanations",
    response_model=CodeExplanationResponse,
)
def create_code_explanation(
    snapshot_id: str,
    payload: CodeExplanationCreate,
    response: Response,
    db: SessionDep,
):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    selection = payload.selection
    if selection.start_line > selection.end_line:
        raise HTTPException(
            status_code=422,
            detail="Selection start_line must be less than or equal to end_line",
        )
    if selection.end_line - selection.start_line + 1 > 80:
        raise HTTPException(
            status_code=422,
            detail="Code Focus supports at most 80 selected lines",
        )

    commit_sha = snapshot.commit_sha or ""
    artifact_key = ":".join(
        (
            selection.file_id,
            str(selection.start_line),
            str(selection.end_line),
            payload.depth,
            payload.feature_flow_id or "none",
            payload.flow_step_id or "none",
        )
    )
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot_id,
        artifact_type="code_explanation",
        artifact_key=artifact_key,
        artifact_version=CODE_EXPLANATION_VERSION,
        payload_model=CodeExplanationResponse,
        commit_sha=commit_sha,
    )
    if cached is not None and cached.snapshot_id == snapshot_id and cached.selection == selection:
        response.headers["X-Navigation-Cache"] = "HIT"
        response.headers["X-Navigation-Artifact-Version"] = CODE_EXPLANATION_VERSION
        return cached

    file = db.scalar(
        select(FileRecord).where(
            FileRecord.snapshot_id == snapshot_id,
            FileRecord.id == selection.file_id,
        )
    )
    if file is None:
        raise HTTPException(status_code=404, detail="Selected file not found")
    if selection.end_line > max(1, file.line_count):
        raise HTTPException(
            status_code=422,
            detail="Selection exceeds the selected file line range",
        )
    symbols = db.scalars(
        select(Symbol)
        .where(Symbol.snapshot_id == snapshot_id, Symbol.file_id == file.id)
        .order_by(Symbol.start_line, Symbol.end_line, Symbol.id)
    ).all()
    edges = db.scalars(
        select(SymbolEdge).where(
            SymbolEdge.snapshot_id == snapshot_id,
            SymbolEdge.source_file_id == file.id,
            SymbolEdge.relation.in_(SEMANTIC_FOCUS_RELATIONS),
        )
    ).all()

    flow_step = None
    if payload.feature_flow_id and payload.flow_step_id:
        flow = load_navigation_artifact(
            db,
            snapshot_id=snapshot_id,
            artifact_type="feature_flow_detail",
            artifact_key=payload.feature_flow_id,
            artifact_version=FEATURE_FLOW_VERSION,
            payload_model=FeatureFlowDetail,
            commit_sha=commit_sha,
        )
        if flow is not None and flow.id == payload.feature_flow_id:
            candidates = [*flow.normal_steps, *flow.failure_steps]
            candidate = next(
                (step for step in candidates if step.id == payload.flow_step_id),
                None,
            )
            if candidate and any(
                evidence.file_id == selection.file_id
                and evidence.start_line <= selection.end_line
                and evidence.end_line >= selection.start_line
                for evidence in candidate.evidence
            ):
                flow_step = candidate

    explanation = build_code_explanation(
        snapshot=snapshot,
        file=file,
        selection=selection,
        depth=payload.depth,
        symbols=symbols,
        edges=edges,
        flow_step=flow_step,
    )
    stored = write_navigation_artifacts(
        db,
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        artifacts=[
            ArtifactWrite(
                artifact_type="code_explanation",
                artifact_key=artifact_key,
                artifact_version=CODE_EXPLANATION_VERSION,
                payload=explanation,
                generation_metadata={
                    "semantic_graph_version": snapshot.parser_version,
                    "feature_flow_id": payload.feature_flow_id,
                    "flow_step_id": payload.flow_step_id,
                },
            )
        ],
    )
    response.headers["X-Navigation-Cache"] = "MISS"
    response.headers["X-Navigation-Cache-Write"] = "STORED" if stored else "SKIPPED"
    response.headers["X-Navigation-Artifact-Version"] = CODE_EXPLANATION_VERSION
    return explanation


@router.get("/snapshots/{snapshot_id}/start-here", response_model=StartHereResponse)
def get_start_here(snapshot_id: str, db: SessionDep):
    snapshot = load_snapshot(db, snapshot_id)
    require_ready(snapshot)
    files = db.scalars(select(FileRecord).where(FileRecord.snapshot_id == snapshot_id)).all()

    languages = {file.language for file in files}
    tech_stack: list[str] = []
    if languages & {"typescript", "tsx"}:
        tech_stack.append("TypeScript")
    if languages & {"javascript", "jsx"}:
        tech_stack.append("JavaScript")
    package_file = next((file for file in files if file.path == "package.json"), None)
    if package_file:
        try:
            package = json.loads(package_file.content)
            dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            known = {
                "next": "Next.js",
                "react": "React",
                "typescript": "TypeScript",
                "tailwindcss": "Tailwind CSS",
                "express": "Express",
                "vite": "Vite",
            }
            tech_stack.extend(
                label
                for key, label in known.items()
                if key in dependencies and label not in tech_stack
            )
        except json.JSONDecodeError:
            pass

    entry_candidates = [
        ("src/app/page.tsx", "Next.js App Router 시작 화면"),
        ("app/page.tsx", "Next.js App Router 시작 화면"),
        ("src/pages/index.tsx", "Next.js Pages Router 시작 화면"),
        ("src/main.tsx", "프론트엔드 애플리케이션 진입점"),
        ("src/index.ts", "애플리케이션 진입점"),
        ("server.ts", "서버 진입점"),
        ("index.ts", "패키지 진입점"),
        ("index.js", "패키지 진입점"),
        ("index.d.ts", "공개 타입 정의"),
    ]
    file_by_path = {file.path: file for file in files}
    entry_points = [
        EntryPoint(file_id=file_by_path[path].id, path=path, reason=reason)
        for path, reason in entry_candidates
        if path in file_by_path
    ][:5]
    if not entry_points:
        entry_points = [
            EntryPoint(file_id=file.id, path=file.path, reason="상위 수준의 코드 파일")
            for file in files
            if file.language in {"typescript", "tsx", "javascript", "jsx"}
        ][:3]

    directory_counts = Counter(file.path.split("/", 1)[0] for file in files if "/" in file.path)
    top_directories = [name for name, _ in directory_counts.most_common(5)]
    repository = snapshot.repository

    return StartHereResponse(
        repository_name=f"{repository.owner}/{repository.name}",
        snapshot_id=snapshot.id,
        commit_sha=snapshot.commit_sha or "",
        summary=(
            f"{snapshot.file_count}개 파일과 {snapshot.symbol_count}개 심볼을 "
            "현재 커밋 기준으로 분석했습니다."
        ),
        tech_stack=tech_stack,
        entry_points=entry_points,
        top_directories=top_directories,
        suggested_goals=[
            "프로젝트 진입점부터 보기",
            "주요 파일 구조 살펴보기",
            "함수와 클래스 목록 확인하기",
            "파일 의존성 그래프 보기",
        ],
    )
