"""
midaz_reconciliation.py — Daily Reconciliation Pipeline
Block D-recon + J-audit, IL-013 Sprint 9
FCA CASS 7.15 / PS25/12 | banxe-emi-stack

OVERVIEW
--------
This module is the single entry-point for the daily safeguarding reconciliation.
It wires together:
  - MidazLedgerAdapter  → fetches account balances from Midaz CBS
  - StatementFetcher    → fetches external bank balances (CAMT.053 or CSV)
  - ReconciliationEngine → compares balances, produces ReconResult list
  - ClickHouseReconClient → writes results to banxe.safeguarding_events (J-audit)
  - n8n webhook         → fires Slack/email alert on DISCREPANCY

FCA CASS 15 requirements addressed:
  - Daily internal vs external reconciliation (CASS 7.15.17R)
  - Discrepancy detection + alert within 1 business day (CASS 7.15.29R)
  - Immutable audit trail in ClickHouse (I-24, I-15)
  - Decimal-only amounts throughout (I-24)

CLI usage (from GMKtec, called by daily-recon.sh cron):
    python -m services.recon.midaz_reconciliation [--date YYYY-MM-DD] [--dry-run]

Return codes:
    0 = all accounts MATCHED
    1 = at least one DISCREPANCY
    2 = at least one PENDING (no statement available)
    3 = fatal error (Midaz or ClickHouse unreachable)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("banxe.recon")

# ── env ───────────────────────────────────────────────────────────────────────
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")
RECON_THRESHOLD = Decimal(os.environ.get("RECON_THRESHOLD_GBP", "1.00"))


# ── public API ────────────────────────────────────────────────────────────────

def run_daily_recon(
    recon_date: Optional[date] = None,
    dry_run: bool = False,
) -> dict:
    """
    Execute daily safeguarding reconciliation pipeline.

    Args:
        recon_date: Date to reconcile. Defaults to today.
        dry_run:    If True, run full pipeline but do NOT write to ClickHouse
                    and do NOT fire webhooks. Used for testing on GMKtec.

    Returns:
        Summary dict with keys:
            recon_date, total_accounts, matched, discrepancy, pending, results
    """
    recon_date = recon_date or date.today()
    logger.info("=== Banxe Daily Recon START | date=%s | dry_run=%s ===", recon_date, dry_run)

    # ── 1. Build adapters ─────────────────────────────────────────────────────
    from services.ledger.midaz_adapter import MidazLedgerAdapter
    from services.recon.clickhouse_client import ClickHouseReconClient
    from services.recon.statement_fetcher import StatementFetcher
    from services.recon.reconciliation_engine import ReconciliationEngine

    ledger = MidazLedgerAdapter()
    fetcher = StatementFetcher()

    if dry_run:
        from services.recon.clickhouse_client import InMemoryReconClient
        ch_client = InMemoryReconClient()
        logger.info("DRY RUN: using InMemoryReconClient (no ClickHouse writes)")
    else:
        ch_client = ClickHouseReconClient()
        _ensure_schema(ch_client)

    engine = ReconciliationEngine(
        ledger_port=ledger,
        ch_client=ch_client,
        statement_fetcher=fetcher,
        threshold=RECON_THRESHOLD,
    )

    # ── 2. Run reconciliation ─────────────────────────────────────────────────
    results = engine.reconcile(recon_date)

    # ── 3. Build summary ──────────────────────────────────────────────────────
    summary = _build_summary(recon_date, results)
    _log_summary(summary)

    # ── 4. Fire alerts if needed ──────────────────────────────────────────────
    if not dry_run:
        _fire_alerts(results, recon_date)

    logger.info("=== Banxe Daily Recon END | %s ===", summary["overall_status"])
    return summary


# ── internal helpers ──────────────────────────────────────────────────────────

def _ensure_schema(ch_client) -> None:
    """Create ClickHouse tables if not yet created (idempotent)."""
    try:
        ch_client.ensure_schema()
    except Exception as exc:
        logger.error("ClickHouse schema ensure failed: %s — continuing", exc)


def _build_summary(recon_date: date, results: list) -> dict:
    matched = sum(1 for r in results if r.status == "MATCHED")
    discrepancy = sum(1 for r in results if r.status == "DISCREPANCY")
    pending = sum(1 for r in results if r.status == "PENDING")

    if discrepancy > 0:
        overall = "DISCREPANCY"
    elif pending > 0:
        overall = "PENDING"
    else:
        overall = "MATCHED"

    return {
        "recon_date": recon_date.isoformat(),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_accounts": len(results),
        "matched": matched,
        "discrepancy": discrepancy,
        "pending": pending,
        "overall_status": overall,
        "results": [
            {
                "account_id": r.account_id,
                "account_type": r.account_type,
                "status": r.status,
                "internal_balance": str(r.internal_balance),
                "external_balance": str(r.external_balance),
                "discrepancy": str(r.discrepancy),
                "currency": r.currency,
                "source_file": r.source_file,
            }
            for r in results
        ],
    }


def _log_summary(summary: dict) -> None:
    logger.info(
        "Recon summary: date=%s total=%d matched=%d discrepancy=%d pending=%d status=%s",
        summary["recon_date"],
        summary["total_accounts"],
        summary["matched"],
        summary["discrepancy"],
        summary["pending"],
        summary["overall_status"],
    )
    for r in summary["results"]:
        level = logging.WARNING if r["status"] != "MATCHED" else logging.INFO
        logger.log(
            level,
            "  %s (%s): internal=£%s external=£%s delta=£%s → %s",
            r["account_type"],
            r["account_id"][-8:],
            r["internal_balance"],
            r["external_balance"],
            r["discrepancy"],
            r["status"],
        )


def _fire_alerts(results: list, recon_date: date) -> None:
    """
    Fire n8n webhook for DISCREPANCY accounts.
    CASS 7.15.29R: alert must be sent within 1 business day.
    """
    if not N8N_WEBHOOK_URL:
        logger.debug("N8N_WEBHOOK_URL not set — skipping alerts")
        return

    discrepancy_results = [r for r in results if r.status == "DISCREPANCY"]
    if not discrepancy_results:
        return

    try:
        import httpx
        payload = {
            "event": "safeguarding_discrepancy",
            "recon_date": recon_date.isoformat(),
            "accounts": [
                {
                    "account_id": r.account_id,
                    "account_type": r.account_type,
                    "discrepancy_gbp": str(r.discrepancy),
                    "internal_balance": str(r.internal_balance),
                    "external_balance": str(r.external_balance),
                }
                for r in discrepancy_results
            ],
            "severity": "HIGH",
            "fca_rule": "CASS 7.15.29R",
        }
        resp = httpx.post(N8N_WEBHOOK_URL, json=payload, timeout=5.0)
        resp.raise_for_status()
        logger.info("n8n alert sent: %d discrepancy account(s)", len(discrepancy_results))
    except Exception as exc:
        # Alert failure must not block the audit trail — log only
        logger.error("n8n alert failed: %s — alert NOT sent", exc)


# ── CLI entry point ───────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Banxe Daily Safeguarding Reconciliation (FCA CASS 7.15)"
    )
    p.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Reconciliation date (default: today)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full pipeline but skip ClickHouse writes and webhooks",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output summary as JSON (for CI / script consumption)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    recon_date: Optional[date] = None
    if args.date:
        try:
            recon_date = date.fromisoformat(args.date)
        except ValueError:
            logger.error("Invalid date format: %s (expected YYYY-MM-DD)", args.date)
            return 3

    try:
        summary = run_daily_recon(recon_date=recon_date, dry_run=args.dry_run)
    except Exception as exc:
        logger.critical("Fatal error in daily recon: %s", exc, exc_info=True)
        return 3

    if args.output_json:
        print(json.dumps(summary, indent=2))

    # Exit code encodes severity for cron monitoring
    if summary["discrepancy"] > 0:
        return 1
    if summary["pending"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
