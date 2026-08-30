from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext
from app.models import (
    AssessmentSession,
    ChatSession,
    DeepTask,
    GuidedPath,
    GuidedTourSession,
    LearnerProfile,
    LearningLesson,
    LearningModule,
    LearningPath,
    LearningSession,
    LearningStep,
    OrganizationMembership,
    OrganizationRepository,
    RemediationBranch,
    RepositorySnapshot,
    RoadmapProposal,
    VoiceSession,
)


def ensure_organization_access(
    db: Session,
    context: AuthContext,
    organization_id: str,
    *,
    roles: set[str] | None = None,
) -> None:
    if not context.authenticated:
        return
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == context.user_id,
            OrganizationMembership.status == "active",
        )
    )
    if membership is None or (roles is not None and membership.role not in roles):
        raise HTTPException(status_code=403, detail={"code": "organization_access_denied"})


def ensure_repository_access(db: Session, context: AuthContext, repository_id: str) -> None:
    if not context.authenticated:
        return
    allowed = db.scalar(
        select(OrganizationRepository.id).where(
            OrganizationRepository.organization_id == context.organization_id,
            OrganizationRepository.repository_id == repository_id,
        )
    )
    if allowed is None:
        raise HTTPException(status_code=404, detail="Repository not found")


def ensure_snapshot_access(db: Session, context: AuthContext, snapshot_id: str) -> None:
    if not context.authenticated:
        return
    repository_id = db.scalar(
        select(RepositorySnapshot.repository_id).where(RepositorySnapshot.id == snapshot_id)
    )
    if repository_id is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    ensure_repository_access(db, context, repository_id)


def ensure_chat_access(db: Session, context: AuthContext, session: ChatSession) -> None:
    if not context.authenticated:
        return
    if session.organization_id and session.organization_id != context.organization_id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.user_id and session.user_id != context.user_id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    ensure_snapshot_access(db, context, session.snapshot_id)


def ensure_learning_access(db: Session, context: AuthContext, session: LearningSession) -> None:
    if not context.authenticated:
        return
    profile = db.get(LearnerProfile, session.learner_profile_id)
    if profile is None or profile.organization_id != context.organization_id:
        raise HTTPException(status_code=404, detail="Learning session not found")
    if profile.user_id and profile.user_id != context.user_id:
        raise HTTPException(status_code=404, detail="Learning session not found")


def ensure_deep_task_access(db: Session, context: AuthContext, task: DeepTask) -> None:
    if not context.authenticated:
        return
    if task.organization_id != context.organization_id or (
        task.user_id is not None and task.user_id != context.user_id
    ):
        raise HTTPException(status_code=404, detail="Deep task not found")


def _not_found(resource: str) -> None:
    raise HTTPException(status_code=404, detail=f"{resource} not found")


def ensure_profile_access(db: Session, context: AuthContext, profile_id: str) -> None:
    if not context.authenticated:
        return
    profile = db.get(LearnerProfile, profile_id)
    if profile is None or profile.organization_id != context.organization_id:
        _not_found("Learner profile")
    if profile.user_id and profile.user_id != context.user_id:
        _not_found("Learner profile")


def ensure_learning_path_access(db: Session, context: AuthContext, path_id: str) -> None:
    path = db.get(LearningPath, path_id)
    if path is None:
        _not_found("Learning path")
    ensure_profile_access(db, context, path.learner_profile_id)
    ensure_snapshot_access(db, context, path.snapshot_id)


def ensure_assessment_access(db: Session, context: AuthContext, assessment_id: str) -> None:
    assessment = db.get(AssessmentSession, assessment_id)
    if assessment is None:
        _not_found("Assessment session")
    ensure_profile_access(db, context, assessment.learner_profile_id)
    ensure_snapshot_access(db, context, assessment.snapshot_id)


def ensure_guided_path_access(db: Session, context: AuthContext, path_id: str) -> None:
    path = db.get(GuidedPath, path_id)
    if path is None:
        _not_found("Guided path")
    ensure_snapshot_access(db, context, path.snapshot_id)


