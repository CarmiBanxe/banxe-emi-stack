"""Characterization tests — lock CURRENT behaviour of BOTH safeguarding paths.

These tests capture the observable compliance behaviour of each regime *before* the
S6.2 shared-core refactor and MUST stay green *after* it. They are the equivalence
contract: same inputs → same MATCHED/BREAK/PENDING (CASS 15) and same
ReconciliationReport/HITLProposal + thresholds (CASS 7.15).

If any assertion here changes, a compliance behaviour has drifted — STOP.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

# ── Router A — CASS 15 aggregate, penny-exact £0.01 ──────────────────────────
from src.safeguarding.daily_reconciliation import DailyReconciliation, ReconStatus

# ── Router B — CASS 7.15 line-item, HITL £100 ────────────────────────────────
from services.recon.recon_agent import ReconAgent
from services.recon.reconciliation_engine_v2 import (
    HITLProposal,
    InMemoryReconStore,
    ReconciliationEngineV2,
    ReconciliationReport,
    StatementEntry,
)


def _recon(internal, external):
    return DailyReconciliation(
        internal_balance_gbp=Decimal(str(internal)),
        external_balance_gbp=Decimal(str(external)) if external is not None else None,
        recon_date=date(2026, 4, 13),
    ).run()


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


# ── CASS 15 (Router A) characterization ──────────────────────────────────────


class TestCass15Characterization:
    def test_exact_match_is_matched(self):
        r = _recon("50000.00", "50000.00")
        assert r.status == ReconStatus.MATCHED
        assert r.difference_gbp == Decimal("0.00")

    def test_diff_equal_to_tolerance_is_matched(self):
        # |0.01| == tolerance → MATCHED (boundary: <= tolerance is within)
        r = _recon("50000.00", "49999.99")
        assert r.status == ReconStatus.MATCHED
        assert r.difference_gbp == Decimal("0.01")

    def test_diff_above_tolerance_is_break(self):
        r = _recon("50000.00", "49999.98")
        assert r.status == ReconStatus.BREAK
        assert r.difference_gbp == Decimal("0.02")

    def test_shortfall_preserves_signed_difference(self):
        # internal < external → negative signed difference, still BREAK
        r = _recon("49000.00", "50000.00")
        assert r.status == ReconStatus.BREAK
        assert r.difference_gbp == Decimal("-1000.00")

    def test_sub_penny_within_tolerance_is_matched(self):
        r = _recon("50000.00", "50000.005")
        assert r.status == ReconStatus.MATCHED

    def test_external_none_is_pending(self):
        r = _recon("50000.00", None)
        assert r.status == ReconStatus.PENDING
        assert r.difference_gbp is None
        assert r.external_balance_gbp is None


# ── CASS 7.15 (Router B) characterization ────────────────────────────────────


class TestCass715Characterization:
    def _agent(self):
        return ReconAgent(store=InMemoryReconStore())

    def test_matched_returns_report_no_breach(self):
        result = self._agent().run_daily_recon(
            "2026-04-21",
            [{"account_iban": "GB29", "amount": "1000.00"}],
            [_stmt("GB29", "1000.00")],
        )
        assert isinstance(result, ReconciliationReport)
        assert result.breach_detected is False

    def test_small_breach_returns_report_breach_true(self):
        result = self._agent().run_daily_recon(
            "2026-04-21", [{"account_iban": "GB29", "amount": "1000.00"}], [_stmt("GB29", "950.00")]
        )
        assert isinstance(result, ReconciliationReport)
        assert result.breach_detected is True

    def test_net_exactly_100_is_not_hitl(self):
        # net == BREACH_HITL_THRESHOLD → report (condition is strict >, not >=)
        result = self._agent().run_daily_recon(
            "2026-04-21", [{"account_iban": "GB29", "amount": "1000.00"}], [_stmt("GB29", "900.00")]
        )
        assert isinstance(result, ReconciliationReport)

    def test_net_over_100_is_hitl(self):
        result = self._agent().run_daily_recon(
            "2026-04-21", [{"account_iban": "GB29", "amount": "1000.00"}], [_stmt("GB29", "899.99")]
        )
        assert isinstance(result, HITLProposal)
        assert result.requires_approval_from == "COMPLIANCE_OFFICER"
        assert result.autonomy_level == "L4"

    @pytest.mark.parametrize(
        "ledger,stmt,expected_status",
        [
            ("1000.00", "1000.00", "MATCHED"),
            ("1000.00", "999.99", "MATCHED"),  # discrepancy == £0.01 tolerance → MATCHED
            ("1000.00", "999.98", "DISCREPANCY"),  # > £0.01 → DISCREPANCY
        ],
    )
    def test_line_item_tolerance_boundary(self, ledger, stmt, expected_status):
        engine = ReconciliationEngineV2(InMemoryReconStore())
        report = engine.run_daily(
            "2026-04-21", [{"account_iban": "GB29", "amount": ledger}], [_stmt("GB29", stmt)]
        )
        assert report.items[0].status == expected_status
