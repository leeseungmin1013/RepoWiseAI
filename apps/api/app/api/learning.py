from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.ai.gateway import extract_usage
from app.core.auth import AuthDep
from app.core.config import get_settings
from app.core.db import get_db
from app.learning.activities import ensure_learning_activity
from app.learning.concepts import build_mastery_overview, resolve_concept_gaps
from app.learning.curriculum import ensure_learning_path
from app.learning.explanations import get_or_create_line_explanation
from app.learning.mastery import apply_mastery_event
from app.learning.replan import replan_learning_session
from app.learning.resources import (
    concept_bridge,
    recommended_sources,
    small_examples,
)
from app.models import (
    ActivityAttempt,
    ChatSession,
    CodeChunk,
    FileRecord,
    JourneyEvent,
    LearnerProfile,
    LearningActivity,
    LearningLesson,
    LearningModule,
    LearningPath,
    LearningSession,
    LearningStep,
    MasteryEvent,
    RemediationBranch,
    utc_now,
)
from app.retrieval.hybrid import evidence_id_for_chunk
from app.schemas import (
    ActivityAttemptCreate,
    ActivityAttemptResponse,
    ActivityAttemptSummary,
    CitationResponse,
    LearningActivityResponse,
    LearningLessonFeedbackCreate,
    LearningLessonResponse,
    LearningModuleResponse,
    LearningPathCreate,
    LearningPathResponse,
    LearningReplanResponse,
    LearningSelectionUpdate,
    LearningSessionCreate,
    LearningSessionResponse,
    LearningSourceResponse,
    LearningStepResponse,
    LineExplanationResponse,
    MasteryEventResponse,
    MasteryOverviewResponse,
    RemediationBranchResponse,
    RemediationCreate,
)
from app.services.usage import UsageContext, UsageService

router = APIRouter(tags=["adaptive-learning"])
SessionDep = Annotated[Session, Depends(get_db)]


