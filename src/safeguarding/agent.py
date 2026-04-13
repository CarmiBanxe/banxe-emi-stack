"""SafeguardingAgent — CASS 15 daily orchestrator (GAP-051).

Wires together the four safeguarding modules into a single daily workflow:

  Step 1: Fetch Midaz ledger balance (via LedgerBalancePort)
  Step 2: Fetch external bank CAMT.053 balance (via BankStatementPort)
  Step 3: Run DailyReconciliation → ReconStatus
  Step 4: Feed result to BreachDetector with streak counter
  Step 5: Log AuditEvent (always — immutable compliance record)
  Step 6: If BreachAlert raised: dispatch FCA notification
  Step 7: Return SafeguardingRunResult for cron exit code

The agent is stateless — streak counts are passed in from the caller's
persistence layer (ClickHouse streak query or Redis counter).

FCA rules:
  CASS 7.15.17R  — daily internal reconciliation
  CASS 7.15.29R  — alert within 1 business day
  CASS 15.12.4R  — monthly FIN060 return
  PS23/3 §3.49   — breach notification from 7 May 2026

Usage (cron / systemd):
    from src.safeguarding.agent import SafeguardingAgent, SafeguardingAgentPorts

    ports = SafeguardingAgentPorts(
        ledger=MidazLedgerPort(),
        bank=BarclaysCAMT053Port(),
        audit=AuditTrail(clickhouse_url=..., dry_run=False),
        streak_counter=ClickHouseStreakCounter(),
    )
    agent = SafeguardingAgent(ports)
    result = agent.run(date.today())
    sys.exit(result.exit_code)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from typing import Protocol, runtime_checkable

from .audit_trail import AuditEvent, AuditTrail
from .breach_detector import BreachAlert, BreachDetector
from .daily_reconciliation import DailyReconciliation, ReconciliationResult, ReconStatus

logger = logging.getLogger(__name__)

# Systemd / cron exit codes
EXIT_MATCHED = 0
EXIT_BREACH = 1
EXIT_PENDING = 2
EXIT_FATAL = 3


# ── Ports ──────────────────────────────────────────────────────────────────────


@runtime_checkable
class LedgerBalancePort(Protocol):
    """Fetch total client-fund balance from Midaz CBS."""

    def get_client_funds_gbp(self, as_of: date) -> Decimal: ...


@runtime_checkable
class BankStatementPort(Protocol):
    """Fetch safeguarding bank closing balance from CAMT.053 statement."""

    def get_closing_balance_gbp(self, statement_date: date) -> Decimal | None:
        """Return None if CAMT.053 not yet received (PENDING)."""
        ...


@runtime_checkable
class StreakCounterPort(Protocol):
    """Return consecutive break-day count for streak-based breach detection."""

    def get_streak(self, as_of: date) -> int: ...

    def reset_streak(self, as_of: date) -> None: ...


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class SafeguardingAgentPorts:
    """Dependency container passed to SafeguardingAgent."""

    ledger: LedgerBalancePort
    bank: BankStatementPort
    audit: AuditTrail
    streak_counter: StreakCounterPort


@dataclass
class SafeguardingRunResult:
    """Result of one daily SafeguardingAgent run.

    Attributes:
        run_date: Date the reconciliation covers.
        recon_result: DailyReconciliation output.
        breach_alert: BreachAlert if raised (None if MATCHED/PENDING without streak).
        audit_event_id: ID of the AuditEvent written to ClickHouse.
        exit_code: 0=MATCHED, 1=BREACH, 2=PENDING, 3=FATAL.
        run_at: UTC timestamp of this run.
    """

    run_date: date
    recon_result: ReconciliationResult | None
    breach_alert: BreachAlert | None
    audit_event_id: str
    exit_code: int
    run_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def status_label(self) -> str:
        if self.exit_code == EXIT_MATCHED:
            return "MATCHED"
        if self.exit_code == EXIT_BREACH:
            return "BREACH"
        if self.exit_code == EXIT_PENDING:
            return "PENDING"
        return "FATAL"

    def summary(self) -> str:
        lines = [f"[{self.run_date}] SafeguardingAgent → {self.status_label}"]
        if self.recon_result:
            lines.append(f"  Recon: {self.recon_result.summary()}")
        if self.breach_alert:
            lines.append(
                f"  Breach: {self.breach_alert.reference} "
                f"severity={self.breach_alert.severity.value} "
                f"fca_required={self.breach_alert.fca_notification_required}"
            )
        lines.append(f"  Audit event: {self.audit_event_id}")
        return "\n".join(lines)


# ── Agent ──────────────────────────────────────────────────────────────────────


class SafeguardingAgent:
    """CASS 15 daily safeguarding orchestrator.

    Args:
        ports:        Dependency container (LedgerPort, BankPort, AuditTrail, StreakCounter).
        fca_notify:   If True, call BreachDetector.notify_fca() for CRITICAL alerts.
                      Set False in dry-run / sandbox.
        detector:     Override BreachDetector instance (for testing).
    """

    def __init__(
        self,
        ports: SafeguardingAgentPorts,
        fca_notify: bool = False,
        detector: BreachDetector | None = None,
    ) -> None:
        self._ports = ports
        self._fca_notify = fca_notify
        self._detector = detector or BreachDetector()

    def run(self, run_date: date | None = None) -> SafeguardingRunResult:
        """Execute the daily safeguarding workflow.

        Never raises — all exceptions are caught and returned as EXIT_FATAL.
        """
        run_date = run_date or date.today()
        logger.info("SafeguardingAgent: starting run for %s", run_date)

        try:
            return self._run_internal(run_date)
        except Exception as exc:
            logger.critical("SafeguardingAgent FATAL: %s", exc, exc_info=True)
            event = AuditEvent(
                event_type="AGENT_FATAL",
                entity_id=f"safeguarding-{run_date.isoformat()}",
                actor="SafeguardingAgent",
                payload={"error": str(exc), "run_date": run_date.isoformat()},
                severity="CRITICAL",
            )
            self._ports.audit.log(event)
            return SafeguardingRunResult(
                run_date=run_date,
                recon_result=None,
                breach_alert=None,
                audit_event_id=event.event_id,
                exit_code=EXIT_FATAL,
            )

    def _run_internal(self, run_date: date) -> SafeguardingRunResult:
        # Step 1: Fetch balances
        internal_balance = self._ports.ledger.get_client_funds_gbp(run_date)
        external_balance = self._ports.bank.get_closing_balance_gbp(run_date)

        # Step 2: Reconcile
        recon = DailyReconciliation(
            internal_balance_gbp=internal_balance,
            external_balance_gbp=external_balance,
            recon_date=run_date,
        )
        result = recon.run()

        # Step 3: Streak + breach detection
        streak = self._ports.streak_counter.get_streak(run_date)
        breach_alert = self._detector.assess(result, consecutive_break_days=streak)

        # Step 4: Audit event (always written)
        severity = (
            "CRITICAL"
            if breach_alert and breach_alert.fca_notification_required
            else ("WARNING" if result.status != ReconStatus.MATCHED else "INFO")
        )
        event = AuditEvent(
            event_type=f"RECON_{result.status.value}",
            entity_id=f"safeguarding-{run_date.isoformat()}",
            actor="SafeguardingAgent",
            payload={
                "recon_date": run_date.isoformat(),
                "recon_status": result.status.value,
                "internal_balance_gbp": str(internal_balance),
                "external_balance_gbp": str(external_balance)
                if external_balance is not None
                else None,
                "difference_gbp": str(result.difference_gbp)
                if result.difference_gbp is not None
                else None,
                "consecutive_break_days": streak,
                "breach_severity": breach_alert.severity.value if breach_alert else None,
                "fca_notification_required": breach_alert.fca_notification_required
                if breach_alert
                else False,
            },
            severity=severity,
        )
        self._ports.audit.log(event)

        # Step 5: FCA notification if needed
        if breach_alert and self._fca_notify:
            self._detector.notify_fca(breach_alert, dry_run=False)
        elif breach_alert and breach_alert.fca_notification_required:
            logger.warning(
                "SafeguardingAgent: FCA notification required but fca_notify=False "
                "(sandbox/dry-run). Breach: %s",
                breach_alert.reference,
            )

        # Step 6: Reset streak if matched
        if result.status == ReconStatus.MATCHED:
            self._ports.streak_counter.reset_streak(run_date)

        # Step 7: Exit code
        if breach_alert and breach_alert.fca_notification_required:
            exit_code = EXIT_BREACH
        elif result.status == ReconStatus.PENDING:
            exit_code = EXIT_PENDING
        elif result.status == ReconStatus.BREAK and breach_alert:
            exit_code = EXIT_BREACH
        else:
            exit_code = EXIT_MATCHED

        run_result = SafeguardingRunResult(
            run_date=run_date,
            recon_result=result,
            breach_alert=breach_alert,
            audit_event_id=event.event_id,
            exit_code=exit_code,
        )
        log_fn = logger.critical if exit_code == EXIT_BREACH else logger.info
        log_fn("SafeguardingAgent: %s", run_result.summary())
        return run_result


# ── In-memory stubs for testing ───────────────────────────────────────────────


class StubLedgerPort:
    """Stub returning a fixed Midaz balance. Use in tests and dry-run."""

    def __init__(self, balance_gbp: Decimal = Decimal("100000")) -> None:
        self._balance = balance_gbp

    def get_client_funds_gbp(self, as_of: date) -> Decimal:
        return self._balance


class StubBankStatementPort:
    """Stub returning a fixed (or None) bank balance. Use in tests and dry-run."""

    def __init__(self, balance_gbp: Decimal | None = Decimal("100000")) -> None:
        self._balance = balance_gbp

    def get_closing_balance_gbp(self, statement_date: date) -> Decimal | None:
        return self._balance


class InMemoryStreakCounter:
    """In-memory streak counter. Use in tests and dry-run."""

    def __init__(self, initial_streak: int = 0) -> None:
        self._streak = initial_streak

    def get_streak(self, as_of: date) -> int:
        return self._streak

    def reset_streak(self, as_of: date) -> None:
        self._streak = 0
