from fastapi import APIRouter
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ready"
    except Exception:
        checks["database"] = "unavailable"

    try:
        Redis.from_url(get_settings().redis_url).ping()
        checks["queue"] = "ready"
    except Exception:
        checks["queue"] = "unavailable"

    return {
        "status": "ready" if all(value == "ready" for value in checks.values()) else "degraded",
        "version": "0.1.0",
        "checks": checks,
    }
