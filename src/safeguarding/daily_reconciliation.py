"""Daily reconciliation — CASS 7.15.17R.

Compares internal Midaz ledger client-fund total against the external
safeguarding bank balance (fetched from CAMT.053 or bank API stub).

Decision table:
  |difference| ≤ £0.01  → MATCHED   (penny-exact tolerance)
  |difference| > £0.01  → BREAK     (escalate immediately)
  external balance = None → PENDING  (statement not yet received)

Usage:
    recon = DailyReconciliation(internal_balance_gbp=Decimal("50000.00"),
                                 external_balance_gbp=Decimal("49999.99"))
    result = recon.run()
    if result.status == ReconStatus.BREAK:
        ... # hand to BreachDetector
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# CASS 7.15.17R: penny-exact tolerance
RECON_TOLERANCE_GBP = Decimal("0.01")


class ReconStatus(str, Enum):
    MATCHED = "MATCHED"  # |diff| ≤ tolerance — compliant
    BREAK = "BREAK"  # |diff| > tolerance — must escalate
    PENDING = "PENDING"  # external balance not yet received


@dataclass
class ReconciliationResult:
    recon_date: date
    internal_balance_gbp: Decimal
    external_balance_gbp: Decimal | None
    difference_gbp: Decimal | None
    status: ReconStatus
    run_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""

    @property
    def is_compliant(self) -> bool:
        return self.status == ReconStatus.MATCHED

    def summary(self) -> str:
        if self.status == ReconStatus.PENDING:
            return (
                f"[{self.recon_date}] PENDING — external statement not received. "
                f"Internal: £{self.internal_balance_gbp:,.2f}"
            )
        sign = "+" if (self.difference_gbp or Decimal(0)) >= 0 else ""
        return (
            f"[{self.recon_date}] {self.status.value} | "
            f"Internal: £{self.internal_balance_gbp:,.2f} | "
            f"External: £{self.external_balance_gbp:,.2f} | "
            f"Diff: {sign}£{self.difference_gbp:,.2f}"
        )


class DailyReconciliation:
    """Run a single day's CASS 15 reconciliation.

    Args:
        internal_balance_gbp: Sum of all client-fund ledger entries in Midaz
                              (client_funds account type, GBP, minor units → Decimal).
        external_balance_gbp: Closing balance from safeguarding bank CAMT.053
                              statement. Pass None if statement not yet received.
        recon_date: Date being reconciled. Defaults to today.
        tolerance_gbp: Override penny-exact tolerance (tests only).
    """

    def __init__(
        self,
        internal_balance_gbp: Decimal,
        external_balance_gbp: Decimal | None,
        recon_date: date | None = None,
        tolerance_gbp: Decimal = RECON_TOLERANCE_GBP,
    ) -> None:
        self.internal = internal_balance_gbp
        self.external = external_balance_gbp
        self.recon_date = recon_date or date.today()
        self.tolerance = tolerance_gbp

    def run(self) -> ReconciliationResult:
        """Execute the reconciliation and return a ReconciliationResult."""
        if self.external is None:
            logger.warning(
                "CASS recon %s: external balance not received — status PENDING",
                self.recon_date,
            )
            return ReconciliationResult(
                recon_date=self.recon_date,
                internal_balance_gbp=self.internal,
                external_balance_gbp=None,
                difference_gbp=None,
                status=ReconStatus.PENDING,
                notes="External bank statement not yet received.",
            )

        diff = self.internal - self.external
        abs_diff = abs(diff)

        if abs_diff <= self.tolerance:
            status = ReconStatus.MATCHED
            notes = "Reconciliation passed — within penny-exact tolerance."
        else:
            status = ReconStatus.BREAK
            notes = (
                f"Reconciliation break: £{abs_diff:,.2f} exceeds tolerance £{self.tolerance}. "
                "Escalate to MLRO + CFO immediately (CASS 7.15.17R)."
            )

        result = ReconciliationResult(
            recon_date=self.recon_date,
            internal_balance_gbp=self.internal,
            external_balance_gbp=self.external,
            difference_gbp=diff,
            status=status,
            notes=notes,
        )

        log_fn = logger.info if status == ReconStatus.MATCHED else logger.critical
        log_fn("CASS recon: %s", result.summary())
        return result
