"""
test_tx_monitor.py — TxMonitorService: dual-entity AML transaction monitoring
MLR 2017 | POCA 2002 s.330 | FCA SYSC 6.3
"""
from __future__ import annotations

import pytest
from decimal import Decimal

from services.aml.tx_monitor import (
    InMemoryVelocityTracker,
    TxMonitorRequest,
    TxMonitorService,
)


def _req(
    amount: str,
    entity_type: str = "INDIVIDUAL",
    customer_id: str = "cust-001",
    is_pep: bool = False,
    is_sanctions_hit: bool = False,
    is_fx: bool = False,
) -> TxMonitorRequest:
    return TxMonitorRequest(
        transaction_id=f"tx-{amount}-{entity_type}",
        customer_id=customer_id,
        entity_type=entity_type,
        amount=Decimal(amount),
        currency="GBP",
        is_pep=is_pep,
        is_sanctions_hit=is_sanctions_hit,
        is_fx=is_fx,
    )


@pytest.fixture
def monitor():
    return TxMonitorService(InMemoryVelocityTracker())


# ── Sanctions ──────────────────────────────────────────────────────────────────

class TestSanctionsBlock:
    def test_sanctions_hit_blocks(self, monitor):
        result = monitor.evaluate(_req("1000", is_sanctions_hit=True))
        assert result.sanctions_block is True
        assert result.should_block is True

    def test_sanctions_block_returns_early(self, monitor):
        result = monitor.evaluate(_req("1000", is_sanctions_hit=True))
        # No other flags should be set when sanctions block is hit
        assert result.edd_required is False
        assert result.sar_required is False

    def test_no_sanctions_not_blocked(self, monitor):
        result = monitor.evaluate(_req("1000"))
        assert result.sanctions_block is False


# ── EDD (MLR 2017 Reg.28) ──────────────────────────────────────────────────────

class TestEDD:
    def test_individual_9999_no_edd(self, monitor):
        result = monitor.evaluate(_req("9999", "INDIVIDUAL"))
        assert result.edd_required is False

    def test_individual_10000_edd(self, monitor):
        result = monitor.evaluate(_req("10000", "INDIVIDUAL"))
        assert result.edd_required is True

    def test_company_49999_no_edd(self, monitor):
        result = monitor.evaluate(_req("49999", "COMPANY"))
        assert result.edd_required is False

    def test_company_50000_edd(self, monitor):
        result = monitor.evaluate(_req("50000", "COMPANY"))
        assert result.edd_required is True

    def test_pep_individual_5000_edd(self, monitor):
        result = monitor.evaluate(_req("5000", "INDIVIDUAL", is_pep=True))
        assert result.edd_required is True

    def test_pep_individual_4999_no_edd(self, monitor):
        result = monitor.evaluate(_req("4999", "INDIVIDUAL", is_pep=True))
        assert result.edd_required is False

    def test_edd_reason_contains_entity_type(self, monitor):
        result = monitor.evaluate(_req("15000", "INDIVIDUAL"))
        assert any("INDIVIDUAL" in r for r in result.reasons)

    def test_fx_lower_edd_threshold(self, monitor):
        # FX EDD threshold for individual = £5,000 (fx_single_edd)
        result = monitor.evaluate(_req("5000", "INDIVIDUAL", is_fx=True))
        assert result.edd_required is True

    def test_fx_below_edd(self, monitor):
        result = monitor.evaluate(_req("4999", "INDIVIDUAL", is_fx=True))
        assert result.edd_required is False


# ── Velocity ───────────────────────────────────────────────────────────────────

class TestVelocity:
    def test_daily_amount_breach_individual(self, monitor):
        # Pre-load £24,500 in tracker
        monitor.record("cust-v", Decimal("24500"))
        result = monitor.evaluate(_req("1000", customer_id="cust-v"))
        assert result.velocity_daily_breach is True

    def test_daily_count_breach_individual(self, monitor):
        # Pre-load 10 transactions
        for _ in range(10):
            monitor.record("cust-vc", Decimal("100"))
        result = monitor.evaluate(_req("100", customer_id="cust-vc"))
        assert result.velocity_daily_breach is True

    def test_company_25k_no_daily_breach(self, monitor):
        monitor.record("cust-corp", Decimal("24500"))
        result = monitor.evaluate(_req("1000", "COMPANY", customer_id="cust-corp"))
        # Company daily limit = £500k — no breach at £25.5k
        assert result.velocity_daily_breach is False

    def test_no_velocity_fresh_customer(self, monitor):
        result = monitor.evaluate(_req("5000"))
        assert result.velocity_daily_breach is False
        assert result.velocity_monthly_breach is False

    def test_monthly_breach_individual(self, monitor):
        monitor.record("cust-m", Decimal("99500"))
        result = monitor.evaluate(_req("1000", customer_id="cust-m"))
        assert result.velocity_monthly_breach is True


