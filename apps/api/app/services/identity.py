from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.models import Organization, OrganizationMembership, User, UserPreference


@dataclass(frozen=True)
class IdentityBootstrap:
    user: User
    organization: Organization
    membership: OrganizationMembership


def _personal_slug(user_id: str) -> str:
    clean = re.sub(r"[^a-z0-9-]+", "-", user_id.lower()).strip("-")[:80] or "user"
    return f"personal-{clean}"


def bootstrap_identity(
    db: Session,
    *,
    user_id: str,
    email: str | None,
    display_name: str | None,
) -> IdentityBootstrap:
    user = db.get(User, user_id)
    if user is None:
        user = User(id=user_id, email=email, display_name=display_name)
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            user = db.get(User, user_id)
            if user is None:
                raise
    else:
        if email and user.email != email:
            user.email = email
        if display_name and user.display_name != display_name:
            user.display_name = display_name

    membership = db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
        .order_by(OrganizationMembership.created_at)
    )
    if membership is None:
        organization = Organization(
            id=new_id("org"),
            name=(display_name or email or "Personal")[:180],
            slug=f"{_personal_slug(user_id)}-{new_id('w')[-8:]}",
            kind="personal",
            owner_user_id=user_id,
        )
        db.add(organization)
        db.flush()
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user_id,
            role="owner",
            status="active",
        )
        db.add(membership)
        db.add(UserPreference(user_id=user_id))
        db.flush()
    else:
        organization = db.get(Organization, membership.organization_id)
        if organization is None:
            raise RuntimeError("Identity membership references a missing organization")
    db.commit()
    return IdentityBootstrap(user=user, organization=organization, membership=membership)
