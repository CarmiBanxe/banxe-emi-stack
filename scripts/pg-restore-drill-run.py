#!/usr/bin/env python3
"""Postgres restore-drill cron entrypoint (ADR-029 §Implementation-Plan item 4).

Runs a single restore drill against a supplied backup URI:
  1. createdb {drill-db}
  2. pg_restore -d {drill-db} {backup-uri}
  3. psql -t -c "SELECT count(*) FROM {validation_table};"
  4. dropdb {drill-db}        (best-effort)

Emits a one-line JSON DrillResult to stdout. Designed for weekly cron.

Cron (Sunday 04:00 per ADR-029 §4):
    0 4 * * 0 cd /opt/banxe && python3 scripts/pg-restore-drill-run.py \\
        --instance banxe-marble-postgres --backup-uri /data/banxe/backups/... \\
        >> /var/log/banxe/restore-drill.log 2>&1

Environment variables (see services/backup/factory.RestoreDrillConfig):
    RESTORE_DRILL_ENABLED            "true" to enable (default: "false" — no-op)
    RESTORE_DRILL_VALIDATION_TABLE   table for row-count check (default: "cases")
    RESTORE_DRILL_DB_PREFIX          throwaway DB prefix (default: "postgres-restore-drill-")

Exit codes:
    0  success (or disabled — no-op)
    1  drill failure
"""

from __future__ import annotations

import argparse
import dataclasses
import json
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
logger = logging.getLogger("banxe.pg-restore-drill")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True, help="logical instance name")
    parser.add_argument(
        "--backup-uri",
        required=True,
        help="pg_restore-compatible backup URI (local path)",
    )
    parser.add_argument(
        "--target-db",
        default=None,
        help="explicit throwaway DB name (default: auto-generated)",
    )
    args = parser.parse_args(argv)

    enabled = os.environ.get("RESTORE_DRILL_ENABLED", "false").lower() == "true"
    if not enabled:
        logger.info("pg-restore-drill: RESTORE_DRILL_ENABLED != true, skipping (no-op)")
        return 0

    try:
        from services.backup.factory import get_restore_drill_adapter
    except ImportError as exc:
        logger.error("Import failed — is PYTHONPATH set? %s", exc)
        return 1

    adapter = get_restore_drill_adapter()
    result = adapter.run_drill(
        instance_name=args.instance,
        backup_uri=args.backup_uri,
        target_db=args.target_db,
    )

    print(json.dumps(dataclasses.asdict(result), default=str))

    if result.success:
        logger.info(
            "pg-restore-drill: OK instance=%s rows=%s table=%s",
            result.instance,
            result.row_count,
            result.validation_table,
        )
        return 0

    logger.error(
        "pg-restore-drill: FAIL instance=%s error=%s",
        result.instance,
        result.error,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