@router.post(
    "/snapshots/{snapshot_id}/learning-paths",
    response_model=LearningPathResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_learning_path(snapshot_id: str, payload: LearningPathCreate, db: SessionDep):
    try:
        path = ensure_learning_path(
            db,
            snapshot_id=snapshot_id,
            learner_profile_id=payload.learner_profile_id,
            goal=payload.goal,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _path_response(db, path.id)


@router.get("/learning-paths/{path_id}", response_model=LearningPathResponse)
def get_learning_path(path_id: str, db: SessionDep):
    return _path_response(db, path_id)


@router.post(
    "/learning-paths/{path_id}/sessions",
    response_model=LearningSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_learning_session(path_id: str, payload: LearningSessionCreate, db: SessionDep):
    path = _load_path(db, path_id)
    existing = db.scalar(
        select(LearningSession).where(
            LearningSession.path_id == path.id,
            LearningSession.learner_profile_id == path.learner_profile_id,
            LearningSession.status.in_(["active", "completed"]),
        )
    )
    if existing is not None:
        return _session_response(db, existing)

    ordered = _ordered_lessons(path)
    if not ordered:
        raise HTTPException(status_code=409, detail="Learning path has no lessons")
    module, lesson = ordered[0]
    step = lesson.steps[0] if lesson.steps else None
    selection = _selection_for_step(db, step)
    learning_session = LearningSession(
        snapshot_id=path.snapshot_id,
        learner_profile_id=path.learner_profile_id,
        path_id=path.id,
        current_module_id=module.id,
        current_lesson_id=lesson.id,
        current_step_id=step.id if step else None,
        current_selection=selection,
        focus_concept_ids=list(lesson.required_concept_ids or []),
        teaching_state=_teaching_state(module, lesson, step),
    )
    db.add(learning_session)
    db.flush()
    db.add(
        ChatSession(
            snapshot_id=path.snapshot_id,
            goal=path.goal,
            preferred_style=payload.preferred_style,
            current_selection=selection,
            teaching_state=learning_session.teaching_state,
            learning_session_id=learning_session.id,
        )
    )
    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type="session_started",
            module_id=module.id,
            lesson_id=lesson.id,
            step_id=step.id if step else None,
        )
    )
    db.commit()
    db.refresh(learning_session)
    return _session_response(db, learning_session)


@router.get("/learning-sessions/{session_id}", response_model=LearningSessionResponse)
def get_learning_session(session_id: str, db: SessionDep):
    learning_session = db.get(LearningSession, session_id)
    if learning_session is None:
        raise HTTPException(status_code=404, detail="Learning session not found")
    return _session_response(db, learning_session)


@router.post(
    "/learning-sessions/{session_id}/replan",
    response_model=LearningReplanResponse,
)
def replan_learning_path(session_id: str, db: SessionDep):
    try:
        result = replan_learning_session(db, session_id=session_id)
        db.expire_all()
        learning_session = _load_learning_session(db, session_id)
        path = _load_path(db, result.path_id)
        ordered = _ordered_lessons(path)
        completed = set(learning_session.completed_lesson_ids or [])
        next_item = next(
            ((module, lesson) for module, lesson in ordered if lesson.id not in completed),
            None,
        )
        if next_item is not None:
            module, lesson = next_item
            step = lesson.steps[0] if lesson.steps else None
            _move_to_lesson(db, learning_session, module, lesson, step)
            learning_session.status = "active"
        else:
            learning_session.status = "completed"
        db.add(
            JourneyEvent(
                learning_session_id=learning_session.id,
                event_type="path_replanned",
                module_id=learning_session.current_module_id,
                lesson_id=learning_session.current_lesson_id,
                step_id=learning_session.current_step_id,
                payload={
                    "revision": result.revision,
                    "preserved_lesson_ids": result.preserved_lesson_ids,
                    "added_lesson_count": result.added_lesson_count,
                },
            )
        )
        _sync_chat_session(db, learning_session)
        db.commit()
        db.expire_all()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return LearningReplanResponse(
        path=_path_response(db, result.path_id),
        session=_session_response(db, _load_learning_session(db, session_id)),
        preserved_lesson_ids=result.preserved_lesson_ids,
        added_lesson_count=result.added_lesson_count,
        revision=result.revision,
    )


@router.patch(
    "/learning-sessions/{session_id}/selection",
    response_model=LearningSessionResponse,
)
def update_learning_selection(session_id: str, payload: LearningSelectionUpdate, db: SessionDep):
    learning_session = _load_learning_session(db, session_id)
    selection = _validated_selection(
        db,
        learning_session.snapshot_id,
        payload.selection.model_dump() if payload.selection else {},
    )
    learning_session.current_selection = selection
    _sync_chat_session(db, learning_session)
    db.commit()
    return _session_response(db, learning_session)


@router.post(
    "/learning-sessions/{session_id}/lessons/{lesson_id}/feedback",
    response_model=LearningSessionResponse,
)
def record_lesson_feedback(
    session_id: str,
    lesson_id: str,
    payload: LearningLessonFeedbackCreate,
    db: SessionDep,
):
    learning_session = _load_learning_session(db, session_id)
    path = _load_path(db, learning_session.path_id)
    ordered = _ordered_lessons(path)
    match = next(((module, lesson) for module, lesson in ordered if lesson.id == lesson_id), None)
    if match is None:
        raise HTTPException(status_code=409, detail="Lesson is not part of this learning path")
    module, lesson = match
    step = lesson.steps[0] if lesson.steps else None

    if payload.event_type in {"opened", "needs_help"}:
        _move_to_lesson(db, learning_session, module, lesson, step)
    if payload.event_type in {"understood", "skip"}:
        completed = list(learning_session.completed_lesson_ids or [])
        if lesson.id not in completed:
            completed.append(lesson.id)
        learning_session.completed_lesson_ids = completed
        if payload.event_type == "understood":
            apply_mastery_event(
                db,
                profile=learning_session.profile,
                learning_session_id=learning_session.id,
                concept_ids=list(lesson.required_concept_ids or []),
                event_type="lesson_understood",
                source_type="lesson_feedback",
                source_id=lesson.id,
                score_delta=0.08,
                confidence_delta=0.08,
                evidence={"evidence_ids": list(lesson.evidence_ids or [])},
            )
        next_item = _next_unfinished(ordered, lesson.id, set(completed))
        if next_item is None:
            learning_session.status = "completed"
        else:
            next_module, next_lesson = next_item
            next_step = next_lesson.steps[0] if next_lesson.steps else None
            _move_to_lesson(db, learning_session, next_module, next_lesson, next_step)
    elif payload.event_type == "needs_help":
        apply_mastery_event(
            db,
            profile=learning_session.profile,
            learning_session_id=learning_session.id,
            concept_ids=list(lesson.required_concept_ids or []),
            event_type="lesson_needs_help",
            source_type="lesson_feedback",
            source_id=lesson.id,
            score_delta=-0.06,
            confidence_delta=0.08,
            evidence={"evidence_ids": list(lesson.evidence_ids or [])},
        )
        learning_session.teaching_state = {
            **(learning_session.teaching_state or {}),
            "help_requested": True,
        }

    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type=payload.event_type,
            module_id=module.id,
            lesson_id=lesson.id,
            step_id=step.id if step else None,
        )
    )
    _sync_chat_session(db, learning_session)
    db.commit()
    return _session_response(db, learning_session)


