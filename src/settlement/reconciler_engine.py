"""Settlement Reconciliation Engine — GAP-010 D-recon (OVERDUE Sprint 9).

Tri-party reconciliation: payment rails ↔ Midaz GL ledger ↔ safeguarding bank.

Architecture
------------
Three `Protocol` ports for dependency injection — the engine never calls
infrastructure directly, so it can be tested with in-memory stubs:

  LedgerPort          → Midaz CBS (GL balance for settlement date)
  SafeguardingBankPort → Barclays/HSBC CAMT.053 closing balance
  PaymentRailsPort    → Hyperswitch / Paymentology settled transaction sum

Three reconciliation legs (all must pass):
  Leg 1: rails_settled_gbp  vs midaz_gl_gbp         (RAILS_VS_LEDGER)
  Leg 2: midaz_gl_gbp       vs safeguarding_bank_gbp  (LEDGER_VS_BANK)
  Leg 3: rails_settled_gbp  vs safeguarding_bank_gbp  (RAILS_VS_BANK)

Tolerance: £1.00 default (CEO decision, D-RECON-DESIGN.md Q3).
CASS 7.15: penny-exact tolerance applies to safeguarding legs in production.

Discrepancy reporting
---------------------
`DiscrepancyReporter` protocol: implement `report(result)` to:
  - write to ClickHouse banxe.settlement_recon_events
  - fire n8n webhook → Telegram/email to MLRO + CFO
  - update BreachDetector streak counter

Daily cron
----------
`ReconcilerCron.run(date)` is the systemd / APScheduler entry point.
Returns exit code: 0=matched, 1=discrepancy, 2=pending, 3=fatal.

CLI:
    python -m src.settlement.reconciler_engine [--date YYYY-MM-DD] [--dry-run]

FCA rules:
    CASS 7.15.17R  — daily reconciliation obligation
    CASS 7.15.29R  — alert within 1 business day
    CASS 15.12.4R  — monthly FIN060 aggregation
    I-24           — Decimal only (never float)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
import json
import logging
import os
import sys
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ── Tolerance ─────────────────────────────────────────────────────────────────
# £1.00 — CEO decision. Override via env RECON_TOLERANCE_GBP.
_DEFAULT_TOLERANCE = Decimal(os.environ.get("RECON_TOLERANCE_GBP", "1.00"))

# ── Exit codes (mirrors cron_daily_recon.py for systemd/monitoring) ──────────
EXIT_MATCHED = 0
EXIT_DISCREPANCY = 1
EXIT_PENDING = 2
EXIT_FATAL = 3


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LedgerBalance:
    """GL balance from Midaz CBS for a given settlement date.

    Attributes:
        settlement_date: Date the balance covers (usually T-1 for end-of-day).
        total_client_funds_gbp: Sum of all client_funds accounts in Midaz.
        total_operational_gbp: Sum of operational accounts (float / float-in-transit).
        currency: ISO-4217 (always GBP for FCA-regulated safeguarding).
        source: Identifier of the Midaz ledger/org used.
    """

    settlement_date: date
    total_client_funds_gbp: Decimal
    total_operational_gbp: Decimal
    currency: str = "GBP"
    source: str = "midaz"

    @property
    def net_position_gbp(self) -> Decimal:
        """client_funds + operational = total Midaz exposure."""
        return self.total_client_funds_gbp + self.total_operational_gbp


@dataclass(frozen=True)
class SafeguardingBalance:
    """Closing balance from external safeguarding bank (CAMT.053 statement).

    Attributes:
        statement_date: Date of the bank statement (must match settlement_date).
        closing_balance_gbp: Ledger balance from CAMT.053 CLBD tag.
        available_balance_gbp: Available balance (ITAV / CLAV) — may differ if
                               holds are applied by the bank.
        account_iban: Safeguarding account IBAN (Barclays/HSBC).
        source_file: CAMT.053 filename for audit traceability.
    """

    statement_date: date
    closing_balance_gbp: Decimal
    available_balance_gbp: Decimal
    account_iban: str = ""
    source_file: str = ""
    currency: str = "GBP"


@dataclass(frozen=True)
class RailsBalance:
    """Settled transaction total from payment rails (Hyperswitch + Paymentology).

    Attributes:
        settlement_date: Date of settlement (T-1 for next-day settlement rails).
        total_settled_gbp: Sum of all settled transaction amounts in GBP.
        total_refunded_gbp: Sum of refunds / chargebacks settled on this date.
        transaction_count: Number of settled transactions.
        source: 'hyperswitch' | 'paymentology' | 'combined'.
    """

    settlement_date: date
    total_settled_gbp: Decimal
    total_refunded_gbp: Decimal = Decimal("0")
    transaction_count: int = 0
    source: str = "combined"

    @property
    def net_settled_gbp(self) -> Decimal:
        """Net settled = gross settled minus refunds/chargebacks."""
        return self.total_settled_gbp - self.total_refunded_gbp


class ReconLeg(str, Enum):
    """Which pair of sources is being compared in a tri-party reconciliation."""

    RAILS_VS_LEDGER = "RAILS_VS_LEDGER"  # Leg 1: payment rails vs Midaz GL
    LEDGER_VS_BANK = "LEDGER_VS_BANK"  # Leg 2: Midaz GL vs safeguarding bank
    RAILS_VS_BANK = "RAILS_VS_BANK"  # Leg 3: payment rails vs safeguarding bank


class TriPartyStatus(str, Enum):
    MATCHED = "MATCHED"  # All three legs within tolerance — compliant
    DISCREPANCY = "DISCREPANCY"  # One or more legs exceed tolerance — escalate
    PENDING = "PENDING"  # One or more data sources not yet available
    FATAL = "FATAL"  # Infrastructure failure — cannot determine status


@dataclass
class LegResult:
    """Result for one reconciliation leg."""

    leg: ReconLeg
    left_gbp: Decimal
    right_gbp: Decimal
    difference_gbp: Decimal
    tolerance_gbp: Decimal
    status: str  # MATCHED | DISCREPANCY | PENDING
    note: str = ""

    @property
    def abs_difference(self) -> Decimal:
        return abs(self.difference_gbp)


@dataclass
class TriPartyResult:
    """Complete tri-party reconciliation result for one settlement date.

    Attributes:
        settlement_date: The date this result covers.
        ledger: Midaz GL balance snapshot.
        safeguarding: External bank balance (None if CAMT.053 not received).
        rails: Payment rails balance snapshot.
        legs: Results for each of the three comparison legs.
        overall_status: Worst-case status across all three legs.
        run_at: UTC timestamp of this reconciliation run.
    """

    settlement_date: date
    ledger: LedgerBalance
    safeguarding: SafeguardingBalance | None
    rails: RailsBalance
    legs: list[LegResult] = field(default_factory=list)
    overall_status: TriPartyStatus = TriPartyStatus.PENDING
    run_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def summary(self) -> str:
        lines = [
            f"[{self.settlement_date}] TRI-PARTY RECON — {self.overall_status.value}",
            f"  Rails net:       £{self.rails.net_settled_gbp:>14,.2f}  ({self.rails.transaction_count} txns)",
            f"  Midaz GL:        £{self.ledger.total_client_funds_gbp:>14,.2f}",
        ]
        if self.safeguarding:
            lines.append(
                f"  Safeguarding:    £{self.safeguarding.closing_balance_gbp:>14,.2f}  ({self.safeguarding.source_file})"
            )
        else:
            lines.append("  Safeguarding:    PENDING (CAMT.053 not received)")
        for leg in self.legs:
            marker = (
                "✅" if leg.status == "MATCHED" else ("⏳" if leg.status == "PENDING" else "❌")
            )
            lines.append(
                f"  {marker} {leg.leg.value}: diff £{leg.difference_gbp:+,.2f}  → {leg.status}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "settlement_date": self.settlement_date.isoformat(),
            "run_at": self.run_at.isoformat(),
            "overall_status": self.overall_status.value,
            "rails_net_gbp": str(self.rails.net_settled_gbp),
            "rails_transaction_count": self.rails.transaction_count,
            "midaz_client_funds_gbp": str(self.ledger.total_client_funds_gbp),
            "midaz_operational_gbp": str(self.ledger.total_operational_gbp),
            "safeguarding_closing_gbp": str(self.safeguarding.closing_balance_gbp)
            if self.safeguarding
            else None,
            "safeguarding_source_file": self.safeguarding.source_file
            if self.safeguarding
            else None,
            "legs": [
                {
                    "leg": leg.leg.value,
                    "left_gbp": str(leg.left_gbp),
                    "right_gbp": str(leg.right_gbp),
                    "difference_gbp": str(leg.difference_gbp),
                    "status": leg.status,
                    "note": leg.note,
                }
                for leg in self.legs
            ],
        }


# ── Ports (dependency injection via Protocol) ─────────────────────────────────


@runtime_checkable
class LedgerPort(Protocol):
    """Fetch GL balances from Midaz CBS for a given settlement date."""

    def get_gl_balance(self, settlement_date: date) -> LedgerBalance: ...


@runtime_checkable
class SafeguardingBankPort(Protocol):
    """Fetch external safeguarding bank balance from CAMT.053 statement."""

    def get_closing_balance(self, statement_date: date) -> SafeguardingBalance | None:
        """Return None if the CAMT.053 statement has not been received yet."""
        ...


@runtime_checkable
class PaymentRailsPort(Protocol):
    """Fetch settled transaction totals from payment rails (Hyperswitch + Paymentology)."""

    def get_settled_total(self, settlement_date: date) -> RailsBalance: ...


@runtime_checkable
class DiscrepancyReporter(Protocol):
    """Report reconciliation results (ClickHouse, n8n, audit trail)."""

    def report(self, result: TriPartyResult) -> None: ...


# ── No-op reporter (tests / dry-run) ─────────────────────────────────────────


class NullDiscrepancyReporter:
    """No-op reporter. Logs to stdout only. Use in dry-run and tests."""

    def report(self, result: TriPartyResult) -> None:
        log_fn = logger.warning if result.overall_status != TriPartyStatus.MATCHED else logger.info
        log_fn("NullReporter: %s", result.summary())


# ── ClickHouse reporter ───────────────────────────────────────────────────────


class ClickHouseDiscrepancyReporter:
    """Write tri-party reconciliation results to ClickHouse.

    Table: banxe.settlement_recon_events
    Created by ensure_schema() — call once at startup.
    """

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS banxe.settlement_recon_events
    (
        event_id          UUID            DEFAULT generateUUIDv4(),
        recorded_at       DateTime64(3, 'UTC') DEFAULT now64(),
        settlement_date   Date,
        overall_status    LowCardinality(String),
        rails_net_gbp     Decimal(18, 2),
        rails_txn_count   UInt32,
        midaz_cf_gbp      Decimal(18, 2),
        midaz_op_gbp      Decimal(18, 2),
        bank_closing_gbp  Nullable(Decimal(18, 2)),
        bank_source_file  String,
        legs_json         String
    )
    ENGINE = MergeTree
    PARTITION BY toYYYYMM(settlement_date)
    ORDER BY (settlement_date, recorded_at)
    TTL settlement_date + INTERVAL 5 YEAR
    SETTINGS index_granularity = 8192
    """.strip()

    def __init__(
        self, clickhouse_url: str = "http://localhost:8123", database: str = "banxe"
    ) -> None:
        self.url = clickhouse_url.rstrip("/")
        self.database = database

    def report(self, result: TriPartyResult) -> None:
        try:
            import httpx
        except ImportError:
            logger.error(
                "ClickHouseDiscrepancyReporter: httpx not installed — falling back to stderr"
            )
            logger.critical("RECON EVENT: %s", json.dumps(result.to_dict()))
            return

        import json as _json

        legs_json = _json.dumps(
            [
                {"leg": lr.leg.value, "diff": str(lr.difference_gbp), "status": lr.status}
                for lr in result.legs
            ]
        )

        bank_gbp = str(result.safeguarding.closing_balance_gbp) if result.safeguarding else "\\N"
        bank_file = (result.safeguarding.source_file if result.safeguarding else "").replace(
            "'", "''"
        )

        row = (
            f"('{result.settlement_date.isoformat()}', "
            f"'{result.overall_status.value}', "
            f"{result.rails.net_settled_gbp}, "
            f"{result.rails.transaction_count}, "
            f"{result.ledger.total_client_funds_gbp}, "
            f"{result.ledger.total_operational_gbp}, "
            f"{bank_gbp}, "
            f"'{bank_file}', "
            f"'{legs_json.replace(chr(39), chr(39) * 2)}')"
        )
        sql = (
            f"INSERT INTO {self.database}.settlement_recon_events "  # nosec B608  # noqa: S608
            f"(settlement_date, overall_status, rails_net_gbp, rails_txn_count, "
            f"midaz_cf_gbp, midaz_op_gbp, bank_closing_gbp, bank_source_file, legs_json) "
            f"VALUES {row}"
        )
        try:
            resp = httpx.post(self.url, params={"query": sql}, timeout=5.0)
            resp.raise_for_status()
        except Exception as exc:
            logger.error(
                "ClickHouseDiscrepancyReporter: insert failed: %s — event logged to stderr", exc
            )
            logger.critical("RECON EVENT: %s", json.dumps(result.to_dict()))

    def ensure_schema(self) -> None:
        try:
            import httpx

            resp = httpx.post(self.url, params={"query": self._CREATE_SQL}, timeout=10.0)
            resp.raise_for_status()
            logger.info("settlement_recon_events table ensured")
        except Exception as exc:
            logger.error("ensure_schema failed: %s", exc)


