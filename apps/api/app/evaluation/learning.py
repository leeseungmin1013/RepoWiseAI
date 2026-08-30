from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import REPOSITORY_ROOT, get_settings
from app.core.db import SessionLocal
from app.learning.activities import ensure_learning_activity
from app.learning.explanations import get_or_create_line_explanation
from app.models import (
    ChatMessage,
    ChatSession,
    CodeChunk,
    ExplanationArtifact,
    FileRecord,
    KnowledgeSource,
    LearningActivity,
    LearningLesson,
    LearningModule,
    LearningPath,
    LearningStep,
    Repository,
    RepositorySnapshot,
    RetrievalRun,
)


class LearningGoldFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    repository: str
    required_module_types: list[str] = Field(min_length=1)
    required_activity_types: list[str] = Field(default_factory=list)
    allowed_source_domains: list[str] = Field(min_length=1)
    thresholds: dict[str, float] = Field(default_factory=dict)


def _ratio(numerator: int, denominator: int, *, empty: float = 0.0) -> float:
    return numerator / denominator if denominator else empty


def evaluate_learning_output(
    output: dict[str, Any],
    fixture: LearningGoldFixture,
) -> dict[str, Any]:
    modules = output.get("modules") or []
    lessons = output.get("lessons") or []
    activities = output.get("activities") or []
    artifacts = output.get("artifacts") or []
    sources = output.get("sources") or []
    retrievals = output.get("learning_retrievals") or []

    expected_modules = set(fixture.required_module_types)
    actual_modules = {str(item.get("module_type")) for item in modules}
    module_coverage = _ratio(
        len(expected_modules & actual_modules),
        len(expected_modules),
        empty=1.0,
    )

    lessons_with_evidence = sum(bool(item.get("evidence_ids")) for item in lessons)
    lesson_evidence_coverage = _ratio(
        lessons_with_evidence,
        len(lessons),
    )

    expected_activities = set(fixture.required_activity_types)
    actual_activities = {str(item.get("activity_type")) for item in activities}
    activity_type_coverage = _ratio(
        len(expected_activities & actual_activities),
        len(expected_activities),
        empty=1.0,
    )
    valid_activities = sum(
        item.get("verification_status") == "verified"
        and item.get("source_hash")
        and bool(item.get("evidence", {}).get("evidence_id"))
        and 1
        <= int(item.get("evidence", {}).get("start_line", 0))
        <= int(item.get("evidence", {}).get("end_line", 0))
        <= int(item.get("file_line_count", 0))
        for item in activities
    )
    activity_evidence_validity = _ratio(
        valid_activities,
        len(activities),
    )

    valid_segments = 0
    total_segments = 0
    for artifact in artifacts:
        for segment in artifact.get("segments") or []:
            total_segments += 1
            valid_segments += int(
                artifact.get("verification_status") == "verified"
                and artifact.get("source_hash") == artifact.get("chunk_source_hash")
                and bool(segment.get("source"))
                and int(artifact.get("chunk_start_line", 0))
                <= int(segment.get("start_line", 0))
                <= int(segment.get("end_line", 0))
                <= int(artifact.get("chunk_end_line", 0))
            )
    statement_span_validity = _ratio(valid_segments, total_segments)

    allowed_domains = {item.casefold().rstrip(".") for item in fixture.allowed_source_domains}
    valid_sources = 0
    for source in sources:
        parsed = urlparse(str(source.get("canonical_url", "")))
        host = (parsed.hostname or "").casefold().rstrip(".")
        allowed = any(host == domain or host.endswith("." + domain) for domain in allowed_domains)
        valid_sources += int(
            parsed.scheme == "https"
            and allowed
            and source.get("source_tier") == "official"
            and source.get("freshness_status") != "unavailable"
        )
    source_policy_precision = _ratio(valid_sources, len(sources))

    required_concepts = {
        str(concept)
        for lesson in lessons
        for concept in lesson.get("required_concept_ids") or []
    }
    sourced_concepts = {str(item.get("concept_id")) for item in sources}
    source_concept_coverage = _ratio(
        len(required_concepts & sourced_concepts),
        len(required_concepts),
        empty=1.0,
    )

    valid_learning_retrievals = sum(
        bool(item.get("learning_session_id"))
        and bool(item.get("concept_ids"))
        and "현재 학습 단계:" in str(item.get("query_text", ""))
        for item in retrievals
    )
    learning_context_retrieval_coverage = _ratio(
        valid_learning_retrievals,
        len(retrievals),
    )

    report: dict[str, Any] = {
        "fixture": fixture.name,
        "repository": fixture.repository,
        "curriculum_module_coverage": round(module_coverage, 4),
        "lesson_evidence_coverage": round(lesson_evidence_coverage, 4),
        "activity_type_coverage": round(activity_type_coverage, 4),
        "activity_evidence_validity": round(activity_evidence_validity, 4),
        "statement_span_validity": round(statement_span_validity, 4),
        "source_policy_precision": round(source_policy_precision, 4),
        "source_concept_coverage": round(source_concept_coverage, 4),
        "learning_context_retrieval_coverage": round(
            learning_context_retrieval_coverage,
            4,
        ),
        "counts": {
            "modules": len(modules),
            "lessons": len(lessons),
            "activities": len(activities),
            "statement_segments": total_segments,
            "sources": len(sources),
            "learning_retrievals": len(retrievals),
        },
    }
    failures = [
        metric
        for metric, threshold in fixture.thresholds.items()
        if float(report.get(metric, 0.0)) < threshold
    ]
    report["failed_thresholds"] = failures
    report["passed"] = not failures
    return report


