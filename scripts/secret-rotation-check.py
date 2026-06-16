#!/usr/bin/env python3
"""Secret rotation check entrypoint (ADR-032, G-SEC-01).

Checks for overdue secret rotations and reports status.
Designed for cron/CI execution.

Usage:
    python3 scripts/secret-rotation-check.py

Cron (daily at 08:00):
    0 8 * * * cd /opt/banxe && python3 scripts/secret-rotation-check.py >> /var/log/banxe/secret-rotation.log 2>&1

Exit codes:
    0  no overdue secrets (or rotation disabled — no-op)
    1  overdue secrets found (alert trigger)
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
logger = logging.getLogger("banxe.secret-rotation-check")


def main() -> int:
    enabled = os.environ.get("SECRET_ROTATION_ENABLED", "false").lower() == "true"
    if not enabled:
        logger.info("SECRET_ROTATION_ENABLED=false, skipping")
        return 0

    try:
        from services.secrets.factory import get_secret_rotator
    except ImportError as exc:
        logger.error("Import failed — is PYTHONPATH set? %s", exc)
        return 1

    rotator = get_secret_rotator()
    all_secrets = rotator.list_secrets()
    overdue = rotator.check_overdue()

    logger.info("secret-rotation-check: %d managed secrets", len(all_secrets))

    for secret in all_secrets:
        status = rotator.get_rotation_status(secret.secret_id)
        flag = "OVERDUE" if status.is_overdue else "OK"
        last = status.last_rotated.date() if status.last_rotated else "NEVER"
        next_due = status.next_due.date() if status.next_due else "N/A"
        logger.info(
            "  [%s] %s — last: %s, next: %s, days_until: %d",
            flag,
            secret.secret_id,
            last,
            next_due,
            status.days_until_due,
        )

    if overdue:
        logger.warning(
            "secret-rotation-check: %d OVERDUE secret(s): %s",
            len(overdue),
            ", ".join(s.secret_id for s in overdue),
        )
        return 1

    logger.info("secret-rotation-check: ALL OK — no overdue secrets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
