from fastapi import APIRouter

from app.api import (
    assessment,
    chat,
    debug,
    deep_tasks,
    guidance,
    health,
    learning,
    repositories,
    voice,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(repositories.router)
api_router.include_router(assessment.router)
api_router.include_router(guidance.router)
api_router.include_router(learning.router)
api_router.include_router(chat.router)
api_router.include_router(deep_tasks.router)
api_router.include_router(voice.router)
api_router.include_router(debug.router)
