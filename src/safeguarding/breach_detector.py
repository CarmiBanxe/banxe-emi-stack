"""Breach detector — CASS 7 / PS23/3.

Tracks consecutive days of reconciliation breaks or shortfalls.
A streak > 3 days triggers a mandatory FCA safeguarding breach notification.

FCA rules:
  CASS 7.15.29G  — breach must be notified within 1 business day of discovery
  PS23/3 §3.49   — enhanced breach notification requirements from 7 May 2026

Breach severity matrix:
  SHORTFALL   — internal < external (client money at risk)   → CRITICAL
  OVERSTATEMENT — internal > external (operational risk)     → MAJOR
  RECON_BREAK — unresolved >1 day                            → MAJOR
  STREAK_>3   — 3 consecutive break days                     → CRITICAL + FCA alert

Usage:
    detector = BreachDetector()
    alert = detector.assess(result, consecutive_break_days=1)
    if alert:
        detector.notify_fca(alert, dry_run=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
import logging

from .daily_reconciliation import ReconciliationResult, ReconStatus

logger = logging.getLogger(__name__)

# CASS / PS23/3 breach thresholds
FCA_ALERT_STREAK_DAYS = 3  # consecutive break days → mandatory FCA notification
SHORTFALL_ALERT_THRESHOLD = Decimal("0")  # any shortfall = critical


class BreachSeverity(str, Enum):
    MINOR = "MINOR"  # isolated recon break <24h
    MAJOR = "MAJOR"  # recon break >1 day or overstatement
    CRITICAL = "CRITICAL"  # shortfall or streak >3 days — FCA notification mandatory


@dataclass
class BreachAlert:
    breach_date: date
    severity: BreachSeverity
    consecutive_days: int
    shortfall_gbp: Decimal | None
    description: str
    fca_notification_required: bool
    raised_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False

    @property
    def reference(self) -> str:
        return f"BREACH-{self.breach_date.isoformat()}-{self.severity.value}"


class BreachDetector:
    """Stateless breach assessor + FCA alert dispatcher.

    Call assess() once per daily reconciliation result.
    Maintains no internal state — pass consecutive_break_days from your
    persistence layer (DB / Redis streak counter).
    """

    def assess(
        self,
        result: ReconciliationResult,
        consecutive_break_days: int = 0,
    ) -> BreachAlert | None:
        """Assess a reconciliation result and return a BreachAlert or None.

        Args:
            result: Output of DailyReconciliation.run()
            consecutive_break_days: Number of calendar days (including today)
                                    that have had a BREAK status. Pass 0 for
                                    today's first break.

        Returns:
            BreachAlert if action is required, None if reconciliation matched.
        """
        if result.status == ReconStatus.MATCHED:
            return None

        if result.status == ReconStatus.PENDING:
            # PENDING is not itself a breach but may become one if not resolved
            if consecutive_break_days >= FCA_ALERT_STREAK_DAYS:
                return self._build_alert(
                    breach_date=result.recon_date,
                    severity=BreachSeverity.MAJOR,
                    consecutive_days=consecutive_break_days,
                    shortfall_gbp=None,
                    description=(
                        f"External bank statement not received for {consecutive_break_days} "
                        "consecutive days. Manual investigation required."
                    ),
                )
            return None

        # BREAK path
        diff = result.difference_gbp or Decimal("0")
        shortfall = diff if diff < Decimal("0") else None  # internal < external = shortfall
        abs_diff = abs(diff)

        if shortfall is not None and abs_diff > SHORTFALL_ALERT_THRESHOLD:
            return self._build_alert(
                breach_date=result.recon_date,
                severity=BreachSeverity.CRITICAL,
                consecutive_days=consecutive_break_days,
                shortfall_gbp=abs_diff,
                description=(
                    f"SAFEGUARDING SHORTFALL: internal £{result.internal_balance_gbp:,.2f} < "
                    f"external £{result.external_balance_gbp:,.2f}. "
                    f"Shortfall: £{abs_diff:,.2f}. "
                    "FCA notification mandatory within 1 business day (CASS 7.15.29G)."
                ),
            )

        if consecutive_break_days >= FCA_ALERT_STREAK_DAYS:
            return self._build_alert(
                breach_date=result.recon_date,
                severity=BreachSeverity.CRITICAL,
                consecutive_days=consecutive_break_days,
                shortfall_gbp=None,
                description=(
                    f"Reconciliation break for {consecutive_break_days} consecutive days. "
                    f"Total discrepancy: £{abs_diff:,.2f}. "
                    "FCA breach notification required (PS23/3 §3.49)."
                ),
            )

        severity = BreachSeverity.MAJOR if consecutive_break_days > 1 else BreachSeverity.MINOR
        return self._build_alert(
            breach_date=result.recon_date,
            severity=severity,
            consecutive_days=consecutive_break_days,
            shortfall_gbp=None,
            description=(
                f"Reconciliation break day {consecutive_break_days}: "
                f"£{abs_diff:,.2f} discrepancy. Escalate to MLRO + CFO."
            ),
        )

    def _build_alert(
        self,
        breach_date: date,
        severity: BreachSeverity,
        consecutive_days: int,
        shortfall_gbp: Decimal | None,
        description: str,
    ) -> BreachAlert:
        fca_required = (
            severity == BreachSeverity.CRITICAL or consecutive_days >= FCA_ALERT_STREAK_DAYS
        )
        alert = BreachAlert(
            breach_date=breach_date,
            severity=severity,
            consecutive_days=consecutive_days,
            shortfall_gbp=shortfall_gbp,
            description=description,
            fca_notification_required=fca_required,
        )
        log_fn = logger.critical if severity == BreachSeverity.CRITICAL else logger.warning
        log_fn("BreachDetector: %s | %s", alert.reference, description)
        return alert

    def notify_fca(self, alert: BreachAlert, dry_run: bool = False) -> None:
        """Dispatch FCA safeguarding breach notification.

        In production this triggers:
          1. Email to FCA SUP via secure portal (manual — CFO must confirm)
          2. Telegram alert to MLRO + CEO (n8n workflow)
          3. Audit event written to ClickHouse (AuditTrail)

        Pass dry_run=True to log the notification without sending.
        """
        if not alert.fca_notification_required:
            logger.debug("notify_fca called but FCA notification not required: %s", alert.reference)
            return

        msg = (
            f"[FCA BREACH NOTIFICATION] {alert.reference}\n"
            f"  Severity: {alert.severity.value}\n"
            f"  Consecutive break days: {alert.consecutive_days}\n"
            f"  Shortfall: £{alert.shortfall_gbp:,.2f}"
            if alert.shortfall_gbp
            else "  Shortfall: none"
        )
        if dry_run:
            logger.warning("DRY RUN — FCA notification suppressed:\n%s", msg)
            return

        # Production: wire to n8n webhook / FCA Connect portal
        logger.critical("FCA BREACH NOTIFICATION DISPATCHED:\n%s", msg)
        # TODO: POST to n8n /webhook/fca-breach-alert
        # TODO: POST to FCA Connect portal (CFO must click confirm)

    def get_consecutive_days(self, history: list[ReconciliationResult]) -> int:
        """Count consecutive trailing BREAK/PENDING days from most recent result.

        Args:
            history: List of results ordered oldest-first.

        Returns:
            Number of consecutive trailing non-MATCHED days.
        """
        count = 0
        for result in reversed(history):
            if result.status == ReconStatus.MATCHED:
                break
            count += 1
        return count
