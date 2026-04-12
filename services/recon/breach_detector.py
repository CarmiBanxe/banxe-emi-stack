"""
breach_detector.py — FCA CASS 15 Safeguarding Breach Detector
IL-015 Step 1 | banxe-emi-stack

FCA CASS 15.12 / PS25/12:
  If a safeguarding discrepancy persists for >= 3 business days,
  the firm MUST:
    1. Write a breach record to safeguarding_breaches
    2. Notify FCA via RegData within 1 business day
    3. Escalate to CEO + CTIO

Threshold: BREACH_DAYS = 3 (configurable via env)
Amount threshold: BREACH_AMOUNT_GBP = 10.00 (£10 minimum reportable)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

BREACH_DAYS = int(os.environ.get("BREACH_DAYS", "3"))
BREACH_AMOUNT_GBP = Decimal(os.environ.get("BREACH_AMOUNT_GBP", "10.00"))
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")


@dataclass(frozen=True)
class BreachRecord:
    """One breach detected by BreachDetector."""

    account_id: str
    account_type: str
    currency: str
    discrepancy: Decimal
    days_outstanding: int
    first_seen: date
    latest_date: date


class BreachClientProtocol(Protocol):
    """Protocol for ClickHouse breach operations (test injection point)."""

    def get_discrepancy_streak(
        self,
        account_id: str,
        as_of: date,
        min_days: int,
    ) -> int:
        """Return consecutive DISCREPANCY days for account up to as_of."""
        ...

    def write_breach(self, breach: BreachRecord) -> None:
        """Insert a breach record into safeguarding_breaches."""
        ...

    def get_latest_discrepancy(self, account_id: str, as_of: date) -> dict | None:
        """Return the most recent DISCREPANCY row for account."""
        ...


class BreachDetector:
    """
    Checks safeguarding_events for persisting DISCREPANCYs.

    Workflow (called after each daily reconciliation):
    1. For each account, count consecutive DISCREPANCY days up to recon_date.
    2. If streak >= BREACH_DAYS AND discrepancy >= BREACH_AMOUNT_GBP:
       a. Write breach record to safeguarding_breaches.
       b. Fire n8n webhook → Slack + FCA notification channel.
    3. Return list of BreachRecord (empty = no breach).

    Usage:
        detector = BreachDetector(ch_breach_client)
        breaches = detector.check_and_escalate(results, date.today())
    """

    def __init__(
        self,
        ch_client: BreachClientProtocol,
        breach_days: int = BREACH_DAYS,
        amount_threshold: Decimal = BREACH_AMOUNT_GBP,
    ) -> None:
        self._ch = ch_client
        self._breach_days = breach_days
        self._amount_threshold = amount_threshold

    def check_and_escalate(
        self,
        results: list,
        recon_date: date,
    ) -> list[BreachRecord]:
        """
        Main entry point — call after ReconciliationEngine.reconcile().

        Args:
            results: List[ReconResult] from reconciliation_engine
            recon_date: The date being reconciled

        Returns:
            List of BreachRecord written to ClickHouse (may be empty)
        """
        breaches: list[BreachRecord] = []

        for result in results:
            if result.status != "DISCREPANCY":
                continue

            discrepancy_abs = abs(result.discrepancy)
            if discrepancy_abs < self._amount_threshold:
                logger.debug(
                    "Discrepancy £%s for %s below threshold £%s — skipping breach",
                    discrepancy_abs,
                    result.account_id,
                    self._amount_threshold,
                )
                continue

            streak = self._ch.get_discrepancy_streak(
                result.account_id, recon_date, self._breach_days
            )
            if streak < self._breach_days:
                logger.info(
                    "DISCREPANCY streak %d days for %s — below %d day threshold",
                    streak,
                    result.account_id,
                    self._breach_days,
                )
                continue

            breach = BreachRecord(
                account_id=result.account_id,
                account_type=result.account_type,
                currency=result.currency,
                discrepancy=discrepancy_abs,
                days_outstanding=streak,
                first_seen=recon_date,
                latest_date=recon_date,
            )
            self._ch.write_breach(breach)
            breaches.append(breach)

            logger.warning(
                "CASS 15 BREACH: account=%s type=%s discrepancy=%s days=%d — "
                "FCA notification required within 1 business day",
                breach.account_id,
                breach.account_type,
                breach.discrepancy,
                breach.days_outstanding,
            )
            _fire_fca_alert(breach)

        return breaches


def _fire_fca_alert(breach: BreachRecord) -> None:
    """
    Fire n8n webhook with FCA breach notification.
    CASS 15.12: notify FCA within 1 business day of breach detection.
    This webhook triggers Slack → Compliance officer → FCA RegData submission.
    """
    if not N8N_WEBHOOK_URL:
        logger.warning(
            "N8N_WEBHOOK_URL not set — FCA breach alert NOT sent for %s", breach.account_id
        )
        return

    payload = {
        "event": "SAFEGUARDING_BREACH",
        "severity": "CRITICAL",
        "account_id": breach.account_id,
        "account_type": breach.account_type,
        "currency": breach.currency,
        "discrepancy_gbp": str(breach.discrepancy),
        "days_outstanding": breach.days_outstanding,
        "first_seen": breach.first_seen.isoformat(),
        "latest_date": breach.latest_date.isoformat(),
        "fca_rule": "CASS 15.12 / PS25/12",
        "action_required": "FCA RegData notification within 1 business day",
    }

    try:
        response = httpx.post(N8N_WEBHOOK_URL, json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info(
            "FCA breach alert sent for %s (n8n HTTP %s)", breach.account_id, response.status_code
        )
    except Exception as exc:
        logger.error(
            "FCA breach alert FAILED for %s: %s — manual notification required",
            breach.account_id,
            exc,
        )