# ── Structuring ────────────────────────────────────────────────────────────────

class TestStructuring:
    def test_structuring_signal_individual(self, monitor):
        # 2 prior txs of £4,500 each (under £10k threshold)
        monitor.record("cust-s", Decimal("4500"))
        monitor.record("cust-s", Decimal("4500"))
        # 3rd tx of £4,500 → 3 txs / £13,500 total in 24h
        result = monitor.evaluate(_req("4500", customer_id="cust-s"))
        assert result.structuring_signal is True

    def test_no_structuring_single_large_tx(self, monitor):
        # Single £15k tx ≥ edd_trigger → EDD, not structuring
        result = monitor.evaluate(_req("15000"))
        assert result.structuring_signal is False
        assert result.edd_required is True

    def test_no_structuring_below_count(self, monitor):
        # Only 1 prior tx
        monitor.record("cust-ns", Decimal("4500"))
        result = monitor.evaluate(_req("4500", customer_id="cust-ns"))
        assert result.structuring_signal is False

    def test_company_structuring_higher_bar(self, monitor):
        # Individual structuring bar (3 txs / £9k) should NOT trigger for company
        monitor.record("cust-corp-s", Decimal("4500"))
        monitor.record("cust-corp-s", Decimal("4500"))
        result = monitor.evaluate(_req("4500", "COMPANY", customer_id="cust-corp-s"))
        assert result.structuring_signal is False


# ── SAR ────────────────────────────────────────────────────────────────────────

class TestSAR:
    def test_individual_50k_sar(self, monitor):
        result = monitor.evaluate(_req("50000", "INDIVIDUAL"))
        assert result.sar_required is True

    def test_individual_below_daily_sar_no_single_sar(self, monitor):
        # £20,000: below single SAR threshold (£50k) AND below daily SAR threshold (£25k)
        # → EDD required (≥ £10k), but no SAR
        result = monitor.evaluate(_req("20000", "INDIVIDUAL"))
        assert result.edd_required is True
        assert result.sar_required is False

    def test_company_250k_sar(self, monitor):
        result = monitor.evaluate(_req("250000", "COMPANY"))
        assert result.sar_required is True

    def test_company_249999_no_sar(self, monitor):
        result = monitor.evaluate(_req("249999", "COMPANY"))
        assert result.sar_required is False

    def test_sar_reason_contains_threshold(self, monitor):
        result = monitor.evaluate(_req("50000", "INDIVIDUAL"))
        assert any("SAR" in r for r in result.reasons)


# ── requires_hitl ──────────────────────────────────────────────────────────────

class TestRequiresHITL:
    def test_clean_tx_no_hitl(self, monitor):
        result = monitor.evaluate(_req("500", "INDIVIDUAL"))
        assert result.requires_hitl is False

    def test_edd_requires_hitl(self, monitor):
        result = monitor.evaluate(_req("15000", "INDIVIDUAL"))
        assert result.requires_hitl is True

    def test_sanctions_requires_hitl(self, monitor):
        result = monitor.evaluate(_req("100", is_sanctions_hit=True))
        assert result.requires_hitl is True


# ── thresholds_applied field ───────────────────────────────────────────────────

class TestThresholdsApplied:
    def test_individual_thresholds_applied(self, monitor):
        result = monitor.evaluate(_req("1000", "INDIVIDUAL"))
        assert result.thresholds_applied == "INDIVIDUAL"

    def test_company_thresholds_applied(self, monitor):
        result = monitor.evaluate(_req("1000", "COMPANY"))
        assert result.thresholds_applied == "COMPANY"
