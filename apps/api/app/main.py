import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import bind_log_context, configure_logging, reset_log_context
from app.workers.queue_recovery import recover_queue_jobs

configure_logging()
logger = logging.getLogger(__name__)


async def periodic_queue_recovery(interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(max(1, interval_seconds))
        try:
            summary = await asyncio.to_thread(recover_queue_jobs)
            logger.info(
                "queue_recovery_periodic",
                extra={"outcome": summary["outcome"]},
            )
        except Exception:
            logger.exception(
                "queue_recovery_periodic_failed",
                extra={"error_code": "queue_recovery_failed", "outcome": "failed"},
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.analysis_workspace.mkdir(parents=True, exist_ok=True)
    logger.info("service_started", extra={"outcome": "ready"})
    recovery_task = asyncio.create_task(
        periodic_queue_recovery(settings.queue_recovery_interval_seconds)
    )
    try:
        yield
    finally:
        recovery_task.cancel()
        with suppress(asyncio.CancelledError):
            await recovery_task
        logger.info("service_stopped", extra={"outcome": "stopped"})


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Location",
        "X-OpenAI-Realtime-Call-Id",
        "X-Navigation-Artifact-Version",
        "X-Navigation-Cache",
        "X-Navigation-Cache-Write",
        "X-Request-Id",
        "X-Analysis-Reuse",
        "X-Retrieval-Cache",
        "X-Generation-Cache",
        "X-Quota-Remaining",
        "X-Realtime-Max-Duration",
        "X-RepoWise-Voice-Session-Id",
    ],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-Id", "")
    request_id = supplied_request_id[:128] if supplied_request_id.isprintable() else ""
    request_id = request_id or str(uuid4())
    request.state.request_id = request_id
    token = bind_log_context(request_id=request_id, trace_id=request_id)
    started = monotonic()
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "http_request_completed",
            extra={
                "duration_ms": round((monotonic() - started) * 1000, 2),
                "outcome": str(response.status_code),
            },
        )
        return response
    finally:
        reset_log_context(token)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "unhandled_request_exception",
        extra={"request_id": request_id, "error_code": "internal_error", "outcome": "failed"},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    response = JSONResponse(
        status_code=500,
        content={"detail": {"code": "internal_error"}, "request_id": request_id},
    )
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return response


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "RepoWise AI API", "docs": "/docs", "health": "/api/health/ready"}
