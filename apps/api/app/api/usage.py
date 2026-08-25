from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthDep
from app.core.authorization import ensure_organization_access
from app.core.db import get_db
from app.models import FeatureLimit, OrganizationSubscription, UsageEvent
from app.schemas import FeatureLimitResponse, UsageCurrentResponse, UsageEventResponse
from app.services.usage import UsageService

router = APIRouter(prefix="/organizations/{organization_id}", tags=["usage"])
SessionDep = Annotated[Session, Depends(get_db)]


@router.get("/usage/current", response_model=UsageCurrentResponse)
def current_usage(
    organization_id: str,
    db: SessionDep,
    auth: AuthDep,
) -> UsageCurrentResponse:
    ensure_organization_access(db, auth, organization_id)
    current = UsageService().current_snapshot(db, organization_id)
    return UsageCurrentResponse(
        organization_id=organization_id,
        period_start=current.period_start,
        period_end=current.period_end,
        allowance_micro_usd=current.allowance_micro_usd,
        bonus_available_micro_usd=current.bonus_available_micro_usd,
        reserved_micro_usd=current.reserved_micro_usd,
        consumed_micro_usd=current.consumed_micro_usd,
        remaining_micro_usd=current.remaining_micro_usd,
    )


@router.get("/usage/events", response_model=list[UsageEventResponse])
def usage_events(
    organization_id: str,
    db: SessionDep,
    auth: AuthDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[UsageEvent]:
    ensure_organization_access(db, auth, organization_id)
    return list(
        db.scalars(
            select(UsageEvent)
            .where(UsageEvent.organization_id == organization_id)
            .order_by(UsageEvent.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.get("/limits", response_model=list[FeatureLimitResponse])
def feature_limits(
    organization_id: str,
    db: SessionDep,
    auth: AuthDep,
) -> list[FeatureLimit]:
    ensure_organization_access(db, auth, organization_id)
    subscription = db.get(OrganizationSubscription, organization_id)
    if subscription is None:
        return []
    return list(
        db.scalars(
            select(FeatureLimit)
            .where(FeatureLimit.plan_id == subscription.plan_id)
            .order_by(FeatureLimit.feature)
        ).all()
    )
