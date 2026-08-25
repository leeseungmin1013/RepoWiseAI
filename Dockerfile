# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY apps/api/app ./app
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134 AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANALYSIS_WORKSPACE=/tmp/repowise/repositories \
    PORT=10000

RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 repowise \
    && useradd --system --uid 10001 --gid repowise --home-dir /nonexistent --shell /usr/sbin/nologin repowise \
    && mkdir -p /tmp/repowise/repositories \
    && chown -R repowise:repowise /tmp/repowise

WORKDIR /app
COPY --from=builder --chown=repowise:repowise /app/.venv ./.venv
COPY --from=builder --chown=repowise:repowise /app/app ./app
COPY --from=builder --chown=repowise:repowise /app/migrations ./migrations
COPY --from=builder --chown=repowise:repowise /app/alembic.ini ./alembic.ini

USER 10001:10001
EXPOSE 10000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000", "--proxy-headers", "--forwarded-allow-ips=*", "--timeout-graceful-shutdown", "240", "--no-access-log"]