# ── Core engine ───────────────────────────────────────────────────────────────


class TriPartyReconciler:
    """Tri-party reconciliation engine.

    Compares three legs:
      Leg 1 (RAILS_VS_LEDGER):  rails.net_settled == ledger.total_client_funds
      Leg 2 (LEDGER_VS_BANK):   ledger.total_client_funds == safeguarding.closing_balance
      Leg 3 (RAILS_VS_BANK):    rails.net_settled == safeguarding.closing_balance

    Args:
        ledger_port: Midaz GL balance provider.
        bank_port:   Safeguarding bank CAMT.053 provider.
        rails_port:  Payment rails settled transaction provider.
        reporter:    Discrepancy reporter (ClickHouse + n8n).
        tolerance:   Maximum allowed difference to still count as MATCHED (GBP).
    """

    def __init__(
        self,
        ledger_port: LedgerPort,
        bank_port: SafeguardingBankPort,
        rails_port: PaymentRailsPort,
        reporter: DiscrepancyReporter,
        tolerance: Decimal = _DEFAULT_TOLERANCE,
    ) -> None:
        self._ledger = ledger_port
        self._bank = bank_port
        self._rails = rails_port
        self._reporter = reporter
        self._tolerance = tolerance

    def reconcile(self, settlement_date: date) -> TriPartyResult:
        """Run tri-party reconciliation for settlement_date.

        Steps:
          1. Fetch balances from all three sources.
          2. Compare each pair (three legs).
          3. Determine overall status (worst-case across legs).
          4. Call reporter.report() regardless of status.
          5. Return TriPartyResult.
        """
        logger.info(
            "TriPartyReconciler: starting reconciliation for %s (tolerance=£%s)",
            settlement_date,
            self._tolerance,
        )

        ledger = self._ledger.get_gl_balance(settlement_date)
        safeguarding = self._bank.get_closing_balance(settlement_date)
        rails = self._rails.get_settled_total(settlement_date)

        legs = self._compare_legs(ledger, safeguarding, rails)
        overall = self._overall_status(legs)

        result = TriPartyResult(
            settlement_date=settlement_date,
            ledger=ledger,
            safeguarding=safeguarding,
            rails=rails,
            legs=legs,
            overall_status=overall,
        )

        log_fn = logger.critical if overall == TriPartyStatus.DISCREPANCY else logger.info
        log_fn("TriPartyReconciler: %s", result.summary())

        self._reporter.report(result)
        return result

    def _compare_legs(
        self,
        ledger: LedgerBalance,
        safeguarding: SafeguardingBalance | None,
        rails: RailsBalance,
    ) -> list[LegResult]:
        legs: list[LegResult] = []

        # Leg 1: payment rails vs Midaz GL
        legs.append(
            self._leg(
                leg=ReconLeg.RAILS_VS_LEDGER,
                left=rails.net_settled_gbp,
                right=ledger.total_client_funds_gbp,
                left_label="rails_net_settled",
                right_label="midaz_client_funds",
            )
        )

        # Legs 2 + 3 require safeguarding bank statement
        if safeguarding is None:
            legs.append(
                LegResult(
                    leg=ReconLeg.LEDGER_VS_BANK,
                    left_gbp=ledger.total_client_funds_gbp,
                    right_gbp=Decimal("0"),
                    difference_gbp=Decimal("0"),
                    tolerance_gbp=self._tolerance,
                    status="PENDING",
                    note="CAMT.053 statement not yet received from safeguarding bank.",
                )
            )
            legs.append(
                LegResult(
                    leg=ReconLeg.RAILS_VS_BANK,
                    left_gbp=rails.net_settled_gbp,
                    right_gbp=Decimal("0"),
                    difference_gbp=Decimal("0"),
                    tolerance_gbp=self._tolerance,
                    status="PENDING",
                    note="CAMT.053 statement not yet received from safeguarding bank.",
                )
            )
        else:
            # Leg 2: Midaz GL vs safeguarding bank
            legs.append(
                self._leg(
                    leg=ReconLeg.LEDGER_VS_BANK,
                    left=ledger.total_client_funds_gbp,
                    right=safeguarding.closing_balance_gbp,
                    left_label="midaz_client_funds",
                    right_label="safeguarding_closing",
                )
            )

            # Leg 3: payment rails vs safeguarding bank
            legs.append(
                self._leg(
                    leg=ReconLeg.RAILS_VS_BANK,
                    left=rails.net_settled_gbp,
                    right=safeguarding.closing_balance_gbp,
                    left_label="rails_net_settled",
                    right_label="safeguarding_closing",
                )
            )

        return legs

    def _leg(
        self,
        leg: ReconLeg,
        left: Decimal,
        right: Decimal,
        left_label: str,
        right_label: str,
    ) -> LegResult:
        diff = left - right
        abs_diff = abs(diff)
        matched = abs_diff <= self._tolerance
        status = "MATCHED" if matched else "DISCREPANCY"

        note = (
            ""
            if matched
            else (
                f"{left_label}=£{left:,.2f} vs {right_label}=£{right:,.2f} "
                f"→ difference £{diff:+,.2f} exceeds tolerance £{self._tolerance}. "
                "Escalate to MLRO + CFO (CASS 7.15.29R)."
            )
        )

        if not matched:
            logger.warning("Recon leg %s: %s", leg.value, note)

        return LegResult(
            leg=leg,
            left_gbp=left,
            right_gbp=right,
            difference_gbp=diff,
            tolerance_gbp=self._tolerance,
            status=status,
            note=note,
        )

    @staticmethod
    def _overall_status(legs: list[LegResult]) -> TriPartyStatus:
        statuses = {leg.status for leg in legs}
        if "DISCREPANCY" in statuses:
            return TriPartyStatus.DISCREPANCY
        if "PENDING" in statuses:
            return TriPartyStatus.PENDING
        return TriPartyStatus.MATCHED


