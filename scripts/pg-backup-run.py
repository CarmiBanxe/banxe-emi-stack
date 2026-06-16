#!/usr/bin/env python3
"""Postgres backup cron entrypoint (ADR-029, G-OPS-01/02).

Runs pg_dump backup for configured databases and rotates old backups.
Designed for cron/systemd-timer execution.

Usage:
    python3 scripts/pg-backup-run.py

Cron (daily at 03:00):
    0 3 * * * cd /opt/banxe && python3 scripts/pg-backup-run.py >> /var/log/banxe/pg-backup.log 2>&1

Environment variables:
    BACKUP_ENABLED          "true" to enable (default: "false" — no-op)
    BACKUP_PG_HOST          PostgreSQL host (default: localhost)
    BACKUP_PG_PORT          PostgreSQL port (default: 5432)
    BACKUP_PG_USER          PostgreSQL user (default: banxe)
    BACKUP_PG_PASSWORD      PostgreSQL password
    BACKUP_DIR              Backup directory (default: /data/banxe/backups)
    BACKUP_RETENTION_COUNT  Backups to keep (default: 7)
    BACKUP_DATABASES        Comma-separated DB names (default: keycloak)

Exit codes:
    0  success (or disabled — no-op)
    1  any backup/rotation failure
"""

from __future__ import annotations

import logging
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("banxe.pg-backup")


def main() -> int:
    enabled = os.environ.get("BACKUP_ENABLED", "false").lower() == "true"
    if not enabled:
        logger.info("pg-backup: BACKUP_ENABLED != true, skipping (no-op)")
        return 0

    try:
        from services.backup.factory import get_backup_adapter
    except ImportError as exc:
        logger.error("Import failed — is PYTHONPATH set? %s", exc)
        return 1

    databases = os.environ.get("BACKUP_DATABASES", "keycloak").split(",")
    databases = [db.strip() for db in databases if db.strip()]
    retention = int(os.environ.get("BACKUP_RETENTION_COUNT", "7"))

    adapter = get_backup_adapter()
    failures = 0

    for db_name in databases:
        logger.info("pg-backup: starting backup for %s", db_name)
        result = adapter.backup(db_name)

        if result.success:
            logger.info(
                "pg-backup: OK %s — %s (%d bytes)",
                db_name,
                result.path,
                result.size_bytes,
            )
        else:
            logger.error("pg-backup: FAIL %s — %s", db_name, result.error)
            failures += 1
            continue

        rot = adapter.rotate(db_name, keep_last=retention)
        if rot.success:
            logger.info(
                "pg-backup: rotation %s — kept=%d deleted=%d freed=%d bytes",
                db_name,
                rot.kept,
                rot.deleted,
                rot.freed_bytes,
            )
        else:
            logger.error("pg-backup: rotation FAIL %s — %s", db_name, rot.error)
            failures += 1

    if failures:
        logger.error("pg-backup: %d failure(s) across %d databases", failures, len(databases))
        return 1

    logger.info("pg-backup: ALL DONE (%d databases)", len(databases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