def evaluate_fixture(
    fixture: LearningGoldFixture,
    *,
    snapshot_id: str | None = None,
    materialize: bool = False,
) -> dict[str, Any]:
    with SessionLocal() as db:
        owner, name = fixture.repository.split("/", 1)
        path_statement = (
            select(LearningPath)
            .join(
                RepositorySnapshot,
                RepositorySnapshot.id == LearningPath.snapshot_id,
            )
            .join(Repository, Repository.id == RepositorySnapshot.repository_id)
            .where(RepositorySnapshot.status == "ready")
            .options(
                selectinload(LearningPath.snapshot),
                selectinload(LearningPath.modules)
                .selectinload(LearningModule.lessons)
                .selectinload(LearningLesson.steps)
                .selectinload(LearningStep.activities),
            )
        )
        if snapshot_id:
            path_statement = path_statement.where(
                RepositorySnapshot.id == snapshot_id
            )
        else:
            path_statement = path_statement.where(
                Repository.owner == owner,
                Repository.name == name,
            )
        path = db.scalar(
            path_statement.order_by(LearningPath.created_at.desc()).limit(1)
        )
        if path is None:
            raise RuntimeError(
                "No ready snapshot with a learning path matched the learning gold fixture"
            )
        snapshot = path.snapshot
        materialized = {"activities": 0, "explanations": 0}
        if materialize:
            materialized = _materialize_learning_artifacts(db, path)
            db.commit()
            db.expire_all()
            path = db.scalar(
                path_statement.where(LearningPath.id == path.id).limit(1)
            )
            if path is None:
                raise RuntimeError("Learning path disappeared after materialization")
            snapshot = path.snapshot

        modules = list(path.modules)
        lessons = [lesson for module in modules for lesson in module.lessons]
        activities: list[LearningActivity] = [
            activity
            for lesson in lessons
            for step in lesson.steps
            for activity in step.activities
        ]
        file_line_counts = {
            item.id: item.line_count
            for item in db.scalars(
                select(FileRecord).where(FileRecord.snapshot_id == snapshot.id)
            ).all()
        }
        chunks = {
            item.id: item
            for item in db.scalars(
                select(CodeChunk).where(CodeChunk.snapshot_id == snapshot.id)
            ).all()
        }
        artifacts = db.scalars(
            select(ExplanationArtifact).where(
                ExplanationArtifact.snapshot_id == snapshot.id,
                ExplanationArtifact.artifact_type == "line_by_line",
            )
        ).all()
        concepts = {
            concept
            for lesson in lessons
            for concept in (lesson.required_concept_ids or [])
        }
        sources = (
            db.scalars(
                select(KnowledgeSource).where(KnowledgeSource.concept_id.in_(concepts))
            ).all()
            if concepts
            else []
        )
        retrieval_rows = db.execute(
            select(ChatMessage, RetrievalRun)
            .join(RetrievalRun, RetrievalRun.message_id == ChatMessage.id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                ChatSession.snapshot_id == snapshot.id,
                ChatSession.learning_session_id.is_not(None),
                ChatMessage.role == "user",
            )
        ).all()

    output = {
        "modules": [{"module_type": item.module_type} for item in modules],
        "lessons": [
            {
                "evidence_ids": list(item.evidence_ids or []),
                "required_concept_ids": list(item.required_concept_ids or []),
            }
            for item in lessons
        ],
        "activities": [
            {
                "activity_type": item.activity_type,
                "verification_status": item.verification_status,
                "source_hash": item.source_hash,
                "evidence": item.evidence or {},
                "file_line_count": file_line_counts.get(
                    str((item.evidence or {}).get("file_id")),
                    0,
                ),
            }
            for item in activities
        ],
        "artifacts": [
            {
                "verification_status": item.verification_status,
                "source_hash": item.source_hash,
                "segments": list(item.segments or []),
                "chunk_source_hash": (
                    chunks[item.chunk_id].content_hash if item.chunk_id in chunks else None
                ),
                "chunk_start_line": (
                    chunks[item.chunk_id].start_line if item.chunk_id in chunks else 0
                ),
                "chunk_end_line": (
                    chunks[item.chunk_id].end_line if item.chunk_id in chunks else 0
                ),
            }
            for item in artifacts
        ],
        "sources": [
            {
                "concept_id": item.concept_id,
                "canonical_url": item.canonical_url,
                "source_tier": item.source_tier,
                "freshness_status": item.freshness_status,
            }
            for item in sources
        ],
        "learning_retrievals": [
            {
                "query_text": run.query_text,
                "learning_session_id": (
                    message.structured_payload.get("learning_context", {}).get(
                        "learning_session_id"
                    )
                ),
                "concept_ids": (
                    message.structured_payload.get("learning_context", {}).get(
                        "concept_ids",
                        [],
                    )
                ),
            }
            for message, run in retrieval_rows
        ],
    }
    report = evaluate_learning_output(output, fixture)
    report.update(
        {
            "snapshot_id": snapshot.id,
            "commit_sha": snapshot.commit_sha or "",
            "learning_path_id": path.id,
            "path_version": path.path_version,
            "materialized": materialized,
        }
    )
    return report


