from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.assessment.question_bank import (
    ASSESSMENT_VERSION,
    merge_questions_for_stack,
    question_by_id,
    questions_for_stack,
)
from app.assessment.scoring import project_profile, score_response
from app.core.auth import AuthContext, AuthDep
from app.core.db import get_db
from app.learning.mastery import apply_mastery_projection
from app.models import (
    AssessmentResponse,
    AssessmentSession,
    FileRecord,
    LearnerProfile,
    RepositorySnapshot,
    utc_now,
)
from app.schemas import (
    AssessmentAnswerCreate,
    AssessmentQuestionResponse,
    AssessmentSessionCreate,
    AssessmentSessionResponse,
    LearnerProfileCreate,
    LearnerProfileResponse,
)

router = APIRouter(tags=["assessment"])
SessionDep = Annotated[Session, Depends(get_db)]


def _create_learner_profile(
    payload: LearnerProfileCreate,
    db: Session,
    auth: AuthContext | None,
) -> LearnerProfile:
    profile = db.scalar(
        select(LearnerProfile).where(LearnerProfile.anonymous_key == payload.anonymous_key)
    )
    if profile is not None and auth is not None and auth.authenticated:
        if profile.user_id not in {None, auth.user_id}:
            raise HTTPException(status_code=409, detail={"code": "anonymous_profile_claimed"})
        if profile.organization_id not in {None, auth.organization_id}:
            raise HTTPException(status_code=409, detail={"code": "anonymous_profile_claimed"})
        profile.user_id = auth.user_id
        profile.organization_id = auth.organization_id
        db.commit()
        db.refresh(profile)
    elif profile is None:
        profile = LearnerProfile(
            anonymous_key=payload.anonymous_key,
            user_id=auth.user_id if auth and auth.authenticated else None,
            organization_id=auth.organization_id if auth and auth.authenticated else None,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def create_learner_profile(payload: LearnerProfileCreate, db: SessionDep):
    """Legacy internal helper; HTTP callers use the authenticated endpoint below."""
    return _create_learner_profile(payload, db, None)


@router.post(
    "/learner-profiles",
    response_model=LearnerProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_learner_profile_endpoint(payload: LearnerProfileCreate, db: SessionDep, auth: AuthDep):
    return _create_learner_profile(payload, db, auth)


@router.get("/learner-profiles/{profile_id}", response_model=LearnerProfileResponse)
def get_learner_profile(profile_id: str, db: SessionDep):
    profile = db.get(LearnerProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Learner profile not found")
    return profile


@router.post(
    "/snapshots/{snapshot_id}/assessment-sessions",
    response_model=AssessmentSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment_session(snapshot_id: str, payload: AssessmentSessionCreate, db: SessionDep):
    snapshot = db.get(RepositorySnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    profile = db.get(LearnerProfile, payload.learner_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Learner profile not found")

    assessment = db.scalar(
        select(AssessmentSession)
        .where(
            AssessmentSession.snapshot_id == snapshot_id,
            AssessmentSession.learner_profile_id == profile.id,
            AssessmentSession.assessment_version == ASSESSMENT_VERSION,
        )
        .options(selectinload(AssessmentSession.responses))
    )
    if assessment is None:
        stack = _detect_stack(db, snapshot_id)
        assessment = AssessmentSession(
            snapshot_id=snapshot_id,
            learner_profile_id=profile.id,
            detected_stack=stack,
            questions=[item.stored_payload() for item in questions_for_stack(stack)],
            assessment_version=ASSESSMENT_VERSION,
        )
        db.add(assessment)
        db.commit()
        db.refresh(assessment)
        assessment.responses = []
    elif _refresh_assessment(db, assessment):
        db.commit()
    return _assessment_response(assessment, profile)


@router.get("/assessment-sessions/{assessment_id}", response_model=AssessmentSessionResponse)
def get_assessment_session(assessment_id: str, db: SessionDep):
    assessment = _load_assessment(db, assessment_id)
    if _refresh_assessment(db, assessment):
        db.commit()
    return _assessment_response(assessment, assessment.profile)


@router.post(
    "/assessment-sessions/{assessment_id}/responses",
    response_model=AssessmentSessionResponse,
)
def answer_assessment(assessment_id: str, payload: AssessmentAnswerCreate, db: SessionDep):
    assessment = _load_assessment(db, assessment_id)
    if assessment.status != "active":
        raise HTTPException(status_code=409, detail="Assessment is already finished")
    _refresh_assessment(db, assessment)
    question = question_by_id(assessment.questions, payload.item_id)
    if question is None:
        raise HTTPException(status_code=422, detail="Assessment item not found")
    allowed_answers = {choice["value"] for choice in question.get("choices", [])}
    if payload.answer not in allowed_answers:
        raise HTTPException(status_code=422, detail="Answer is not valid for this item")
    scored = score_response(question, payload.answer)
    response = next(
        (item for item in assessment.responses if item.item_id == payload.item_id), None
    )
    if response is None:
        response = AssessmentResponse(
            assessment_session_id=assessment.id,
            item_id=payload.item_id,
            answer=payload.answer,
            is_correct=scored.is_correct,
            score_delta=scored.score,
            confidence=scored.confidence,
        )
        db.add(response)
        assessment.responses.append(response)
    else:
        response.answer = payload.answer
        response.is_correct = scored.is_correct
        response.score_delta = scored.score
        response.confidence = scored.confidence
    db.commit()
    return _assessment_response(assessment, assessment.profile)


@router.post(
    "/assessment-sessions/{assessment_id}/submit",
    response_model=AssessmentSessionResponse,
)
def submit_assessment(assessment_id: str, db: SessionDep):
    assessment = _load_assessment(db, assessment_id)
    if assessment.status == "completed":
        return _assessment_response(assessment, assessment.profile)
    if assessment.status == "skipped":
        raise HTTPException(status_code=409, detail="Skipped assessment cannot be submitted")
    answers = {item.item_id: item.answer for item in assessment.responses}
    projection = project_profile(
        questions=assessment.questions,
        answers=answers,
        previous_mastery=assessment.profile.concept_mastery,
    )
    profile = assessment.profile
    profile.goal = projection["goal"]
    profile.preferred_explanation = projection["preferred_explanation"]
    profile.pace = projection["pace"]
    apply_mastery_projection(
        db,
        profile=profile,
        projected_mastery=projection["concept_mastery"],
        event_type="assessment_result",
        source_type="assessment",
        source_id=assessment.id,
        evidence={
            "assessment_version": ASSESSMENT_VERSION,
            "answered_item_ids": sorted(answers),
        },
    )
    profile.assessment_version = ASSESSMENT_VERSION
    assessment.status = "completed"
    assessment.submitted_at = utc_now()
    db.commit()
    return _assessment_response(assessment, profile)


@router.post(
    "/assessment-sessions/{assessment_id}/skip",
    response_model=AssessmentSessionResponse,
)
def skip_assessment(assessment_id: str, db: SessionDep):
    assessment = _load_assessment(db, assessment_id)
    if assessment.status == "completed":
        return _assessment_response(assessment, assessment.profile)
    assessment.status = "skipped"
    assessment.skipped_at = utc_now()
    profile = assessment.profile
    if not profile.preferred_explanation:
        profile.preferred_explanation = ["line_by_line"]
    db.commit()
    return _assessment_response(assessment, profile)


def _load_assessment(db: Session, assessment_id: str) -> AssessmentSession:
    assessment = db.scalar(
        select(AssessmentSession)
        .where(AssessmentSession.id == assessment_id)
        .options(
            selectinload(AssessmentSession.responses),
            selectinload(AssessmentSession.profile),
        )
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment session not found")
    return assessment


def _assessment_response(
    assessment: AssessmentSession, profile: LearnerProfile
) -> AssessmentSessionResponse:
    answers = {item.item_id: item.answer for item in assessment.responses}
    questions = [
        AssessmentQuestionResponse.model_validate(
            {key: value for key, value in item.items() if key != "answer_key"}
        )
        for item in assessment.questions
    ]
    return AssessmentSessionResponse(
        id=assessment.id,
        snapshot_id=assessment.snapshot_id,
        learner_profile_id=assessment.learner_profile_id,
        status=assessment.status,
        detected_stack=list(assessment.detected_stack or []),
        assessment_version=assessment.assessment_version,
        questions=questions,
        answers=answers,
        answered_count=len(answers),
        total_count=len(questions),
        created_at=assessment.created_at,
        submitted_at=assessment.submitted_at,
        skipped_at=assessment.skipped_at,
        profile=LearnerProfileResponse.model_validate(profile),
    )


def _detect_stack(db: Session, snapshot_id: str) -> list[str]:
    files = db.scalars(select(FileRecord).where(FileRecord.snapshot_id == snapshot_id)).all()
    if not files:
        return []
    languages = {item.language for item in files}
    stack: list[str] = []
    if languages & {"typescript", "tsx"}:
        stack.append("TypeScript")
    elif languages & {"javascript", "jsx"}:
        stack.append("JavaScript")
    package_file = next((item for item in files if item.path == "package.json"), None)
    if package_file:
        try:
            package = json.loads(package_file.content)
            dependencies = {
                **package.get("dependencies", {}),
                **package.get("devDependencies", {}),
            }
            if "react" in dependencies:
                stack.append("React")
            if "next" in dependencies:
                stack.append("Next.js")
        except json.JSONDecodeError:
            pass
    return stack


def _refresh_assessment(db: Session, assessment: AssessmentSession) -> bool:
    if assessment.status != "active":
        return False
    stack = _detect_stack(db, assessment.snapshot_id)
    questions = merge_questions_for_stack(assessment.questions or [], stack)
    changed = stack != list(assessment.detected_stack or []) or questions != list(
        assessment.questions or []
    )
    if changed:
        assessment.detected_stack = stack
        assessment.questions = questions
        db.flush()
    return changed
