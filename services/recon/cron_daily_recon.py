#!/usr/bin/env python3
"""
cron_daily_recon.py — Systemd entry point for FCA CASS 15 daily reconciliation.

This module is the systemd-facing wrapper around midaz_reconciliation.run_daily_recon().
Systemd services do not inherit the shell environment, so this module loads .env
before invoking the pipeline.

Usage:
  python3 -m services.recon.cron_daily_recon
  python3 -m services.recon.cron_daily_recon 2026-05-07
  python3 -m services.recon.cron_daily_recon --dry-run

Systemd unit:  /etc/systemd/system/banxe-recon.service
Systemd timer: /etc/systemd/system/banxe-recon.timer  (07:00 UTC Mon-Fri)

Exit codes:
  0 = MATCHED            — all accounts reconciled, no action required
  1 = DISCREPANCY        — MLRO alert sent, investigate within 1 business day (CASS 7.15.29R)
  2 = PENDING            — no bank statement yet (sandbox or weekend)
  3 = FATAL              — infrastructure failure, PagerDuty / CEO immediate action
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path

# ── Journal-compatible logging (systemd reads stdout/stderr via journald) ─────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s banxe-recon: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("banxe.recon.cron")

# ── Exit code constants (mirrors daily-recon.sh for cron-monitor compatibility)
EXIT_MATCHED = 0
EXIT_DISCREPANCY = 1
EXIT_PENDING = 2
EXIT_FATAL = 3


def _load_env(repo_dir: Path) -> None:
    """
    Parse and load .env into os.environ.

    Uses minimal parsing (no external deps) so it works before pip installs.
    Variables already set in the environment take precedence (Docker / systemd
    EnvironmentFile overrides).
    """
    env_path = repo_dir / ".env"
    if not env_path.exists():
        logger.warning(".env not found at %s — relying on system environment", env_path)
        return

    loaded = 0
    with env_path.open() as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
                loaded += 1

    logger.info("Loaded %d variable(s) from %s", loaded, env_path)


def _parse_args() -> tuple[date | None, bool]:
    """Parse CLI args without argparse (avoids import before .env load)."""
    args = list(sys.argv[1:])
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    recon_date: date | None = None
    if args:
        try:
            recon_date = date.fromisoformat(args[0])
        except ValueError:
            logger.error("Invalid date: %s (expected YYYY-MM-DD)", args[0])
            sys.exit(EXIT_FATAL)

    return recon_date, dry_run


def main() -> int:
    # ── 1. Locate repo root ───────────────────────────────────────────────────
    # This file lives at  <repo>/services/recon/cron_daily_recon.py
    repo_dir = Path(__file__).resolve().parent.parent.parent

    # ── 2. Load .env before any other imports ────────────────────────────────
    _load_env(repo_dir)

    # ── 3. Ensure repo is on sys.path ────────────────────────────────────────
    repo_str = str(repo_dir)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)

    # ── 4. Parse CLI ─────────────────────────────────────────────────────────
    recon_date, dry_run = _parse_args()

    if dry_run:
        logger.info("DRY RUN: no ClickHouse writes, no webhooks")

    # ── 5. Run reconciliation pipeline ───────────────────────────────────────
    try:
        from services.recon.midaz_reconciliation import run_daily_recon  # noqa: PLC0415
        summary = run_daily_recon(recon_date=recon_date, dry_run=dry_run)
    except Exception as exc:
        logger.critical("FATAL — reconciliation pipeline crashed: %s", exc, exc_info=True)
        return EXIT_FATAL

    # ── 6. Structured summary for journald ───────────────────────────────────
    status = summary.get("overall_status", "FATAL")
    logger.info(
        "STATUS=%s date=%s matched=%d discrepancy=%d pending=%d total=%d",
        status,
        summary.get("recon_date", "?"),
        summary.get("matched", 0),
        summary.get("discrepancy", 0),
        summary.get("pending", 0),
        summary.get("total_accounts", 0),
    )

    # ── 7. Exit code → systemd service result / on-failure alerting ─────────
    if status == "DISCREPANCY":
        logger.warning(
            "CASS 7.15.29R: shortfall detected — MLRO must investigate within 1 business day"
        )
        return EXIT_DISCREPANCY

    if status == "PENDING":
        logger.info("No bank statement available — PENDING (non-critical for sandbox)")
        return EXIT_PENDING

    if status == "MATCHED":
        logger.info("All accounts matched — safeguarding requirement satisfied")
        return EXIT_MATCHED

    logger.error("Unknown status: %s", status)
    return EXIT_FATAL


if __name__ == "__main__":
    sys.exit(main())
