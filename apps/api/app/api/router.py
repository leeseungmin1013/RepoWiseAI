from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api import (
    account,
    admin,
    assessment,
    chat,
    debug,
    deep_tasks,
    guidance,
    health,
    learning,
    repositories,
    usage,
    voice,
)
from app.core.auth import AuthDep, require_admin
from app.core.authorization import authorize_request_scope, ensure_profile_access
from app.core.db import get_db

SessionDep = Annotated[Session, Depends(get_db)]


async def authorize_scope(request: Request, db: SessionDep, context: AuthDep) -> None:
    authorize_request_scope(request, db, context)
    if (
        context.authenticated
        and request.method in {"POST", "PUT", "PATCH"}
        and "application/json" in request.headers.get("content-type", "")
    ):
        try:
            payload = await request.json()
        except ValueError:
            return
        if isinstance(payload, dict) and isinstance(payload.get("learner_profile_id"), str):
            ensure_profile_access(db, context, payload["learner_profile_id"])


api_router = APIRouter()
api_router.include_router(health.router)
protected = [Depends(authorize_scope)]
api_router.include_router(account.router, dependencies=protected)
api_router.include_router(usage.router, dependencies=protected)
api_router.include_router(admin.router, dependencies=protected)
api_router.include_router(repositories.router, dependencies=protected)
api_router.include_router(assessment.router, dependencies=protected)
api_router.include_router(guidance.router, dependencies=protected)
api_router.include_router(learning.router, dependencies=protected)
api_router.include_router(chat.router, dependencies=protected)
api_router.include_router(deep_tasks.router, dependencies=protected)
api_router.include_router(voice.router, dependencies=protected)
api_router.include_router(debug.router, dependencies=[Depends(require_admin)])
