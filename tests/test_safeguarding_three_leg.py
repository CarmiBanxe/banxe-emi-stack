"""
tests/test_safeguarding_three_leg.py — CASS 15 three-leg tie-out.

D-RECON-BUILD-SPEC §3 (3-leg model): A (Midaz ledger) == B (safeguarding account)
== C (payment rail) within penny-exact tolerance (£0.01). Reuses src.recon_core
mechanics; Leg B port (BankStatementPort) already exists — this adds Leg C
(RailBalancePort) + the tie-out. Offline; Decimal-only (I-01).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.safeguarding.three_leg import (
    InMemoryRailBalancePort,
    RailBalancePort,
    ThreeLegStatus,
    three_leg_reconcile,
)

D = date(2026, 6, 26)


def test_all_three_legs_match():
    r = three_leg_reconcile(
        Decimal("50000.00"), Decimal("50000.00"), Decimal("50000.00"), recon_date=D
    )
    assert r.status == ThreeLegStatus.MATCHED
    assert r.is_compliant
    assert not r.shortfall


def test_within_penny_tolerance_matches():
    # every leg-pair |diff| <= £0.01 → MATCHED (strict breach is > threshold)
    r = three_leg_reconcile(
        Decimal("50000.00"), Decimal("50000.01"), Decimal("50000.00"), recon_date=D
    )
    assert r.status == ThreeLegStatus.MATCHED


def test_leg_break_escalates():
    r = three_leg_reconcile(
        Decimal("50000.00"), Decimal("50000.00"), Decimal("49000.00"), recon_date=D
    )
    assert r.status == ThreeLegStatus.BREAK
    assert r.b_vs_c.is_breach
    assert not r.shortfall  # A == B, so no client-fund shortfall


def test_shortfall_flagged_when_ledger_exceeds_safeguarding():
    # A (client-fund ledger) > B (safeguarding account) ⇒ under-safeguarded
    r = three_leg_reconcile(
        Decimal("60000.00"), Decimal("50000.00"), Decimal("60000.00"), recon_date=D
    )
    assert r.status == ThreeLegStatus.BREAK
    assert r.shortfall is True
    assert "SHORTFALL" in r.notes


def test_surplus_is_not_shortfall():
    # B (safeguarding) > A (ledger) ⇒ surplus, BREAK but not a shortfall
    r = three_leg_reconcile(
        Decimal("50000.00"), Decimal("60000.00"), Decimal("50000.00"), recon_date=D
    )
    assert r.status == ThreeLegStatus.BREAK
    assert r.shortfall is False


def test_pending_when_safeguarding_leg_missing():
    r = three_leg_reconcile(Decimal("50000.00"), None, Decimal("50000.00"), recon_date=D)
    assert r.status == ThreeLegStatus.PENDING
    assert r.a_vs_b is None


def test_pending_when_rail_leg_missing():
    r = three_leg_reconcile(Decimal("50000.00"), Decimal("50000.00"), None, recon_date=D)
    assert r.status == ThreeLegStatus.PENDING


def test_signed_difference_preserved():
    r = three_leg_reconcile(
        Decimal("60000.00"), Decimal("50000.00"), Decimal("60000.00"), recon_date=D
    )
    assert r.a_vs_b.difference == Decimal("10000.00")  # A - B, signed
    assert isinstance(r.a_vs_b.difference, Decimal)  # I-01


# ── RailBalancePort (Leg C source) ────────────────────────────────────────────


def test_rail_port_returns_configured_balance():
    port = InMemoryRailBalancePort({D: Decimal("12345.67")})
    assert port.get_rail_balance_gbp(D) == Decimal("12345.67")
    assert isinstance(port.get_rail_balance_gbp(D), Decimal)


def test_rail_port_missing_returns_none():
    port = InMemoryRailBalancePort()
    assert port.get_rail_balance_gbp(D) is None


def test_rail_port_satisfies_protocol():
    assert isinstance(InMemoryRailBalancePort(), RailBalancePort)
