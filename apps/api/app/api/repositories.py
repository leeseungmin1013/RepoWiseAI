import json
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analysis.tree import build_file_tree
from app.core.db import get_db
from app.models import AnalysisJob, FileRecord, Repository, RepositorySnapshot, Symbol, SymbolEdge
from app.queue import enqueue_repository_analysis
from app.schemas import (
    AnalysisJobResponse,
    EntryPoint,
    FileResponse,
    GraphEdge,
    GraphNode,
    GraphResponse,
    RepositoryCreate,
    RepositoryCreateResponse,
    RepositorySummary,
    SnapshotResponse,
    StartHereResponse,
    SymbolResponse,
    TreeNode,
)
from app.services.github import parse_github_url

router = APIRouter(tags=["repositories"])
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
def create_repository(payload: RepositoryCreate, db: SessionDep):
    try:
        owner, name, canonical_url = parse_github_url(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repository = db.scalar(
        select(Repository).where(
            Repository.provider == "github", Repository.owner == owner, Repository.name == name
        )
    )
    if repository is None:
        repository = Repository(owner=owner, name=name, url=canonical_url)
        db.add(repository)
        db.flush()

    snapshot = RepositorySnapshot(repository_id=repository.id, branch=payload.branch)
    db.add(snapshot)
    db.flush()
    analysis_job = AnalysisJob(snapshot_id=snapshot.id)
    db.add(analysis_job)
    db.commit()
    db.refresh(repository)
    db.refresh(snapshot)
    db.refresh(analysis_job)

    try:
        enqueue_repository_analysis(snapshot.id)
    except Exception as exc:
        snapshot.status = "failed"
        snapshot.error_message = "Analysis queue is unavailable"
        analysis_job.status = "failed"
        analysis_job.error_code = "queue_unavailable"
        analysis_job.error_detail = str(exc)
        db.commit()
        raise HTTPException(status_code=503, detail="Analysis queue is unavailable") from exc

    snapshot.jobs = [analysis_job]
    return RepositoryCreateResponse(
        repository=RepositorySummary.model_validate(repository),
        snapshot=to_snapshot_response(snapshot),
    )


@router.get("/snapshots", response_model=list[SnapshotResponse])
def list_snapshots(db: SessionDep, limit: SnapshotLimit = 10):
    snapshots = db.scalars(
        select(RepositorySnapshot)
        .options(selectinload(RepositorySnapshot.jobs))
        .order_by(RepositorySnapshot.created_at.desc())
        .limit(limit)
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
