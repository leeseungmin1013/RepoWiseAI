from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import NavigationArtifact


@dataclass(frozen=True)
class ArtifactWrite:
    artifact_type: str
    artifact_key: str
    artifact_version: str
    payload: BaseModel
    generation_metadata: dict[str, Any] = field(default_factory=dict)


def load_navigation_artifact[ArtifactModel: BaseModel](
    db: Session,
    *,
    snapshot_id: str,
    artifact_type: str,
    artifact_key: str,
    artifact_version: str,
    payload_model: type[ArtifactModel],
    commit_sha: str,
) -> ArtifactModel | None:
    """Return a validated artifact or a cache miss without mutating the session."""

    try:
        artifact = db.scalar(
            select(NavigationArtifact).where(
                NavigationArtifact.snapshot_id == snapshot_id,
                NavigationArtifact.artifact_type == artifact_type,
                NavigationArtifact.artifact_key == artifact_key,
                NavigationArtifact.artifact_version == artifact_version,
                NavigationArtifact.status == "ready",
            )
        )
    except SQLAlchemyError:
        db.rollback()
        return None
    if artifact is None:
        return None
    if (
        artifact.snapshot_id != snapshot_id
        or artifact.artifact_type != artifact_type
        or artifact.artifact_key != artifact_key
        or artifact.artifact_version != artifact_version
        or artifact.status != "ready"
    ):
        return None
    metadata = artifact.generation_metadata
    if not isinstance(metadata, dict) or metadata.get("commit_sha") != commit_sha:
        return None
    try:
        return payload_model.model_validate(artifact.payload_json)
    except (TypeError, ValidationError):
        return None


def write_navigation_artifacts(
    db: Session,
    *,
    snapshot_id: str,
    commit_sha: str,
    artifacts: Iterable[ArtifactWrite],
) -> bool:
    """Atomically upsert deterministic artifacts; cache failures never fail the request."""

    writes = list(artifacts)
    if not writes:
        return True
    now = datetime.now(UTC)
    values = []
    for artifact in writes:
        payload = artifact.payload.model_dump(mode="json")
        values.append(
            {
                "id": _artifact_id(
                    snapshot_id,
                    artifact.artifact_type,
                    artifact.artifact_key,
                    artifact.artifact_version,
                ),
                "snapshot_id": snapshot_id,
                "artifact_type": artifact.artifact_type,
                "artifact_key": artifact.artifact_key,
                "artifact_version": artifact.artifact_version,
                "status": "ready",
                "payload_json": payload,
                "evidence_ids": _evidence_ids(payload),
                "confidence_summary": _confidence_summary(payload),
                "generation_metadata": {
                    **artifact.generation_metadata,
                    "commit_sha": commit_sha,
                    "generator": "deterministic_navigation_builder",
                },
                "created_at": now,
                "updated_at": now,
            }
        )

    statement = postgresql_insert(NavigationArtifact).values(values)
    excluded = statement.excluded
    statement = statement.on_conflict_do_update(
        index_elements=[
            NavigationArtifact.snapshot_id,
            NavigationArtifact.artifact_type,
            NavigationArtifact.artifact_key,
            NavigationArtifact.artifact_version,
        ],
        set_={
            "status": excluded.status,
            "payload_json": excluded.payload_json,
            "evidence_ids": excluded.evidence_ids,
            "confidence_summary": excluded.confidence_summary,
            "generation_metadata": excluded.generation_metadata,
            "updated_at": excluded.updated_at,
        },
    )
    try:
        db.execute(statement)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return False
    return True


def _artifact_id(
    snapshot_id: str, artifact_type: str, artifact_key: str, artifact_version: str
) -> str:
    semantic_key = "|".join(
        (snapshot_id, artifact_type, artifact_key, artifact_version)
    )
    digest = hashlib.sha256(semantic_key.encode("utf-8")).hexdigest()[:32]
    return f"navart_{digest}"


def _evidence_ids(payload: object) -> list[str]:
    evidence_ids: set[str] = set()
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            file_id = current.get("file_id")
            if (
                isinstance(file_id, str)
                and isinstance(current.get("path"), str)
                and isinstance(current.get("start_line"), int)
            ):
                evidence_ids.add(file_id)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return sorted(evidence_ids)


def _confidence_summary(payload: object) -> dict[str, int]:
    counts: Counter[str] = Counter()
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            confidence = current.get("confidence")
            if confidence in {"verified", "inferred", "unknown"}:
                counts[str(confidence)] += 1
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return {
        key: counts.get(key, 0) for key in ("verified", "inferred", "unknown")
    }
