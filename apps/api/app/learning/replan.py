from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.learning.curriculum import (
    append_curriculum_modules,
    load_curriculum_candidates,
    plan_curriculum,
    profile_fingerprint,
)
from app.models import (
    LearningLesson,
    LearningModule,
    LearningPath,
    LearningSession,
    RemediationBranch,
    Symbol,
)


@dataclass(frozen=True)
class ReplanResult:
    path_id: str
    preserved_lesson_ids: list[str]
    added_lesson_count: int
    revision: int


def replan_learning_session(db: Session, *, session_id: str) -> ReplanResult:
    learning_session = db.scalar(
        select(LearningSession)
        .where(LearningSession.id == session_id)
        .options(
            selectinload(LearningSession.profile),
            selectinload(LearningSession.path)
            .selectinload(LearningPath.modules)
            .selectinload(LearningModule.lessons)
            .selectinload(LearningLesson.steps),
        )
        .with_for_update()
    )
    if learning_session is None:
        raise ValueError("Learning session not found")
    path = learning_session.path
    profile = learning_session.profile
    candidates = load_curriculum_candidates(db, learning_session.snapshot_id)
    if not candidates:
        raise ValueError("Snapshot has no verified curriculum candidates")
    symbol_count = (
        db.scalar(
            select(func.count(Symbol.id)).where(Symbol.snapshot_id == learning_session.snapshot_id)
        )
        or 0
    )
    modules = plan_curriculum(candidates, profile, symbol_count=symbol_count)

    requested_completed = set(learning_session.completed_lesson_ids or [])
    all_lessons = [lesson for module in path.modules for lesson in module.lessons]
    valid_completed = [lesson for lesson in all_lessons if lesson.id in requested_completed]
    preserved_ids = [lesson.id for lesson in valid_completed]
    preserved_chunk_ids = {
        step.chunk_id for lesson in valid_completed for step in lesson.steps if step.chunk_id
    }
    preserved_minutes = sum(lesson.estimated_minutes for lesson in valid_completed)

    learning_session.current_module_id = None
    learning_session.current_lesson_id = None
    learning_session.current_step_id = None
    learning_session.return_stack = []
    learning_session.teaching_state = {}
    learning_session.current_selection = {}
    db.execute(
        delete(RemediationBranch).where(
            RemediationBranch.learning_session_id == learning_session.id
        )
    )

    for module in list(path.modules):
        completed_in_module = [
            lesson for lesson in module.lessons if lesson.id in requested_completed
        ]
        if not completed_in_module:
            db.delete(module)
            continue
        for lesson in list(module.lessons):
            if lesson.id not in requested_completed:
                db.delete(lesson)
        module.estimated_minutes = sum(lesson.estimated_minutes for lesson in completed_in_module)
    db.flush()

    max_ordinal = (
        db.scalar(select(func.max(LearningModule.ordinal)).where(LearningModule.path_id == path.id))
        or 0
    )
    future_minutes = append_curriculum_modules(
        db,
        path=path,
        modules=modules,
        profile=profile,
        start_ordinal=max_ordinal + 1,
        excluded_chunk_ids=preserved_chunk_ids,
    )
    db.flush()
    total_lessons = (
        db.scalar(
            select(func.count(LearningLesson.id))
            .join(LearningModule, LearningLesson.module_id == LearningModule.id)
            .where(LearningModule.path_id == path.id)
        )
        or 0
    )
    module_types = list(
        db.scalars(select(LearningModule.module_type).where(LearningModule.path_id == path.id))
    )
    previous_metadata = dict(path.model_metadata or {})
    revision = int(previous_metadata.get("revision", 1)) + 1
    path.model_metadata = {
        **previous_metadata,
        "planner": "deterministic-candidate-planner-v1",
        "profile_fingerprint": profile_fingerprint(profile),
        "profile_assessment_version": profile.assessment_version,
        "candidate_count": len(candidates),
        "revision": revision,
        "preserved_lesson_count": len(preserved_ids),
    }
    path.generation_method = "verified-structure-replan-v1"
    path.estimated_minutes = preserved_minutes + future_minutes
    path.coverage = {
        key: "covered" if key in module_types else "not_applicable"
        for key in (
            "orientation",
            "foundations",
            "architecture",
            "feature_flow",
            "data_failure",
            "test_apply",
        )
    }
    learning_session.completed_lesson_ids = preserved_ids
    learning_session.status = "active" if total_lessons > len(preserved_ids) else "completed"
    db.flush()
    return ReplanResult(
        path_id=path.id,
        preserved_lesson_ids=preserved_ids,
        added_lesson_count=max(0, total_lessons - len(preserved_ids)),
        revision=revision,
    )
