"""Three-leg safeguarding tie-out (CASS 15) — D-RECON-BUILD-SPEC §3 (3-leg model).

Extends the existing two-leg CASS 15 reconciliation (internal Midaz ledger vs
safeguarding bank account, see ``daily_reconciliation.py``) with a THIRD leg —
the payment-rail / operational bank balance — and a full A == B == C tie-out:

  * Leg A — internal Midaz ledger client-fund total   (LedgerBalancePort, agent.py)
  * Leg B — safeguarding bank account closing balance  (BankStatementPort, agent.py)
  * Leg C — payment-rail / operational bank balance    (RailBalancePort, THIS module)

The comparison MECHANICS are reused from ``src.recon_core`` (no duplication):
each leg-pair is classified by the shared ``BreachEvaluator`` with the CASS 15
penny-exact threshold (£0.01, ``breach_kind="BREAK"``) — thresholds remain a
per-regime INPUT, never unified (S6.2 / ADR-SAF-01).

Leg B (safeguarding account) already has a port — ``BankStatementPort`` in
``agent.py`` — and is NOT redefined here (ADR-102): this module adds only the
missing Leg C port and the 3-leg tie-out.

Pure + offline: ``three_leg_reconcile`` takes raw Decimal balances (mirroring
``DailyReconciliation``); ``RailBalancePort`` is the Leg-C source seam, wired by
the orchestrator. Invariant I-01: Decimal money only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from src.recon_core import BreachEvaluator, CoreReconResult, evaluate_balances

# CASS 15 penny-exact tolerance (matches daily_reconciliation.RECON_TOLERANCE_GBP).
RECON_TOLERANCE_GBP = Decimal("0.01")


@runtime_checkable
class RailBalancePort(Protocol):
    """Fetch the payment-rail / operational bank balance (Leg C)."""

    def get_rail_balance_gbp(self, as_of: date) -> Decimal | None:
        """Return the rail/bank balance, or None if not yet available (PENDING)."""
        ...


class InMemoryRailBalancePort:
    """Offline Leg-C stub: configurable rail balances by date (tests / sandbox)."""

    def __init__(self, balances: dict[date, Decimal] | None = None) -> None:
        self._balances: dict[date, Decimal] = dict(balances or {})

    def set_balance(self, as_of: date, balance: Decimal) -> None:
        self._balances[as_of] = balance

    def get_rail_balance_gbp(self, as_of: date) -> Decimal | None:
        return self._balances.get(as_of)


class ThreeLegStatus(str, Enum):
    MATCHED = "MATCHED"  # all three legs tie out within tolerance
    BREAK = "BREAK"  # at least one leg-pair exceeds tolerance — escalate
    PENDING = "PENDING"  # Leg B or Leg C not yet available


@dataclass(frozen=True)
class ThreeLegResult:
    """Outcome of an A == B == C safeguarding tie-out (I-01 Decimal)."""

    recon_date: date
    leg_a_ledger: Decimal
    leg_b_safeguarding: Decimal | None
    leg_c_rail: Decimal | None
    a_vs_b: CoreReconResult | None
    b_vs_c: CoreReconResult | None
    a_vs_c: CoreReconResult | None
    status: ThreeLegStatus
    # Shortfall (CASS 15 escalation trigger): client-fund ledger (A) exceeds the
    # safeguarding account (B) beyond tolerance ⇒ client funds not fully safeguarded.
    shortfall: bool
    run_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""

    @property
    def is_compliant(self) -> bool:
        return self.status == ThreeLegStatus.MATCHED


def three_leg_reconcile(
    leg_a_ledger: Decimal,
    leg_b_safeguarding: Decimal | None,
    leg_c_rail: Decimal | None,
    *,
    recon_date: date | None = None,
    tolerance: Decimal = RECON_TOLERANCE_GBP,
) -> ThreeLegResult:
    """Tie out A (ledger) == B (safeguarding) == C (rail) within ``tolerance``.

    Returns PENDING if Leg B or Leg C is not yet available. Otherwise classifies
    each leg-pair via the shared CASS 15 ``BreachEvaluator`` (£0.01 "BREAK") and
    is BREAK if ANY pair exceeds tolerance. The signed A−B difference is used to
    flag a *shortfall* (client funds under-safeguarded) distinct from a surplus.
    """
    recon_date = recon_date or date.today()

    if leg_b_safeguarding is None or leg_c_rail is None:
        missing = "safeguarding account" if leg_b_safeguarding is None else "payment rail"
        return ThreeLegResult(
            recon_date=recon_date,
            leg_a_ledger=leg_a_ledger,
            leg_b_safeguarding=leg_b_safeguarding,
            leg_c_rail=leg_c_rail,
            a_vs_b=None,
            b_vs_c=None,
            a_vs_c=None,
            status=ThreeLegStatus.PENDING,
            shortfall=False,
            notes=f"Leg balance not yet available ({missing}).",
        )

    evaluator = BreachEvaluator(threshold=tolerance, breach_kind="BREAK")
    a_vs_b = evaluate_balances(leg_a_ledger, leg_b_safeguarding, evaluator)
    b_vs_c = evaluate_balances(leg_b_safeguarding, leg_c_rail, evaluator)
    a_vs_c = evaluate_balances(leg_a_ledger, leg_c_rail, evaluator)

    any_breach = a_vs_b.is_breach or b_vs_c.is_breach or a_vs_c.is_breach
    status = ThreeLegStatus.BREAK if any_breach else ThreeLegStatus.MATCHED
    # Shortfall iff ledger (A) > safeguarding (B) beyond tolerance (signed A−B).
    shortfall = a_vs_b.difference > tolerance

    if status == ThreeLegStatus.MATCHED:
        notes = "Three-leg tie-out passed — A == B == C within tolerance."
    elif shortfall:
        notes = (
            "Three-leg BREAK with SHORTFALL: client-fund ledger exceeds safeguarding "
            "account — funds not fully safeguarded. Escalate to MLRO + CFO (CASS 15)."
        )
    else:
        notes = "Three-leg BREAK: a leg-pair exceeds tolerance. Escalate (CASS 15)."

    return ThreeLegResult(
        recon_date=recon_date,
        leg_a_ledger=leg_a_ledger,
        leg_b_safeguarding=leg_b_safeguarding,
        leg_c_rail=leg_c_rail,
        a_vs_b=a_vs_b,
        b_vs_c=b_vs_c,
        a_vs_c=a_vs_c,
        status=status,
        shortfall=shortfall,
        notes=notes,
    )
