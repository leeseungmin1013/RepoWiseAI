from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)
_sensitive_assignment = re.compile(
    r"(?i)(access[_-]?token|database_url|redis_url)"
    r"\s*[:=]\s*([^\s,}]+)"
)
_sensitive_header = re.compile(r"(?i)(authorization|cookie)\s*[:=]\s*([^,}\r\n]+)")
_internal_url = re.compile(
    r"(?i)(postgres(?:ql)?(?:\+[^:]+)?|rediss?)://[^\s,}]+"
)


def bind_log_context(**values: Any):
    values = {key: value for key, value in values.items() if value is not None}
    return _context.set({**(_context.get() or {}), **values})


def replace_log_context(**values: Any):
    values = {key: value for key, value in values.items() if value is not None}
    return _context.set(values)


def reset_log_context(token) -> None:
    _context.reset(token)


def current_log_context() -> dict[str, Any]:
    return dict(_context.get() or {})


def current_trace_id() -> str | None:
    context = current_log_context()
    value = context.get("trace_id") or context.get("request_id")
    return str(value) if value else None


def redact(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = _sensitive_header.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    value = _sensitive_assignment.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return _internal_url.sub(lambda match: f"{match.group(1)}://[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": settings.service_name,
            "environment": settings.app_env,
            "release": settings.resolved_release_sha,
            "message": redact(record.getMessage()),
            **current_log_context(),
        }
        for field in (
            "request_id",
            "trace_id",
            "organization_id",
            "job_id",
            "task_id",
            "snapshot_id",
            "duration_ms",
            "outcome",
            "error_code",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = redact(value)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "rq.worker"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
