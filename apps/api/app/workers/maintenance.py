from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import SemanticCacheEntry
from app.services.usage import UsageService


def cleanup_semantic_cache() -> int:
    with SessionLocal() as db:
        result = db.execute(
            delete(SemanticCacheEntry).where(
                SemanticCacheEntry.expires_at < datetime.now(UTC),
                SemanticCacheEntry.hit_count == 0,
            )
        )
        db.commit()
        return int(result.rowcount or 0)


def release_stale_usage_reservations() -> int:
    with SessionLocal() as db:
        return UsageService(get_settings()).release_stale(db)


def run_maintenance() -> dict[str, int]:
    return {
        "semantic_cache_deleted": cleanup_semantic_cache(),
        "stale_reservations_released": release_stale_usage_reservations(),
    }
