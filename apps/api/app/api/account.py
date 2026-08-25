from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthDep
from app.core.db import get_db
from app.models import Organization, OrganizationMembership, User
from app.schemas import MeResponse, OrganizationResponse, UserResponse

router = APIRouter(tags=["account"])
SessionDep = Annotated[Session, Depends(get_db)]


def _organizations(db: Session, auth: AuthDep) -> list[OrganizationResponse]:
    if not auth.authenticated:
        return [
            OrganizationResponse(
                id=auth.organization_id,
                name="Development workspace",
                slug="development",
                kind="personal",
                role=auth.role,
            )
        ]
    rows = db.execute(
        select(Organization, OrganizationMembership.role)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.user_id == auth.user_id,
            OrganizationMembership.status == "active",
            Organization.status == "active",
        )
        .order_by(Organization.created_at)
    ).all()
    return [
        OrganizationResponse(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            kind=organization.kind,
            role=role,
        )
        for organization, role in rows
    ]


@router.get("/me", response_model=MeResponse)
def get_me(db: SessionDep, auth: AuthDep) -> MeResponse:
    organizations = _organizations(db, auth)
    active = next(
        (item for item in organizations if item.id == auth.organization_id),
        organizations[0],
    )
    user = db.get(User, auth.user_id) if auth.authenticated else None
    return MeResponse(
        user=UserResponse(
            id=auth.user_id,
            email=user.email if user else auth.email,
            display_name=user.display_name if user else "Developer",
        ),
        active_organization=active,
        organizations=organizations,
    )


@router.get("/organizations", response_model=list[OrganizationResponse])
def list_organizations(db: SessionDep, auth: AuthDep) -> list[OrganizationResponse]:
    return _organizations(db, auth)
