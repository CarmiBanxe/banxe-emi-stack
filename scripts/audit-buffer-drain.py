#!/usr/bin/env python3
"""Drain the SQLite audit ring-buffer to ClickHouse.

Reads undrained events from the SQLite buffer (BufferedAuditPort) and forwards
them to AuditTrail (ClickHouse). Cleans up drained rows older than 14 days.

Usage:
    python3 scripts/audit-buffer-drain.py

Cron (every 5 minutes):
    */5 * * * * cd /opt/banxe && python3 scripts/audit-buffer-drain.py >> /var/log/banxe/audit-drain.log 2>&1

Environment variables:
    CLICKHOUSE_URL      ClickHouse HTTP endpoint (default: http://192.168.0.72:8123)
    CLICKHOUSE_DB       ClickHouse database name (default: banxe)
    AUDIT_DRY_RUN       true → log only, no CH writes (default: false)
    AUDIT_BUFFER_PATH   SQLite ring-buffer path (default: /tmp/banxe-audit-buffer.db)

Exit codes:
    0  success (including zero events to drain)
    1  unexpected error
"""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("banxe.audit-drain")

# Ensure repo root is on sys.path when run as a script
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def main() -> int:
    try:
        from src.safeguarding.audit_trail import AuditTrail
        from src.safeguarding.buffered_audit_port import BufferedAuditPort
    except ImportError as exc:
        logger.error("Import failed — is PYTHONPATH set correctly? %s", exc)
        return 1

    ch_url = os.getenv("CLICKHOUSE_URL", "http://192.168.0.72:8123")
    db = os.getenv("CLICKHOUSE_DB", "banxe")
    dry_run = os.getenv("AUDIT_DRY_RUN", "false").lower() == "true"
    buffer_path = os.getenv("AUDIT_BUFFER_PATH", "/tmp/banxe-audit-buffer.db")

    target = AuditTrail(clickhouse_url=ch_url, database=db, dry_run=dry_run)
    port = BufferedAuditPort(db_path=buffer_path)

    pending_before = port.pending_count()
    logger.info("audit-drain start: pending=%d buffer=%s", pending_before, buffer_path)

    try:
        drained = port.drain(target=target, batch_size=100)
        cleaned = port.cleanup(max_age_days=14)
        pending_after = port.pending_count()
        logger.info(
            "audit-drain done: drained=%d cleaned=%d pending=%d",
            drained,
            cleaned,
            pending_after,
        )
    except Exception as exc:
        logger.error("audit-drain error: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