def ensure_guided_tour_access(db: Session, context: AuthContext, session_id: str) -> None:
    tour = db.get(GuidedTourSession, session_id)
    if tour is None:
        _not_found("Guided tour session")
    ensure_guided_path_access(db, context, tour.path_id)


def ensure_learning_step_access(db: Session, context: AuthContext, step_id: str) -> None:
    path_id = db.scalar(
        select(LearningModule.path_id)
        .join(LearningLesson, LearningLesson.module_id == LearningModule.id)
        .join(LearningStep, LearningStep.lesson_id == LearningLesson.id)
        .where(LearningStep.id == step_id)
    )
    if path_id is None:
        _not_found("Learning step")
    ensure_learning_path_access(db, context, path_id)


def ensure_remediation_access(db: Session, context: AuthContext, branch_id: str) -> None:
    branch = db.get(RemediationBranch, branch_id)
    if branch is None:
        _not_found("Remediation branch")
    session = db.get(LearningSession, branch.learning_session_id)
    if session is None:
        _not_found("Remediation branch")
    ensure_learning_access(db, context, session)


def ensure_voice_session_access(
    db: Session,
    context: AuthContext,
    voice_session_id: str,
) -> None:
    voice_session = db.get(VoiceSession, voice_session_id)
    if voice_session is None:
        _not_found("Voice session")
    session = db.get(LearningSession, voice_session.learning_session_id)
    if session is None:
        _not_found("Voice session")
    ensure_learning_access(db, context, session)


def ensure_roadmap_proposal_access(
    db: Session,
    context: AuthContext,
    proposal_id: str,
) -> None:
    proposal = db.get(RoadmapProposal, proposal_id)
    if proposal is None:
        _not_found("Roadmap proposal")
    session = db.get(LearningSession, proposal.learning_session_id)
    if session is None:
        _not_found("Roadmap proposal")
    ensure_learning_access(db, context, session)


def authorize_request_scope(request: Request, db: Session, context: AuthContext) -> None:
    """Authorize path-addressed resources before protected endpoint execution."""
    if not context.authenticated:
        return
    params = request.path_params
    path = request.url.path
    organization_id = params.get("organization_id")
    if organization_id:
        ensure_organization_access(db, context, organization_id)
    snapshot_id = params.get("snapshot_id")
    if snapshot_id:
        ensure_snapshot_access(db, context, snapshot_id)
    task_id = params.get("task_id")
    if task_id:
        task = db.get(DeepTask, task_id)
        if task is None:
            _not_found("Deep task")
        ensure_deep_task_access(db, context, task)
    profile_id = params.get("profile_id")
    if profile_id:
        ensure_profile_access(db, context, profile_id)
    assessment_id = params.get("assessment_id")
    if assessment_id:
        ensure_assessment_access(db, context, assessment_id)
    path_id = params.get("path_id")
    if path_id:
        if "/guided-paths/" in path:
            ensure_guided_path_access(db, context, path_id)
        else:
            ensure_learning_path_access(db, context, path_id)
    session_id = params.get("session_id")
    if session_id:
        if "/chat/sessions/" in path:
            session = db.get(ChatSession, session_id)
            if session is None:
                _not_found("Chat session")
            ensure_chat_access(db, context, session)
        elif "/guided-tour-sessions/" in path:
            ensure_guided_tour_access(db, context, session_id)
        elif "/learning-sessions/" in path:
            session = db.get(LearningSession, session_id)
            if session is None:
                _not_found("Learning session")
            ensure_learning_access(db, context, session)
    step_id = params.get("step_id")
    if step_id and "/learning-steps/" in path:
        ensure_learning_step_access(db, context, step_id)
    branch_id = params.get("branch_id")
    if branch_id:
        ensure_remediation_access(db, context, branch_id)
    proposal_id = params.get("proposal_id")
    if proposal_id:
        ensure_roadmap_proposal_access(db, context, proposal_id)
    voice_session_id = params.get("voice_session_id")
    if voice_session_id:
        ensure_voice_session_access(db, context, voice_session_id)
