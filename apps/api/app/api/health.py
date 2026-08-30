from datetime import UTC, datetime

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Response, status
from redis import Redis
from rq import Worker
from sqlalchemy import text

from app.core.config import API_ROOT, get_settings
from app.core.db import SessionLocal

router = APIRouter(tags=["system"])


def _identity() -> dict[str, str]:
    settings = get_settings()
    return {"version": "0.1.0", "release": settings.resolved_release_sha}


@router.get("/health")
@router.get("/health/live")
def liveness() -> dict[str, object]:
    return {"status": "alive", **_identity()}


def _expected_migration_head() -> str | None:
    config = Config(str(API_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


@router.get("/health/ready")
def readiness(response: Response) -> dict[str, object]:
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        with SessionLocal() as session:
            session.execute(
                text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                {"timeout_ms": str(max(1, int(settings.healthcheck_timeout_seconds * 1000)))},
            )
            session.execute(text("SELECT 1"))
            current_head = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if current_head != _expected_migration_head():
                raise RuntimeError("database migration is not at application head")
        checks["database"] = "ready"
        checks["migration"] = "ready"
    except Exception:
        checks["database"] = "unavailable"
        checks["migration"] = "incompatible"

    connection = None
    try:
        connection = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.healthcheck_timeout_seconds,
            socket_timeout=settings.healthcheck_timeout_seconds,
        )
        connection.ping()
        checks["queue"] = "ready"
    except Exception:
        checks["queue"] = "unavailable"

    if connection is not None and checks["queue"] == "ready":
        try:
            now = datetime.now(UTC)
            active = []
            for worker in Worker.all(connection=connection):
                queue_names = set(worker.queue_names())
                heartbeat = worker.last_heartbeat
                if heartbeat is None or settings.queue_name not in queue_names:
                    continue
                if heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=UTC)
                age = (now - heartbeat).total_seconds()
                if age <= settings.worker_heartbeat_stale_seconds:
                    active.append(worker)
            checks["worker"] = "ready" if active else "unavailable"
        except Exception:
            checks["worker"] = "unavailable"
    else:
        checks["worker"] = "unavailable"

    core_ready = all(checks.get(name) == "ready" for name in ("database", "migration", "queue"))
    if not core_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": (
            "unavailable"
            if not core_ready
            else "ready"
            if checks["worker"] == "ready"
            else "degraded"
        ),
        **_identity(),
        "checks": checks,
    }
