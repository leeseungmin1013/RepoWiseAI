from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.auth import AuthContext
from app.core.config import Settings
from app.models import (
    AnalysisJob,
    OrganizationRepository,
    Repository,
    RepositorySnapshot,
)
from app.navigation.versions import (
    ARCHITECTURE_GRAPH_VERSION,
    CODE_EXPLANATION_VERSION,
    FEATURE_FLOW_VERSION,
    PROJECT_MAP_VERSION,
    REPOSITORY_STORY_VERSION,
    SEMANTIC_GRAPH_VERSION,
)
from app.services.github import GitHubClient, GitHubSnapshot


def canonical_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def analysis_fingerprint(settings: Settings) -> str:
    return canonical_hash(
        {
            "version": settings.analysis_fingerprint_version,
            "filter": {
                "version": settings.file_filter_version,
                "max_files": settings.max_repository_files,
                "max_bytes": settings.max_repository_bytes,
                "max_file_bytes": settings.max_file_bytes,
            },
            "parser": SEMANTIC_GRAPH_VERSION,
            "languages": ["python", "typescript", "tsx", "javascript", "jsx"],
            "chunker": {
                "version": settings.chunker_version,
                "max_lines": settings.chunk_max_lines,
                "overlap_lines": settings.chunk_overlap_lines,
            },
            "embedding": {
                "provider": settings.embedding_provider,
                "model": settings.embedding_model,
                "dimensions": settings.embedding_dimensions,
                "prompt_version": settings.embedding_prompt_version,
            },
            "index": settings.retrieval_index_schema_version,
            "navigation": {
                "bundle": settings.navigation_artifact_bundle_version,
                "project_map": PROJECT_MAP_VERSION,
                "architecture": ARCHITECTURE_GRAPH_VERSION,
                "feature_flow": FEATURE_FLOW_VERSION,
                "story": REPOSITORY_STORY_VERSION,
                "code_explanation": CODE_EXPLANATION_VERSION,
            },
        }
    )


@dataclass(frozen=True)
class SnapshotResolution:
    repository: Repository
    snapshot: RepositorySnapshot
    job: AnalysisJob | None
    cache_hit: bool
    mode: str
    base_snapshot_id: str | None
    reason: str
    should_enqueue: bool


def _attach_repository(db: Session, repository: Repository, context: AuthContext) -> None:
    if not context.authenticated:
        return
    db.execute(
        insert(OrganizationRepository)
        .values(
            organization_id=context.organization_id,
            repository_id=repository.id,
            added_by=context.user_id,
        )
        .on_conflict_do_nothing(
            index_elements=["organization_id", "repository_id"],
        )
    )


def resolve_snapshot_request(
    db: Session,
    *,
    settings: Settings,
    context: AuthContext,
    owner: str,
    name: str,
    canonical_url: str,
    requested_branch: str | None,
    github: GitHubClient | None = None,
) -> SnapshotResolution:
    repository = db.scalar(
        select(Repository).where(
            Repository.provider == "github",
            Repository.owner == owner,
            Repository.name == name,
        )
    )
    if repository is None:
        repository = Repository(owner=owner, name=name, url=canonical_url)
        db.add(repository)
        db.flush()
    _attach_repository(db, repository, context)

    owned_client = github is None
    client = github or GitHubClient(settings)
    try:
        remote: GitHubSnapshot = client.resolve_snapshot(owner, name, requested_branch)
    finally:
        if owned_client:
            client.close()

    fingerprint = analysis_fingerprint(settings)
    if settings.exact_snapshot_reuse_enabled:
        existing = db.scalar(
            select(RepositorySnapshot)
            .where(
                RepositorySnapshot.repository_id == repository.id,
                RepositorySnapshot.commit_sha == remote.commit_sha,
                RepositorySnapshot.analysis_fingerprint == fingerprint,
            )
            .options(selectinload(RepositorySnapshot.jobs))
        )
        if existing is not None and existing.status in {"pending", "analyzing", "ready"}:
            existing.reuse_mode = "exact"
            latest_job = (
                max(existing.jobs, key=lambda item: item.created_at) if existing.jobs else None
            )
            db.commit()
            return SnapshotResolution(
                repository=repository,
                snapshot=existing,
                job=latest_job,
                cache_hit=True,
                mode="exact_snapshot",
                base_snapshot_id=existing.base_snapshot_id,
                reason="same_commit_and_analysis_fingerprint",
                should_enqueue=False,
            )

    base = db.scalar(
        select(RepositorySnapshot)
        .where(
            RepositorySnapshot.repository_id == repository.id,
            RepositorySnapshot.branch == remote.branch,
            RepositorySnapshot.analysis_fingerprint == fingerprint,
            RepositorySnapshot.status == "ready",
            RepositorySnapshot.commit_sha != remote.commit_sha,
        )
        .order_by(
            RepositorySnapshot.ready_at.desc().nullslast(), RepositorySnapshot.created_at.desc()
        )
        .limit(1)
    )
    mode = "incremental" if settings.incremental_analysis_enabled and base else "full"
    now = datetime.now(UTC)
    snapshot = RepositorySnapshot(
        repository_id=repository.id,
        branch=remote.branch,
        commit_sha=remote.commit_sha,
        analysis_fingerprint=fingerprint,
        base_snapshot_id=base.id if base else None,
        reuse_mode=mode,
        resolved_at=now,
    )
    db.add(snapshot)
    db.flush()
    job = AnalysisJob(
        snapshot_id=snapshot.id,
        requested_by_user_id=context.user_id if context.authenticated else None,
        organization_id=context.organization_id if context.authenticated else None,
        base_snapshot_id=base.id if base else None,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(
            select(RepositorySnapshot)
            .where(
                RepositorySnapshot.repository_id == repository.id,
                RepositorySnapshot.commit_sha == remote.commit_sha,
                RepositorySnapshot.analysis_fingerprint == fingerprint,
            )
            .options(selectinload(RepositorySnapshot.jobs))
        )
        if winner is None:
            raise
        latest_job = max(winner.jobs, key=lambda item: item.created_at) if winner.jobs else None
        return SnapshotResolution(
            repository=repository,
            snapshot=winner,
            job=latest_job,
            cache_hit=True,
            mode="exact_snapshot",
            base_snapshot_id=winner.base_snapshot_id,
            reason="single_flight_conflict_winner",
            should_enqueue=False,
        )
    return SnapshotResolution(
        repository=repository,
        snapshot=snapshot,
        job=job,
        cache_hit=False,
        mode=mode,
        base_snapshot_id=base.id if base else None,
        reason="compatible_base_snapshot" if base else "no_compatible_base_snapshot",
        should_enqueue=True,
    )
