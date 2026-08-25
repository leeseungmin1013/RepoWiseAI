from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    BonusCreditGrant,
    FeatureLimit,
    ModelPrice,
    OrganizationSubscription,
    Plan,
    QuotaPeriod,
    UsageEvent,
    UsageReservation,
)

FEATURE_CODES = {
    "repository_analysis_full",
    "repository_analysis_incremental",
    "repository_embedding",
    "chat_query_embedding",
    "chat_generation",
    "deep_explanation",
    "roadmap_proposal",
    "research_web_search",
    "architecture_label_generation",
    "realtime_voice",
    "realtime_transcription",
    "cached_request",
}


@dataclass(frozen=True)
class UsageContext:
    organization_id: str
    user_id: str | None
    feature: str
    request_id: str
    idempotency_key: str


@dataclass(frozen=True)
class UsageSnapshot:
    period_start: datetime
    period_end: datetime
    allowance_micro_usd: int
    bonus_available_micro_usd: int
    reserved_micro_usd: int
    consumed_micro_usd: int

    @property
    def remaining_micro_usd(self) -> int:
        return max(
            0,
            self.allowance_micro_usd
            + self.bonus_available_micro_usd
            - self.reserved_micro_usd
            - self.consumed_micro_usd,
        )


def month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return start, end


class UsageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def current_snapshot(self, db: Session, organization_id: str) -> UsageSnapshot:
        period = self._period(db, organization_id, lock=False)
        now = datetime.now(UTC)
        bonus = (
            db.scalar(
                select(func.coalesce(func.sum(BonusCreditGrant.remaining_micro_usd), 0)).where(
                    BonusCreditGrant.organization_id == organization_id,
                    BonusCreditGrant.cancelled_at.is_(None),
                    BonusCreditGrant.remaining_micro_usd > 0,
                    or_(BonusCreditGrant.expires_at.is_(None), BonusCreditGrant.expires_at > now),
                )
            )
            or 0
        )
        return UsageSnapshot(
            period_start=period.period_start,
            period_end=period.period_end,
            allowance_micro_usd=period.allowance_micro_usd,
            bonus_available_micro_usd=int(bonus),
            reserved_micro_usd=period.reserved_micro_usd,
            consumed_micro_usd=period.consumed_micro_usd,
        )

    def reserve(
        self,
        db: Session,
        *,
        context: UsageContext,
        estimated_cost_micro_usd: int,
    ) -> UsageReservation | None:
        if context.feature not in FEATURE_CODES:
            raise ValueError(f"Unknown usage feature: {context.feature}")
        if estimated_cost_micro_usd < 0:
            raise ValueError("Estimated cost cannot be negative")
        if self.settings.quota_enforcement_mode == "off":
            return None
        existing = db.scalar(
            select(UsageReservation).where(
                UsageReservation.organization_id == context.organization_id,
                UsageReservation.idempotency_key == context.idempotency_key,
            )
        )
        if existing is not None:
            return existing
        period = self._period(db, context.organization_id, lock=True)
        feature_limit_exceeded = False
        try:
            self._check_feature_limit(db, context, period)
        except HTTPException:
            if self.settings.quota_enforcement_mode == "enforce":
                raise
            feature_limit_exceeded = True
        snapshot = self.current_snapshot(db, context.organization_id)
        if snapshot.remaining_micro_usd < estimated_cost_micro_usd:
            detail = {
                "code": "monthly_quota_exceeded",
                "feature": context.feature,
                "period_end": snapshot.period_end.isoformat(),
                "usage": snapshot.consumed_micro_usd,
                "limit": snapshot.allowance_micro_usd,
                "bonus_available": snapshot.bonus_available_micro_usd,
            }
            if self.settings.quota_enforcement_mode == "enforce":
                raise HTTPException(status_code=429, detail=detail)
        reservation = UsageReservation(
            organization_id=context.organization_id,
            user_id=context.user_id,
            quota_period_id=period.id,
            feature=context.feature,
            idempotency_key=context.idempotency_key,
            estimated_cost_micro_usd=estimated_cost_micro_usd,
            status=(
                "reserved"
                if (
                    not feature_limit_exceeded
                    and snapshot.remaining_micro_usd >= estimated_cost_micro_usd
                )
                else "shadow_exceeded"
            ),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self.settings.usage_reservation_ttl_seconds),
        )
        db.add(reservation)
        if reservation.status == "reserved":
            period.reserved_micro_usd += estimated_cost_micro_usd
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return db.scalar(
                select(UsageReservation).where(
                    UsageReservation.organization_id == context.organization_id,
                    UsageReservation.idempotency_key == context.idempotency_key,
                )
            )
        return reservation

    def settle(
        self,
        db: Session,
        *,
        reservation_id: str | None,
        context: UsageContext,
        provider: str | None,
        model: str | None,
        usage: dict[str, Any],
        settled_cost_micro_usd: int | None = None,
        provider_request_id: str | None = None,
        cache_status: str = "miss",
    ) -> UsageEvent:
        event_key = f"{context.idempotency_key}:settlement"
        existing = db.scalar(
            select(UsageEvent).where(
                UsageEvent.organization_id == context.organization_id,
                UsageEvent.idempotency_key == event_key,
            )
        )
        if existing is not None:
            return existing
        reservation = (
            db.scalar(
                select(UsageReservation)
                .where(
                    UsageReservation.id == reservation_id,
                    UsageReservation.organization_id == context.organization_id,
                )
                .with_for_update()
            )
            if reservation_id
            else None
        )
        if reservation_id and reservation is None:
            raise ValueError("Usage reservation does not belong to the current organization")
        calculated_cost, price_version = self.calculate_cost(
            db, provider=provider, model=model, usage=usage
        )
        actual = settled_cost_micro_usd if settled_cost_micro_usd is not None else calculated_cost
        period = self._period(db, context.organization_id, lock=True)
        if reservation and reservation.status == "reserved":
            period.reserved_micro_usd = max(
                0, period.reserved_micro_usd - reservation.estimated_cost_micro_usd
            )
            reservation.status = "settled"
            reservation.settled_cost_micro_usd = actual
            reservation.provider_request_id = provider_request_id
            reservation.settled_at = datetime.now(UTC)
        bonus_available = self._bonus_available(db, context.organization_id, lock=True)
        bonus_charge = min(actual, bonus_available)
        if bonus_charge > 0:
            self._consume_bonus(db, context.organization_id, bonus_charge)
            period.bonus_consumed_micro_usd += bonus_charge
        allowance_charge = actual - bonus_charge
        period.consumed_micro_usd += allowance_charge
        event = UsageEvent(
            organization_id=context.organization_id,
            user_id=context.user_id,
            reservation_id=reservation.id if reservation else None,
            feature=context.feature,
            idempotency_key=event_key,
            provider=provider,
            model=model,
            price_version=price_version,
            usage_json=usage,
            estimated_cost_micro_usd=(reservation.estimated_cost_micro_usd if reservation else 0),
            settled_cost_micro_usd=actual,
            cache_status=cache_status,
        )
        db.add(event)
        db.commit()
        return event

    def release(
        self,
        db: Session,
        reservation_id: str | None,
        *,
        commit: bool = True,
    ) -> None:
        if not reservation_id:
            return
        reservation = db.scalar(
            select(UsageReservation).where(UsageReservation.id == reservation_id).with_for_update()
        )
        if reservation is None or reservation.status != "reserved":
            return
        period = db.scalar(
            select(QuotaPeriod)
            .where(QuotaPeriod.id == reservation.quota_period_id)
            .with_for_update()
        )
        if period:
            period.reserved_micro_usd = max(
                0, period.reserved_micro_usd - reservation.estimated_cost_micro_usd
            )
        reservation.status = "released"
        reservation.settled_at = datetime.now(UTC)
        if commit:
            db.commit()

    def calculate_cost(
        self,
        db: Session,
        *,
        provider: str | None,
        model: str | None,
        usage: dict[str, Any],
    ) -> tuple[int, str | None]:
        if not provider or not model:
            return 0, None
        now = datetime.now(UTC)
        prices = db.scalars(
            select(ModelPrice)
            .where(
                ModelPrice.provider == provider,
                ModelPrice.model == model,
                ModelPrice.effective_at <= now,
                or_(ModelPrice.expires_at.is_(None), ModelPrice.expires_at > now),
            )
            .order_by(ModelPrice.effective_at.desc())
        ).all()
        total = 0
        version = None
        priced_usage_types: set[str] = set()
        for price in prices:
            if price.usage_type in priced_usage_types:
                continue
            priced_usage_types.add(price.usage_type)
            amount = int(usage.get(price.usage_type, 0) or 0)
            total += amount * price.micro_usd_per_unit
            version = version or price.version
        return total, version

    def grant_bonus(
        self,
        db: Session,
        *,
        organization_id: str,
        amount_micro_usd: int,
        reason: str,
        reference: str,
        granted_by_user_id: str,
        expires_at: datetime | None,
    ) -> BonusCreditGrant:
        if amount_micro_usd <= 0 or not reason.strip() or not reference.strip():
            raise HTTPException(status_code=422, detail={"code": "invalid_bonus_grant"})
        grant = BonusCreditGrant(
            organization_id=organization_id,
            amount_micro_usd=amount_micro_usd,
            remaining_micro_usd=amount_micro_usd,
            reason=reason.strip(),
            reference=reference.strip(),
            granted_by_user_id=granted_by_user_id,
            expires_at=expires_at,
        )
        db.add(grant)
        db.flush()
        return grant

    def release_stale(self, db: Session, *, commit: bool = True) -> int:
        now = datetime.now(UTC)
        reservations = db.scalars(
            select(UsageReservation).where(
                UsageReservation.status == "reserved",
                UsageReservation.expires_at < now,
                UsageReservation.provider_request_id.is_(None),
            ).with_for_update(skip_locked=True)
        ).all()
        for item in reservations:
            self.release(db, item.id, commit=False)
        if commit:
            db.commit()
        return len(reservations)

    def _period(self, db: Session, organization_id: str, *, lock: bool) -> QuotaPeriod:
        start, end = month_bounds()
        query = select(QuotaPeriod).where(
            QuotaPeriod.organization_id == organization_id,
            QuotaPeriod.period_start == start,
        )
        if lock:
            query = query.with_for_update()
        period = db.scalar(query)
        if period is not None:
            return period
        allowance = self.settings.default_monthly_allowance_micro_usd
        subscription = db.scalar(
            select(OrganizationSubscription).where(
                OrganizationSubscription.organization_id == organization_id,
                OrganizationSubscription.status == "active",
            )
        )
        if subscription:
            plan = db.get(Plan, subscription.plan_id)
            if plan:
                allowance = plan.monthly_allowance_micro_usd
        period = QuotaPeriod(
            organization_id=organization_id,
            period_start=start,
            period_end=end,
            allowance_micro_usd=allowance,
        )
        db.add(period)
        db.flush()
        return period

    @staticmethod
    def _bonus_available(db: Session, organization_id: str, *, lock: bool) -> int:
        now = datetime.now(UTC)
        query = select(BonusCreditGrant).where(
            BonusCreditGrant.organization_id == organization_id,
            BonusCreditGrant.cancelled_at.is_(None),
            BonusCreditGrant.remaining_micro_usd > 0,
            or_(BonusCreditGrant.expires_at.is_(None), BonusCreditGrant.expires_at > now),
        )
        if lock:
            query = query.with_for_update()
        return sum(item.remaining_micro_usd for item in db.scalars(query).all())

    @staticmethod
    def _consume_bonus(db: Session, organization_id: str, amount: int) -> None:
        now = datetime.now(UTC)
        grants = db.scalars(
            select(BonusCreditGrant)
            .where(
                BonusCreditGrant.organization_id == organization_id,
                BonusCreditGrant.cancelled_at.is_(None),
                BonusCreditGrant.remaining_micro_usd > 0,
                or_(BonusCreditGrant.expires_at.is_(None), BonusCreditGrant.expires_at > now),
            )
            .order_by(BonusCreditGrant.expires_at.asc().nullslast(), BonusCreditGrant.created_at)
            .with_for_update()
        ).all()
        remaining = amount
        for grant in grants:
            used = min(remaining, grant.remaining_micro_usd)
            grant.remaining_micro_usd -= used
            remaining -= used
            if remaining == 0:
                break

    @staticmethod
    def _check_feature_limit(
        db: Session,
        context: UsageContext,
        period: QuotaPeriod,
    ) -> None:
        subscription = db.scalar(
            select(OrganizationSubscription).where(
                OrganizationSubscription.organization_id == context.organization_id,
                OrganizationSubscription.status == "active",
            )
        )
        if subscription is None:
            return
        limit = db.scalar(
            select(FeatureLimit).where(
                FeatureLimit.plan_id == subscription.plan_id,
                FeatureLimit.feature == context.feature,
            )
        )
        if limit is None:
            return
        count = (
            db.scalar(
                select(func.count(UsageEvent.id)).where(
                    UsageEvent.organization_id == context.organization_id,
                    UsageEvent.feature == context.feature,
                    UsageEvent.created_at >= period.period_start,
                    UsageEvent.created_at < period.period_end,
                )
            )
            or 0
        )
        active_reservations = (
            db.scalar(
                select(func.count(UsageReservation.id)).where(
                    UsageReservation.organization_id == context.organization_id,
                    UsageReservation.feature == context.feature,
                    UsageReservation.status == "reserved",
                    UsageReservation.expires_at > datetime.now(UTC),
                )
            )
            or 0
        )
        if limit.concurrent_limit is not None and active_reservations >= limit.concurrent_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "feature_concurrency_exceeded",
                    "feature": context.feature,
                    "usage": active_reservations,
                    "limit": limit.concurrent_limit,
                    "period_end": period.period_end.isoformat(),
                },
            )
        if limit.request_limit is not None and count >= limit.request_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "feature_limit_exceeded",
                    "feature": context.feature,
                    "period_end": period.period_end.isoformat(),
                    "usage": count,
                    "limit": limit.request_limit,
                    "bonus_available": 0,
                },
            )