@router.post(
    "/learning-sessions/{session_id}/steps/{step_id}/activity",
    response_model=LearningActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_learning_activity(session_id: str, step_id: str, db: SessionDep):
    learning_session = _load_learning_session(db, session_id)
    path_id = db.scalar(
        select(LearningModule.path_id)
        .join(LearningLesson, LearningLesson.module_id == LearningModule.id)
        .join(LearningStep, LearningStep.lesson_id == LearningLesson.id)
        .where(LearningStep.id == step_id)
    )
    if path_id != learning_session.path_id:
        raise HTTPException(status_code=409, detail="Step is not part of this session")
    try:
        activity, _, _ = ensure_learning_activity(db, step_id=step_id)
        latest = db.scalar(
            select(ActivityAttempt)
            .where(
                ActivityAttempt.learning_session_id == learning_session.id,
                ActivityAttempt.activity_id == activity.id,
            )
            .order_by(ActivityAttempt.created_at.desc())
            .limit(1)
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _activity_response(activity, latest)


@router.post(
    "/learning-sessions/{session_id}/activities/{activity_id}/attempts",
    response_model=ActivityAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_activity_attempt(
    session_id: str,
    activity_id: str,
    payload: ActivityAttemptCreate,
    db: SessionDep,
):
    learning_session = _load_learning_session(db, session_id)
    activity = db.scalar(
        select(LearningActivity)
        .where(LearningActivity.id == activity_id)
        .options(
            selectinload(LearningActivity.step)
            .selectinload(LearningStep.lesson)
            .selectinload(LearningLesson.module)
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Learning activity not found")
    if activity.step.lesson.module.path_id != learning_session.path_id:
        raise HTTPException(status_code=409, detail="Activity is not part of this session")
    choices = {item["id"]: item for item in activity.choices or []}
    selected = choices.get(payload.selected_choice_id)
    if selected is None:
        raise HTTPException(status_code=422, detail="Activity choice is not valid")
    correct = choices.get(activity.answer_key)
    if correct is None:
        raise HTTPException(status_code=409, detail="Activity answer key is invalid")
    is_correct = payload.selected_choice_id == activity.answer_key
    score_delta = 0.12 if is_correct else -0.08
    feedback = {
        "message": "정답입니다. 코드 근거와 실행 흐름이 일치합니다."
        if is_correct
        else "선택한 답과 실제 코드 근거가 다릅니다.",
        "explanation": activity.explanation,
        "selected_label": selected["label"],
        "correct_label": correct["label"],
    }
    attempt = ActivityAttempt(
        learning_session_id=learning_session.id,
        activity_id=activity.id,
        selected_choice_id=payload.selected_choice_id,
        is_correct=is_correct,
        score_delta=score_delta,
        feedback=feedback,
    )
    db.add(attempt)
    db.flush()
    updates = apply_mastery_event(
        db,
        profile=learning_session.profile,
        learning_session_id=learning_session.id,
        concept_ids=list(activity.concept_ids or []),
        event_type="activity_correct" if is_correct else "activity_incorrect",
        source_type="activity_attempt",
        source_id=attempt.id,
        score_delta=score_delta,
        confidence_delta=0.15 if is_correct else 0.12,
        evidence=activity.evidence or {},
    )
    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type="activity_correct" if is_correct else "activity_incorrect",
            module_id=activity.step.lesson.module_id,
            lesson_id=activity.step.lesson_id,
            step_id=activity.step_id,
            payload={
                "activity_id": activity.id,
                "attempt_id": attempt.id,
                "selected_choice_id": payload.selected_choice_id,
            },
        )
    )
    db.commit()
    return ActivityAttemptResponse(
        id=attempt.id,
        activity_id=activity.id,
        learning_session_id=learning_session.id,
        selected_choice_id=attempt.selected_choice_id,
        correct_choice_id=activity.answer_key,
        is_correct=attempt.is_correct,
        score_delta=attempt.score_delta,
        feedback=attempt.feedback,
        evidence=_activity_citation(activity),
        mastery_updates=[item.payload() for item in updates],
        created_at=attempt.created_at,
    )


@router.get(
    "/learner-profiles/{profile_id}/mastery-events",
    response_model=list[MasteryEventResponse],
)
def get_mastery_events(
    profile_id: str,
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    if db.get(LearnerProfile, profile_id) is None:
        raise HTTPException(status_code=404, detail="Learner profile not found")
    return db.scalars(
        select(MasteryEvent)
        .where(MasteryEvent.learner_profile_id == profile_id)
        .order_by(MasteryEvent.created_at.desc())
        .limit(limit)
    ).all()


@router.get(
    "/learner-profiles/{profile_id}/mastery-overview",
    response_model=MasteryOverviewResponse,
)
def get_mastery_overview(profile_id: str, db: SessionDep):
    profile = db.get(LearnerProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Learner profile not found")
    overview = build_mastery_overview(db, profile)
    db.commit()
    return overview


@router.get(
    "/learning-steps/{step_id}/explanations",
    response_model=LineExplanationResponse,
)
def get_line_explanation(
    step_id: str,
    db: SessionDep,
    auth: AuthDep,
    depth: Annotated[str, Query(pattern="^(beginner|standard|advanced)$")] = "beginner",
):
    settings = get_settings()
    usage: dict[str, int] = {}

    def record(provider_response, *, embedding: bool = False) -> None:
        measured = extract_usage(provider_response, embedding=embedding).as_dict()
        for key, value in measured.items():
            usage[key] = usage.get(key, 0) + value

    context = (
        UsageContext(
            organization_id=auth.organization_id,
            user_id=auth.user_id,
            feature="deep_explanation",
            request_id=f"line-explanation:{step_id}:{depth}",
            idempotency_key=f"line-explanation:{step_id}:{depth}",
        )
        if auth.authenticated
        else None
    )
    reservation = (
        UsageService(settings).reserve(
            db,
            context=context,
            estimated_cost_micro_usd=settings.chat_generation_reservation_micro_usd,
        )
        if context
        else None
    )
    try:
        artifact, step, file, mode = get_or_create_line_explanation(
            db,
            step_id=step_id,
            depth_band=depth,
            settings=settings,
            recorder=record,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        if reservation is not None:
            UsageService(settings).release(db, reservation.id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if context and mode == "openai":
        UsageService(settings).settle(
            db,
            reservation_id=reservation.id if reservation else None,
            context=context,
            provider="openai",
            model=settings.generation_model,
            usage=usage,
        )
    elif reservation is not None:
        UsageService(settings).release(db, reservation.id)
    return LineExplanationResponse(
        artifact_id=artifact.id,
        step_id=step.id,
        file_id=file.id,
        path=file.path,
        segments=artifact.segments,
        generation_mode=mode,
    )


@router.get(
    "/learning-steps/{step_id}/sources",
    response_model=list[LearningSourceResponse],
)
def get_learning_sources(
    step_id: str,
    db: SessionDep,
    learner_profile_id: str | None = None,
):
    step = db.scalar(
        select(LearningStep)
        .where(LearningStep.id == step_id)
        .options(selectinload(LearningStep.lesson))
    )
    if step is None:
        raise HTTPException(status_code=404, detail="Learning step not found")
    profile = db.get(LearnerProfile, learner_profile_id) if learner_profile_id else None
    concepts = _concepts_for_step(step)
    sources = recommended_sources(db, concepts, profile)
    db.flush()
    result = [
        LearningSourceResponse(
            id=source.id,
            concept_id=source.concept_id,
            title=source.title,
            publisher=source.publisher,
            canonical_url=source.canonical_url,
            source_tier=source.source_tier,
            difficulty=source.difficulty,
            language=source.language,
            estimated_minutes=source.estimated_minutes,
            recommendation_reason=(
                f"현재 학습 단계의 {source.concept_id.replace('_', ' ')} 개념을 보충합니다."
            ),
        )
        for source in sources
    ]
    db.commit()
    return result


@router.post(
    "/learning-sessions/{session_id}/remediation",
    response_model=RemediationBranchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_remediation(session_id: str, payload: RemediationCreate, db: SessionDep):
    learning_session = _load_learning_session(db, session_id)
    lesson = db.scalar(
        select(LearningLesson)
        .join(LearningModule, LearningLesson.module_id == LearningModule.id)
        .where(
            LearningLesson.id == payload.lesson_id,
            LearningModule.path_id == learning_session.path_id,
        )
        .options(selectinload(LearningLesson.steps))
    )
    if lesson is None:
        raise HTTPException(status_code=409, detail="Lesson is not part of this session")
    step = next((item for item in lesson.steps if item.id == payload.step_id), None)
    if payload.step_id and step is None:
        raise HTTPException(status_code=409, detail="Step is not part of this lesson")
    step = step or (lesson.steps[0] if lesson.steps else None)
    concepts = _concepts_for_step(step) if step else list(lesson.required_concept_ids or [])
    concepts = concepts or ["function", "variable"]
    gap_resolution: list[dict] = []
    branch_concepts = concepts
    if payload.mode == "prerequisite":
        gaps = resolve_concept_gaps(
            db,
            profile=learning_session.profile,
            required_concept_ids=concepts,
        )
        gap_resolution = [item.payload() for item in gaps]
        branch_concepts = [item.concept_id for item in gaps] or concepts[:1]
    content = _remediation_content(
        db,
        payload.mode,
        step,
        branch_concepts,
        learning_session,
        gap_resolution=gap_resolution,
    )
    branch = RemediationBranch(
        learning_session_id=learning_session.id,
        source_lesson_id=lesson.id,
        source_step_id=step.id if step else None,
        mode=payload.mode,
        concept_ids=branch_concepts,
        content=content,
        return_lesson_id=learning_session.current_lesson_id or lesson.id,
        return_step_id=learning_session.current_step_id,
    )
    db.add(branch)
    db.flush()
    learning_session.return_stack = [
        *(learning_session.return_stack or []),
        {
            "branch_id": branch.id,
            "lesson_id": branch.return_lesson_id,
            "step_id": branch.return_step_id,
        },
    ]
    learning_session.teaching_state = {
        **(learning_session.teaching_state or {}),
        "active_remediation_id": branch.id,
        "help_requested": False,
    }
    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type="remediation_started",
            module_id=learning_session.current_module_id,
            lesson_id=lesson.id,
            step_id=step.id if step else None,
            payload={
                "branch_id": branch.id,
                "mode": payload.mode,
                "concept_ids": branch_concepts,
                "gap_resolution": gap_resolution,
            },
        )
    )
    _sync_chat_session(db, learning_session)
    db.commit()
    db.refresh(branch)
    return _branch_response(branch)


@router.post(
    "/remediation-branches/{branch_id}/complete",
    response_model=RemediationBranchResponse,
)
def complete_remediation(branch_id: str, db: SessionDep):
    branch = db.get(RemediationBranch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Remediation branch not found")
    if branch.status != "completed":
        branch.status = "completed"
        branch.completed_at = utc_now()
        learning_session = _load_learning_session(db, branch.learning_session_id)
        learning_session.return_stack = [
            item
            for item in (learning_session.return_stack or [])
            if item.get("branch_id") != branch.id
        ]
        learning_session.teaching_state = {
            **(learning_session.teaching_state or {}),
            "active_remediation_id": None,
        }
        db.add(
            JourneyEvent(
                learning_session_id=learning_session.id,
                event_type="remediation_completed",
                module_id=learning_session.current_module_id,
                lesson_id=branch.source_lesson_id,
                step_id=branch.source_step_id,
                payload={"branch_id": branch.id, "mode": branch.mode},
            )
        )
        _sync_chat_session(db, learning_session)
        db.commit()
    return _branch_response(branch)


def _load_path(db: Session, path_id: str) -> LearningPath:
    path = db.scalar(
        select(LearningPath)
        .where(LearningPath.id == path_id)
        .options(
            selectinload(LearningPath.modules)
            .selectinload(LearningModule.lessons)
            .selectinload(LearningLesson.steps)
            .selectinload(LearningStep.chunk)
        )
    )
    if path is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    return path


def _load_learning_session(db: Session, session_id: str) -> LearningSession:
    learning_session = db.scalar(
        select(LearningSession)
        .where(LearningSession.id == session_id)
        .options(selectinload(LearningSession.profile))
    )
    if learning_session is None:
        raise HTTPException(status_code=404, detail="Learning session not found")
    return learning_session


def _path_response(db: Session, path_id: str) -> LearningPathResponse:
    path = _load_path(db, path_id)
    file_ids = {
        step.chunk.file_id
        for module in path.modules
        for lesson in module.lessons
        for step in lesson.steps
        if step.chunk is not None
    }
    files = db.scalars(select(FileRecord).where(FileRecord.id.in_(file_ids))).all()
    files_by_id = {file.id: file for file in files}
    modules: list[LearningModuleResponse] = []
    total_lessons = 0
    for module in path.modules:
        lessons: list[LearningLessonResponse] = []
        for lesson in module.lessons:
            steps = [
                _step_response(step, files_by_id.get(step.chunk.file_id) if step.chunk else None)
                for step in lesson.steps
            ]
            lessons.append(
                LearningLessonResponse(
                    id=lesson.id,
                    ordinal=lesson.ordinal,
                    lesson_type=lesson.lesson_type,
                    title=lesson.title,
                    objective=lesson.objective,
                    required_concept_ids=list(lesson.required_concept_ids or []),
                    checkpoint=lesson.checkpoint or {},
                    estimated_minutes=lesson.estimated_minutes,
                    optional=lesson.optional,
                    steps=steps,
                )
            )
        total_lessons += len(lessons)
        modules.append(
            LearningModuleResponse(
                id=module.id,
                ordinal=module.ordinal,
                module_type=module.module_type,
                title=module.title,
                objective=module.objective,
                required=module.required,
                estimated_minutes=module.estimated_minutes,
                coverage_keys=list(module.coverage_keys or []),
                lessons=lessons,
            )
        )
    return LearningPathResponse(
        id=path.id,
        snapshot_id=path.snapshot_id,
        learner_profile_id=path.learner_profile_id,
        title=path.title,
        goal=path.goal,
        status=path.status,
        path_version=path.path_version,
        generation_method=path.generation_method,
        coverage=path.coverage or {},
        model_metadata=path.model_metadata or {},
        estimated_minutes=path.estimated_minutes,
        total_modules=len(modules),
        total_lessons=total_lessons,
        modules=modules,
        created_at=path.created_at,
        updated_at=path.updated_at,
    )


def _step_response(step: LearningStep, file: FileRecord | None) -> LearningStepResponse:
    evidence = None
    chunk = step.chunk
    if chunk is not None:
        if file is None or not _chunk_matches_file(chunk, file):
            raise HTTPException(status_code=409, detail="Learning path evidence is stale")
        evidence = CitationResponse(
            evidence_id=evidence_id_for_chunk(chunk.id),
            snapshot_id=chunk.snapshot_id,
            file_id=file.id,
            path=file.path,
            language=file.language,
            title=chunk.title,
            chunk_type=chunk.chunk_type,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            preview=_preview(chunk.content),
            score=1.0,
            retrievers=["adaptive_curriculum"],
        )
    return LearningStepResponse(
        id=step.id,
        ordinal=step.ordinal,
        step_type=step.step_type,
        title=step.title,
        instruction=step.instruction,
        concept_id=step.concept_id,
        evidence=evidence,
        metadata=step.metadata_json or {},
    )


def _ordered_lessons(path: LearningPath) -> list[tuple[LearningModule, LearningLesson]]:
    return [
        (module, lesson)
        for module in sorted(path.modules, key=lambda item: item.ordinal)
        for lesson in sorted(module.lessons, key=lambda item: item.ordinal)
    ]


def _next_unfinished(
    ordered: list[tuple[LearningModule, LearningLesson]],
    lesson_id: str,
    completed: set[str],
) -> tuple[LearningModule, LearningLesson] | None:
    current_index = next(
        (index for index, (_, lesson) in enumerate(ordered) if lesson.id == lesson_id),
        -1,
    )
    candidates = [*ordered[current_index + 1 :], *ordered[: current_index + 1]]
    return next((item for item in candidates if item[1].id not in completed), None)


def _move_to_lesson(
    db: Session,
    learning_session: LearningSession,
    module: LearningModule,
    lesson: LearningLesson,
    step: LearningStep | None,
) -> None:
    learning_session.current_module_id = module.id
    learning_session.current_lesson_id = lesson.id
    learning_session.current_step_id = step.id if step else None
    learning_session.current_selection = _selection_for_step(db, step)
    learning_session.focus_concept_ids = list(lesson.required_concept_ids or [])
    learning_session.teaching_state = _teaching_state(module, lesson, step)


def _teaching_state(
    module: LearningModule, lesson: LearningLesson, step: LearningStep | None
) -> dict:
    return {
        "module_title": module.title,
        "lesson_title": lesson.title,
        "objective": lesson.objective,
        "checkpoint": lesson.checkpoint or {},
        "step_instruction": step.instruction if step else None,
        "concept_ids": list(lesson.required_concept_ids or []),
        "help_requested": False,
    }


def _selection_for_step(db: Session, step: LearningStep | None) -> dict:
    if step is None or step.chunk is None:
        return {}
    chunk = step.chunk
    file = db.get(FileRecord, chunk.file_id)
    if file is None or not _chunk_matches_file(chunk, file):
        return {}
    return {
        "file_id": file.id,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }


def _validated_selection(db: Session, snapshot_id: str, selection: dict) -> dict:
    if not selection:
        return {}
    file = db.scalar(
        select(FileRecord).where(
            FileRecord.id == selection.get("file_id"),
            FileRecord.snapshot_id == snapshot_id,
        )
    )
    if file is None:
        raise HTTPException(status_code=422, detail="Selected file is not in this snapshot")
    start_line = int(selection.get("start_line", 0))
    end_line = int(selection.get("end_line", 0))
    if start_line < 1 or start_line > end_line or end_line > file.line_count:
        raise HTTPException(status_code=422, detail="Selected line range is invalid")
    return {"file_id": file.id, "start_line": start_line, "end_line": end_line}


def _sync_chat_session(db: Session, learning_session: LearningSession) -> None:
    chat = db.scalar(
        select(ChatSession).where(ChatSession.learning_session_id == learning_session.id)
    )
    if chat is not None:
        chat.current_selection = learning_session.current_selection or {}
        chat.teaching_state = learning_session.teaching_state or {}


def _session_response(db: Session, learning_session: LearningSession) -> LearningSessionResponse:
    chat_id = db.scalar(
        select(ChatSession.id).where(ChatSession.learning_session_id == learning_session.id)
    )
    if chat_id is None:
        raise HTTPException(status_code=409, detail="Learning session has no linked chat")
    total_lessons = (
        db.scalar(
            select(func.count(LearningLesson.id))
            .join(LearningModule, LearningLesson.module_id == LearningModule.id)
            .where(LearningModule.path_id == learning_session.path_id)
        )
        or 0
    )
    completed = list(learning_session.completed_lesson_ids or [])
    return LearningSessionResponse(
        id=learning_session.id,
        snapshot_id=learning_session.snapshot_id,
        learner_profile_id=learning_session.learner_profile_id,
        path_id=learning_session.path_id,
        chat_session_id=chat_id,
        current_module_id=learning_session.current_module_id,
        current_lesson_id=learning_session.current_lesson_id,
        current_step_id=learning_session.current_step_id,
        completed_lesson_ids=completed,
        return_stack=list(learning_session.return_stack or []),
        current_selection=learning_session.current_selection or {},
        focus_concept_ids=list(learning_session.focus_concept_ids or []),
        status=learning_session.status,
        completed_count=len(completed),
        total_lessons=total_lessons,
        created_at=learning_session.created_at,
        updated_at=learning_session.updated_at,
    )


def _concepts_for_step(step: LearningStep) -> list[str]:
    metadata = step.metadata_json or {}
    return list(
        dict.fromkeys(
            [
                *(metadata.get("concept_ids") or []),
                *(step.lesson.required_concept_ids or []),
                *([step.concept_id] if step.concept_id else []),
            ]
        )
    )


def _remediation_content(
    db: Session,
    mode: str,
    step: LearningStep | None,
    concepts: list[str],
    learning_session: LearningSession,
    *,
    gap_resolution: list[dict] | None = None,
) -> dict:
    if mode == "line_by_line":
        if step is None:
            raise HTTPException(status_code=409, detail="This lesson has no code to explain")
        artifact, _, file, generation_mode = get_or_create_line_explanation(
            db,
            step_id=step.id,
            depth_band="beginner",
            settings=get_settings(),
        )
        return {
            "type": "line_by_line",
            "path": file.path,
            "file_id": file.id,
            "generation_mode": generation_mode,
            "segments": artifact.segments,
        }
    if mode == "prerequisite":
        sources = recommended_sources(db, concepts, learning_session.profile, limit=4)
        db.flush()
        return {
            "type": "prerequisite",
            "concepts": concept_bridge(concepts),
            "gap_resolution": gap_resolution or [],
            "sources": [_source_dict(item) for item in sources],
        }
    if mode == "small_example":
        return {"type": "small_example", "examples": small_examples(concepts)}
    sources = recommended_sources(db, concepts, learning_session.profile)
    db.flush()
    return {
        "type": "learning_sources",
        "sources": [_source_dict(item) for item in sources],
    }


def _source_dict(source) -> dict:
    return {
        "id": source.id,
        "concept_id": source.concept_id,
        "title": source.title,
        "publisher": source.publisher,
        "canonical_url": source.canonical_url,
        "source_tier": source.source_tier,
        "difficulty": source.difficulty,
        "language": source.language,
        "estimated_minutes": source.estimated_minutes,
    }


def _activity_response(
    activity: LearningActivity, latest: ActivityAttempt | None
) -> LearningActivityResponse:
    return LearningActivityResponse(
        id=activity.id,
        step_id=activity.step_id,
        activity_type=activity.activity_type,
        prompt=activity.prompt,
        choices=list(activity.choices or []),
        concept_ids=list(activity.concept_ids or []),
        evidence=_activity_citation(activity),
        generator_version=activity.generator_version,
        latest_attempt=(
            ActivityAttemptSummary(
                id=latest.id,
                selected_choice_id=latest.selected_choice_id,
                is_correct=latest.is_correct,
                score_delta=latest.score_delta,
                feedback=latest.feedback or {},
                created_at=latest.created_at,
            )
            if latest
            else None
        ),
    )


def _activity_citation(activity: LearningActivity) -> CitationResponse:
    evidence = activity.evidence or {}
    return CitationResponse(
        evidence_id=evidence["evidence_id"],
        snapshot_id=evidence["snapshot_id"],
        file_id=evidence["file_id"],
        path=evidence["path"],
        language=evidence["language"],
        title=evidence["title"],
        chunk_type=evidence["chunk_type"],
        start_line=evidence["start_line"],
        end_line=evidence["end_line"],
        preview=evidence["preview"],
        score=1.0,
        retrievers=["learning_activity"],
    )


def _branch_response(branch: RemediationBranch) -> RemediationBranchResponse:
    return RemediationBranchResponse.model_validate(
        {
            "id": branch.id,
            "learning_session_id": branch.learning_session_id,
            "source_lesson_id": branch.source_lesson_id,
            "source_step_id": branch.source_step_id,
            "mode": branch.mode,
            "status": branch.status,
            "concept_ids": list(branch.concept_ids or []),
            "content": branch.content or {},
            "return_lesson_id": branch.return_lesson_id,
            "return_step_id": branch.return_step_id,
            "created_at": branch.created_at,
            "completed_at": branch.completed_at,
        }
    )


def _chunk_matches_file(chunk: CodeChunk, file: FileRecord) -> bool:
    if chunk.start_line < 1 or chunk.end_line > file.line_count:
        return False
    source = "\n".join(file.content.splitlines()[chunk.start_line - 1 : chunk.end_line])
    return source == chunk.content


def _preview(content: str, limit: int = 320) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    return compact if len(compact) <= limit else f"{compact[: limit - 3].rstrip()}..."
