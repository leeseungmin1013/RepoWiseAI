from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import API_ROOT, get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)
_MIGRATION_LOCK_ID = 1_380_275_022


def main() -> int:
    configure_logging()
    settings = get_settings()
    database_url = settings.migration_database_url or settings.database_url
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": _MIGRATION_LOCK_ID},
            )
            try:
                config = Config(str(API_ROOT / "alembic.ini"))
                config.set_main_option("sqlalchemy.url", database_url)
                command.upgrade(config, "head")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _MIGRATION_LOCK_ID},
                )
        logger.info("migration_completed", extra={"outcome": "success"})
        return 0
    except Exception:
        logger.exception(
            "migration_failed",
            extra={"error_code": "migration_failed", "outcome": "failed"},
        )
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
