import logging
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import bind_log_context, configure_logging, reset_log_context

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.analysis_workspace.mkdir(parents=True, exist_ok=True)
    logger.info("service_started", extra={"outcome": "ready"})
    yield
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
    ],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-Id", "")
    request_id = supplied_request_id[:128] if supplied_request_id.isprintable() else ""
    request_id = request_id or str(uuid4())
    request.state.request_id = request_id
    token = bind_log_context(request_id=request_id)
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
