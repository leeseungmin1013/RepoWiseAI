from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import OrganizationMembership
from app.services.identity import bootstrap_identity


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    organization_id: str
    role: str
    email: str | None = None
    authenticated: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role in {"owner", "admin"}


_current_auth: ContextVar[AuthContext | None] = ContextVar("repowise_auth", default=None)


def current_auth_context() -> AuthContext | None:
    return _current_auth.get()


_bearer = HTTPBearer(auto_error=False)
_jwks_clients: dict[str, PyJWKClient] = {}


def _jwks_client(settings: Settings) -> PyJWKClient:
    url = settings.resolved_supabase_jwks_url
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "auth_not_configured"},
        )
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(
            url,
            cache_keys=True,
            lifespan=settings.supabase_jwks_ttl_seconds,
            timeout=10,
        )
        _jwks_clients[url] = client
    return client


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    issuer = settings.resolved_supabase_issuer
    if not issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "auth_not_configured"},
        )
    try:
        signing_key = _jwks_client(settings).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.supabase_jwt_audience,
            issuer=issuer,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_access_token"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_access_token"},
        )
    return payload


def get_auth_context(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    organization_header: Annotated[str | None, Header(alias="X-Organization-Id")] = None,
) -> AuthContext:
    settings = get_settings()
    if credentials is None:
        if settings.auth_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "authentication_required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthContext(
            user_id="dev-user",
            organization_id=settings.default_organization_id or "dev-org",
            role="owner",
            authenticated=False,
        )
    payload = decode_access_token(credentials.credentials, settings)
    bootstrap = bootstrap_identity(
        db,
        user_id=str(payload["sub"]),
        email=payload.get("email"),
        display_name=(payload.get("user_metadata") or {}).get("display_name")
        or (payload.get("user_metadata") or {}).get("full_name"),
    )
    organization_id = organization_header or bootstrap.organization.id
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == bootstrap.user.id,
            OrganizationMembership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail={"code": "organization_access_denied"})
    return AuthContext(
        user_id=bootstrap.user.id,
        organization_id=membership.organization_id,
        role=membership.role,
        email=bootstrap.user.email,
    )


AuthDep = Annotated[AuthContext, Depends(get_auth_context)]


def require_admin(context: AuthDep) -> AuthContext:
    if not context.is_admin:
        raise HTTPException(status_code=403, detail={"code": "admin_role_required"})
    return context


AdminDep = Annotated[AuthContext, Depends(require_admin)]
