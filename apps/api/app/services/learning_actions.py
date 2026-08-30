from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.learning.mastery import apply_mastery_event
from app.models import (
    ActivityAttempt,
    ChatSession,
    FileRecord,
    JourneyEvent,
    LearningActivity,
    LearningLesson,
    LearningModule,
    LearningPath,
    LearningSession,
    LearningStep,
    RemediationBranch,
    utc_now,
)


def apply_learning_action(
    db: Session,
    *,
    session_id: str,
    action: str,
    lesson_id: str | None = None,
    choice_id: str | None = None,
    source: str = "voice",
) -> dict:
    learning_session = _load_session(db, session_id)
    path = learning_session.path
    ordered = _ordered_lessons(path)
    current_index = next(
        (
            index
            for index, (_, lesson) in enumerate(ordered)
            if lesson.id == (lesson_id or learning_session.current_lesson_id)
        ),
        -1,
    )
    if current_index < 0:
        raise ValueError("Learning session has no current lesson")
    module, lesson = ordered[current_index]
    step = lesson.steps[0] if lesson.steps else None

    if action in {"opened", "understood", "needs_help", "skip"}:
        _apply_feedback(
            db,
            learning_session=learning_session,
            ordered=ordered,
            module=module,
            lesson=lesson,
            step=step,
            event_type=action,
            source=source,
        )
    elif action == "next":
        if current_index + 1 >= len(ordered):
            raise ValueError("There is no next lesson")
        next_module, next_lesson = ordered[current_index + 1]
        _move_to_lesson(
            db,
            learning_session,
            next_module,
            next_lesson,
            next_lesson.steps[0] if next_lesson.steps else None,
        )
        _event(db, learning_session, "next", source=source)
    elif action == "previous":
        if current_index == 0:
            raise ValueError("There is no previous lesson")
        previous_module, previous_lesson = ordered[current_index - 1]
        _move_to_lesson(
            db,
            learning_session,
            previous_module,
            previous_lesson,
            previous_lesson.steps[0] if previous_lesson.steps else None,
        )
        _event(db, learning_session, "previous", source=source)
    elif action == "return":
        branch = db.scalar(
            select(RemediationBranch)
            .where(
                RemediationBranch.learning_session_id == learning_session.id,
                RemediationBranch.status == "active",
            )
            .order_by(RemediationBranch.created_at.desc())
            .limit(1)
        )
        if branch is None:
            raise ValueError("There is no remediation to return from")
        branch.status = "completed"
        branch.completed_at = utc_now()
        learning_session.return_stack = [
            item
            for item in (learning_session.return_stack or [])
            if item.get("branch_id") != branch.id
        ]
        learning_session.teaching_state = {
            **(learning_session.teaching_state or {}),
            "active_remediation_id": None,
        }
        _event(
            db,
            learning_session,
            "remediation_completed",
            source=source,
            payload={"branch_id": branch.id, "mode": branch.mode},
        )
    elif action == "submit_choice":
        if not choice_id:
            raise ValueError("A checkpoint choice is required")
        _submit_current_choice(
            db,
            learning_session=learning_session,
            choice_id=choice_id,
            source=source,
        )
    else:
        raise ValueError(f"Unsupported learning action: {action}")

    _sync_chat(db, learning_session)
    db.flush()
    return {
        "status": "applied",
        "action": action,
        "learning_session_id": learning_session.id,
        "current_lesson_id": learning_session.current_lesson_id,
        "completed_lesson_ids": list(learning_session.completed_lesson_ids or []),
    }


def command_context_state(db: Session, *, session_id: str) -> dict:
    learning_session = _load_session(db, session_id)
    ordered = _ordered_lessons(learning_session.path)
    current_index = next(
        (
            index
            for index, (_, lesson) in enumerate(ordered)
            if lesson.id == learning_session.current_lesson_id
        ),
        -1,
    )
    activity = db.scalar(
        select(LearningActivity)
        .where(LearningActivity.step_id == learning_session.current_step_id)
        .order_by(LearningActivity.created_at.desc())
        .limit(1)
    )
    choices = list(activity.choices or []) if activity is not None else []
    has_return = (
        db.scalar(
            select(RemediationBranch.id)
            .where(
                RemediationBranch.learning_session_id == learning_session.id,
                RemediationBranch.status == "active",
            )
            .limit(1)
        )
        is not None
    )
    return {
        "has_current_lesson": current_index >= 0,
        "has_previous_lesson": current_index > 0,
        "has_return_target": has_return,
        "choice_ids": tuple(str(item["id"]) for item in choices),
        "choice_labels": {str(item["id"]): str(item.get("label", "")) for item in choices},
    }


