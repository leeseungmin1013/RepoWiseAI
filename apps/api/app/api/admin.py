from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import AdminDep
from app.core.authorization import ensure_organization_access
from app.core.db import get_db
from app.models import (
    AuditEvent,
    LearnerProfile,
    LearningSession,
    SemanticCacheEntry,
    UsageEvent,
    UsageReservation,
    VoiceSession,
    VoiceTurn,
)
from app.schemas import BonusCreditCreate, BonusCreditResponse
from app.services.usage import UsageService
from app.services.voice_metrics import summarize_voice_metrics

router = APIRouter(prefix="/admin", tags=["admin"])
SessionDep = Annotated[Session, Depends(get_db)]


@router.post(
    "/organizations/{organization_id}/bonus-credits",
    response_model=BonusCreditResponse,
)
def grant_bonus_credit(
    organization_id: str,
    payload: BonusCreditCreate,
    db: SessionDep,
    admin: AdminDep,
):
    ensure_organization_access(db, admin, organization_id, roles={"owner", "admin"})
    grant = UsageService().grant_bonus(
        db,
        organization_id=organization_id,
        amount_micro_usd=payload.amount_micro_usd,
        reason=payload.reason,
        reference=payload.reference,
        granted_by_user_id=admin.user_id,
        expires_at=payload.expires_at,
    )
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=admin.user_id,
            action="bonus_credit_granted",
            target_type="bonus_credit_grant",
            target_id=grant.id,
            metadata_json={
                "amount_micro_usd": grant.amount_micro_usd,
                "reference": grant.reference,
            },
        )
    )
    db.commit()
    return grant


@router.get("/voice/metrics")
def voice_metrics(
    db: SessionDep,
    admin: AdminDep,
    hours: int = 24,
) -> dict:
    bounded_hours = min(max(hours, 1), 24 * 30)
    since = datetime.now(UTC) - timedelta(hours=bounded_hours)
    sessions = db.scalars(
        select(VoiceSession)
        .join(LearningSession, LearningSession.id == VoiceSession.learning_session_id)
        .join(LearnerProfile, LearnerProfile.id == LearningSession.learner_profile_id)
        .where(
            LearnerProfile.organization_id == admin.organization_id,
            VoiceSession.started_at >= since,
        )
    ).all()
    turns = db.scalars(
        select(VoiceTurn)
        .join(VoiceSession, VoiceSession.id == VoiceTurn.voice_session_id)
        .join(LearningSession, LearningSession.id == VoiceSession.learning_session_id)
        .join(LearnerProfile, LearnerProfile.id == LearningSession.learner_profile_id)
        .where(
            LearnerProfile.organization_id == admin.organization_id,
            VoiceTurn.created_at >= since,
        )
    ).all()
    usage_events = db.scalars(
        select(UsageEvent).where(
            UsageEvent.organization_id == admin.organization_id,
            UsageEvent.feature == "realtime_voice",
            UsageEvent.created_at >= since,
        )
    ).all()
    return {
        "organization_id": admin.organization_id,
        "window_hours": bounded_hours,
        "since": since.isoformat(),
        "checked_at": datetime.now(UTC).isoformat(),
        **summarize_voice_metrics(sessions, turns, usage_events),
    }


@router.get("/usage/reconciliation")
def usage_reconciliation(db: SessionDep, admin: AdminDep) -> dict:
    pending = (
        db.scalar(
            select(func.count(UsageReservation.id)).where(
                UsageReservation.organization_id == admin.organization_id,
                UsageReservation.status == "pending_reconciliation",
            )
        )
        or 0
    )
    stale = (
        db.scalar(
            select(func.count(UsageReservation.id)).where(
                UsageReservation.organization_id == admin.organization_id,
                UsageReservation.status == "reserved",
                UsageReservation.expires_at < datetime.now(UTC),
            )
        )
        or 0
    )
    internal_cost = (
        db.scalar(
            select(func.coalesce(func.sum(UsageEvent.settled_cost_micro_usd), 0)).where(
                UsageEvent.organization_id == admin.organization_id
            )
        )
        or 0
    )
    invalid_cache = (
        db.scalar(
            select(func.count(SemanticCacheEntry.id)).where(
                SemanticCacheEntry.scope == "organization",
                SemanticCacheEntry.scope_id == admin.organization_id,
                SemanticCacheEntry.quality_status.in_(["quarantined", "invalid"]),
            )
        )
        or 0
    )
    return {
        "organization_id": admin.organization_id,
        "pending_reconciliation": int(pending),
        "stale_reservations": int(stale),
        "internal_settled_micro_usd": int(internal_cost),
        "invalid_cache_entries": int(invalid_cache),
        "checked_at": datetime.now(UTC).isoformat(),
    }