# ── Cron wrapper ──────────────────────────────────────────────────────────────


class ReconcilerCron:
    """Daily cron entry point for systemd / APScheduler.

    Returns integer exit code:
      0 — all legs MATCHED
      1 — at least one DISCREPANCY (escalate to MLRO within 1 business day)
      2 — at least one PENDING (normal for sandbox / weekends)
      3 — infrastructure FATAL (page on-call immediately)
    """

    def __init__(
        self,
        ledger_port: LedgerPort,
        bank_port: SafeguardingBankPort,
        rails_port: PaymentRailsPort,
        reporter: DiscrepancyReporter,
        tolerance: Decimal = _DEFAULT_TOLERANCE,
    ) -> None:
        self._engine = TriPartyReconciler(
            ledger_port=ledger_port,
            bank_port=bank_port,
            rails_port=rails_port,
            reporter=reporter,
            tolerance=tolerance,
        )

    def run(self, settlement_date: date | None = None, output_json: bool = False) -> int:
        """Execute daily reconciliation. Returns exit code."""
        settlement_date = settlement_date or date.today()

        try:
            result = self._engine.reconcile(settlement_date)
        except Exception as exc:
            logger.critical("ReconcilerCron FATAL: %s", exc, exc_info=True)
            return EXIT_FATAL

        if output_json:
            print(json.dumps(result.to_dict(), indent=2))

        if result.overall_status == TriPartyStatus.DISCREPANCY:
            logger.warning(
                "CASS 7.15.29R: discrepancy on %s — MLRO must investigate within 1 business day",
                settlement_date,
            )
            return EXIT_DISCREPANCY

        if result.overall_status == TriPartyStatus.PENDING:
            logger.info("Recon PENDING for %s — non-critical in sandbox/weekend", settlement_date)
            return EXIT_PENDING

        logger.info("Recon MATCHED for %s — safeguarding requirement satisfied", settlement_date)
        return EXIT_MATCHED


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_stub_cron(dry_run: bool) -> ReconcilerCron:
    """Build a ReconcilerCron with in-memory stub ports for CLI / dev.

    Production wiring is done by the service initialisation layer
    (api/main.py or a dedicated runner script), not here.
    """
    from decimal import Decimal as D

    class _StubLedger:
        def get_gl_balance(self, settlement_date: date) -> LedgerBalance:
            return LedgerBalance(
                settlement_date=settlement_date,
                total_client_funds_gbp=D("0"),
                total_operational_gbp=D("0"),
                source="stub",
            )

    class _StubBank:
        def get_closing_balance(self, statement_date: date) -> SafeguardingBalance | None:
            return None  # PENDING — no bank statement in stub

    class _StubRails:
        def get_settled_total(self, settlement_date: date) -> RailsBalance:
            return RailsBalance(
                settlement_date=settlement_date,
                total_settled_gbp=D("0"),
                source="stub",
            )

    return ReconcilerCron(
        ledger_port=_StubLedger(),
        bank_port=_StubBank(),
        rails_port=_StubRails(),
        reporter=NullDiscrepancyReporter(),
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Banxe Settlement Reconciliation Engine (GAP-010 D-recon)"
    )
    p.add_argument("--date", metavar="YYYY-MM-DD", help="Settlement date (default: today)")
    p.add_argument("--dry-run", action="store_true", help="Stub ports, no ClickHouse writes")
    p.add_argument("--json", action="store_true", dest="output_json", help="Output JSON summary")
    args = p.parse_args()

    settlement_date: date | None = None
    if args.date:
        try:
            settlement_date = date.fromisoformat(args.date)
        except ValueError:
            logger.error("Invalid date: %s (expected YYYY-MM-DD)", args.date)
            return EXIT_FATAL

    cron = _build_stub_cron(dry_run=args.dry_run)
    return cron.run(settlement_date=settlement_date, output_json=args.output_json)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    sys.exit(main())
