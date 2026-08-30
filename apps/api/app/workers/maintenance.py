from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import delete, text, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.learning.resources import ensure_knowledge_sources, refresh_knowledge_sources
from app.models import SemanticCacheEntry, VoiceTurn
from app.services.usage import UsageService

logger = logging.getLogger(__name__)
_MAINTENANCE_LOCK_ID = 1_380_275_023


def _utc_now() -> datetime:
    return datetime.now(UTC)


def expire_voice_transcripts(
    db,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    cutoff = (now or _utc_now()) - timedelta(days=retention_days)
    result = db.execute(
        update(VoiceTurn)
        .where(
            VoiceTurn.created_at < cutoff,
            VoiceTurn.transcript.is_not(None),
        )
        .values(
            transcript=None,
            transcript_status="expired",
        )
    )
    return int(result.rowcount or 0)


def run_maintenance() -> dict[str, object]:
    started_at = _utc_now()
    started = monotonic()
    summary: dict[str, object] = {
        "started_at": started_at.isoformat(),
        "semantic_cache_deleted": 0,
        "stale_reservations_released": 0,
        "voice_transcripts_expired": 0,
        "learning_sources": {},
    }
    with SessionLocal() as db:
        lock_acquired = bool(
            db.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": _MAINTENANCE_LOCK_ID},
            ).scalar()
        )
        if not lock_acquired:
            summary.update(
                {
                    "finished_at": _utc_now().isoformat(),
                    "duration_ms": round((monotonic() - started) * 1000, 2),
                    "outcome": "skipped_concurrent_run",
                }
            )
            return summary
        try:
            result = db.execute(
                delete(SemanticCacheEntry).where(
                    SemanticCacheEntry.expires_at < _utc_now(),
                    SemanticCacheEntry.hit_count == 0,
                )
            )
            summary["semantic_cache_deleted"] = int(result.rowcount or 0)
            summary["stale_reservations_released"] = UsageService(get_settings()).release_stale(
                db, commit=False
            )
            summary["voice_transcripts_expired"] = expire_voice_transcripts(
                db,
                retention_days=get_settings().voice_transcript_retention_days,
            )
            ensure_knowledge_sources(db)
            summary["learning_sources"] = refresh_knowledge_sources(db)
            db.commit()
            summary["outcome"] = "success"
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _MAINTENANCE_LOCK_ID},
            )
    summary.update(
        {
            "finished_at": _utc_now().isoformat(),
            "duration_ms": round((monotonic() - started) * 1000, 2),
        }
    )
    return summary


def main() -> int:
    configure_logging()
    try:
        summary = run_maintenance()
    except Exception:
        logger.exception(
            "maintenance_failed",
            extra={"error_code": "maintenance_failed", "outcome": "failed"},
        )
        return 1
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