def _materialize_learning_artifacts(
    db: Any,
    path: LearningPath,
) -> dict[str, int]:
    settings = get_settings().model_copy(
        update={
            "openai_api_key": None,
            "generation_provider": "local",
        }
    )
    activity_ids: set[str] = set()
    explanation_ids: set[str] = set()
    scores = {
        "beginner": 0.2,
        "intermediate": 0.55,
        "advanced": 0.85,
    }
    for module in path.modules:
        for lesson in module.lessons:
            concept_ids = list(lesson.required_concept_ids or [])
            for step in lesson.steps:
                if step.chunk_id is None:
                    continue
                for score in scores.values():
                    mastery = {
                        concept_id: {"score": score, "confidence": 1.0}
                        for concept_id in concept_ids
                    }
                    activity, _, _ = ensure_learning_activity(
                        db,
                        step_id=step.id,
                        mastery=mastery,
                    )
                    activity_ids.add(activity.id)
                artifact, _, _, _ = get_or_create_line_explanation(
                    db,
                    step_id=step.id,
                    depth_band="beginner",
                    settings=settings,
                )
                explanation_ids.add(artifact.id)
    return {
        "activities": len(activity_ids),
        "explanations": len(explanation_ids),
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate grounded learning quality")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("apps/api/evaluation/fixtures/learning_repowise_gold_v1.json"),
    )
    parser.add_argument("--snapshot-id")
    parser.add_argument("--report-out", type=Path)
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="Create deterministic activities and line explanations before evaluation",
    )
    args = parser.parse_args()

    fixture_path = args.fixture
    if not fixture_path.is_absolute():
        fixture_path = REPOSITORY_ROOT / fixture_path
    fixture = LearningGoldFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    report = evaluate_fixture(
        fixture,
        snapshot_id=args.snapshot_id,
        materialize=args.materialize,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report_out:
        report_path = args.report_out
        if not report_path.is_absolute():
            report_path = REPOSITORY_ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()