def _apply_feedback(
    db: Session,
    *,
    learning_session: LearningSession,
    ordered: list[tuple[LearningModule, LearningLesson]],
    module: LearningModule,
    lesson: LearningLesson,
    step: LearningStep | None,
    event_type: str,
    source: str,
) -> None:
    if event_type == "opened":
        _move_to_lesson(db, learning_session, module, lesson, step)
    elif event_type == "needs_help":
        _move_to_lesson(db, learning_session, module, lesson, step)
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
    else:
        completed = list(learning_session.completed_lesson_ids or [])
        if lesson.id not in completed:
            completed.append(lesson.id)
        learning_session.completed_lesson_ids = completed
        if event_type == "understood":
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
            _move_to_lesson(
                db,
                learning_session,
                next_module,
                next_lesson,
                next_lesson.steps[0] if next_lesson.steps else None,
            )
    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type=event_type,
            module_id=module.id,
            lesson_id=lesson.id,
            step_id=step.id if step else None,
            payload={"source": source},
        )
    )


def _submit_current_choice(
    db: Session,
    *,
    learning_session: LearningSession,
    choice_id: str,
    source: str,
) -> None:
    activity = db.scalar(
        select(LearningActivity)
        .where(LearningActivity.step_id == learning_session.current_step_id)
        .options(
            selectinload(LearningActivity.step)
            .selectinload(LearningStep.lesson)
            .selectinload(LearningLesson.module)
        )
        .order_by(LearningActivity.created_at.desc())
        .limit(1)
    )
    if activity is None:
        raise ValueError("There is no active checkpoint")
    choices = {str(item["id"]): item for item in (activity.choices or [])}
    if choice_id not in choices:
        raise ValueError("Checkpoint choice is not valid")
    if activity.answer_key not in choices:
        raise ValueError("Checkpoint answer key is invalid")
    is_correct = choice_id == activity.answer_key
    score_delta = 0.12 if is_correct else -0.08
    attempt = ActivityAttempt(
        learning_session_id=learning_session.id,
        activity_id=activity.id,
        selected_choice_id=choice_id,
        is_correct=is_correct,
        score_delta=score_delta,
        feedback={
            "message": (
                "정답입니다. 코드 근거와 실행 흐름이 일치합니다."
                if is_correct
                else "선택한 답과 실제 코드 근거가 다릅니다."
            ),
            "explanation": activity.explanation,
            "selected_label": choices[choice_id]["label"],
            "correct_label": choices[activity.answer_key]["label"],
        },
    )
    db.add(attempt)
    db.flush()
    apply_mastery_event(
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
    _event(
        db,
        learning_session,
        "activity_correct" if is_correct else "activity_incorrect",
        source=source,
        payload={
            "activity_id": activity.id,
            "attempt_id": attempt.id,
            "selected_choice_id": choice_id,
        },
    )


def _load_session(db: Session, session_id: str) -> LearningSession:
    learning_session = db.scalar(
        select(LearningSession)
        .where(LearningSession.id == session_id)
        .options(
            selectinload(LearningSession.profile),
            selectinload(LearningSession.path)
            .selectinload(LearningPath.modules)
            .selectinload(LearningModule.lessons)
            .selectinload(LearningLesson.steps)
            .selectinload(LearningStep.chunk),
        )
    )
    if learning_session is None:
        raise ValueError("Learning session not found")
    return learning_session


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
    learning_session.focus_concept_ids = list(lesson.required_concept_ids or [])
    learning_session.teaching_state = {
        "module_title": module.title,
        "lesson_title": lesson.title,
        "objective": lesson.objective,
        "checkpoint": lesson.checkpoint or {},
        "step_instruction": step.instruction if step else None,
        "concept_ids": list(lesson.required_concept_ids or []),
        "help_requested": False,
    }
    if step is None or step.chunk is None:
        learning_session.current_selection = {}
        return
    file = db.get(FileRecord, step.chunk.file_id)
    learning_session.current_selection = (
        {
            "file_id": file.id,
            "start_line": step.chunk.start_line,
            "end_line": step.chunk.end_line,
        }
        if file is not None
        else {}
    )


def _sync_chat(db: Session, learning_session: LearningSession) -> None:
    chat = db.scalar(
        select(ChatSession).where(ChatSession.learning_session_id == learning_session.id)
    )
    if chat is not None:
        chat.current_selection = learning_session.current_selection or {}
        chat.teaching_state = learning_session.teaching_state or {}


def _event(
    db: Session,
    learning_session: LearningSession,
    event_type: str,
    *,
    source: str,
    payload: dict | None = None,
) -> None:
    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type=event_type,
            module_id=learning_session.current_module_id,
            lesson_id=learning_session.current_lesson_id,
            step_id=learning_session.current_step_id,
            payload={"source": source, **(payload or {})},
        )
    )
