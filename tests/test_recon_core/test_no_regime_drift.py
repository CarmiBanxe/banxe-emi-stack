"""No-regime-drift contract — the two CASS thresholds stay DISTINCT.

S6.2 extracts shared *mechanics* but deliberately does NOT unify the two
regulatory regimes. This test fails loudly if anyone later collapses the
£0.01 (CASS 15 aggregate penny-exact) and £100 (CASS 7.15 line-item HITL)
thresholds into one rule.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.recon_core import BreachEvaluator
from src.safeguarding.daily_reconciliation import (
    RECON_TOLERANCE_GBP,
    DailyReconciliation,
    ReconStatus,
)

from services.recon.recon_agent import ReconAgent
from services.recon.reconciliation_engine_v2 import (
    BREACH_HITL_THRESHOLD,
    HITLProposal,
    InMemoryReconStore,
    ReconciliationReport,
    StatementEntry,
)


def _stmt(iban, amount):
    return StatementEntry(
        entry_id="e",
        account_iban=iban,
        amount=Decimal(amount),
        currency="GBP",
        value_date="2026-04-21",
        description="d",
        transaction_ref="REF",
    )


def test_thresholds_are_distinct_and_unchanged():
    # The two regimes keep their own, different thresholds — NOT unified.
    assert Decimal("0.01") == RECON_TOLERANCE_GBP  # CASS 15 aggregate penny-exact
    assert Decimal("100") == BREACH_HITL_THRESHOLD  # CASS 7.15 line-item HITL
    assert RECON_TOLERANCE_GBP != BREACH_HITL_THRESHOLD


def test_cass15_still_breaks_at_one_penny_not_below():
    # CASS 15: MATCHED at exactly £0.01, BREAK just above.
    matched = DailyReconciliation(
        Decimal("50000.00"), Decimal("49999.99"), recon_date=date(2026, 4, 13)
    ).run()
    broken = DailyReconciliation(
        Decimal("50000.00"), Decimal("49999.98"), recon_date=date(2026, 4, 13)
    ).run()
    assert matched.status == ReconStatus.MATCHED
    assert broken.status == ReconStatus.BREAK


def test_cass715_still_escalates_at_100_not_below():
    # CASS 7.15: report at exactly £100, HITLProposal just above.
    agent = ReconAgent(store=InMemoryReconStore())
    at_threshold = agent.run_daily_recon(
        "2026-04-21", [{"account_iban": "GB29", "amount": "1000.00"}], [_stmt("GB29", "900.00")]
    )
    over_threshold = ReconAgent(store=InMemoryReconStore()).run_daily_recon(
        "2026-04-21", [{"account_iban": "GB29", "amount": "1000.00"}], [_stmt("GB29", "899.99")]
    )
    assert isinstance(at_threshold, ReconciliationReport)
    assert isinstance(over_threshold, HITLProposal)


def test_evaluators_carry_each_regimes_own_threshold():
    # The shared core treats thresholds as injected inputs, never a shared constant.
    cass15 = BreachEvaluator(RECON_TOLERANCE_GBP, "BREAK")
    cass715 = BreachEvaluator(BREACH_HITL_THRESHOLD, "HITL")
    assert cass15.threshold == Decimal("0.01")
    assert cass715.threshold == Decimal("100")
    # A £50 discrepancy: a CASS 15 BREAK, but below the CASS 7.15 HITL line.
    assert cass15.evaluate(Decimal("50")).is_breach is True
    assert cass715.evaluate(Decimal("50")).is_breach is False
