from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.analysis_workspace.mkdir(parents=True, exist_ok=True)
    yield


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
    request_id = request.headers.get("X-Request-Id") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "RepoWise AI API", "docs": "/docs", "health": "/api/health"}
