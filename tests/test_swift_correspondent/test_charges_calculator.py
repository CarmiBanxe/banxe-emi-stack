"""
Tests for SWIFT Charges Calculator.
IL-SWF-01 | Sprint 34 | Phase 47
Tests: SHA/BEN/OUR, EDD surcharge (I-04), all Decimal (I-22)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.swift_correspondent.charges_calculator import (
    AML_EDD_THRESHOLD,
    OUR_FEE_BASE_GBP,
    OUR_FEE_PCT,
    ChargesCalculator,
)
from services.swift_correspondent.models import ChargeCode


@pytest.fixture
def calc():
    return ChargesCalculator()


class TestSHACharges:
    def test_sha_sender_fee_25(self, calc):
        breakdown = calc.calculate_charges("msg_001", ChargeCode.SHA, Decimal("1000"))
        assert breakdown["sender_fee"] == Decimal("25.00")

    def test_sha_beneficiary_fee_zero(self, calc):
        breakdown = calc.calculate_charges("msg_001", ChargeCode.SHA, Decimal("1000"))
        assert breakdown["beneficiary_fee"] == Decimal("0.00")

    def test_sha_fee_is_decimal(self, calc):
        breakdown = calc.calculate_charges("msg_001", ChargeCode.SHA, Decimal("5000"))
        assert isinstance(breakdown["sender_fee"], Decimal)


class TestBENCharges:
    def test_ben_sender_fee_zero(self, calc):
        breakdown = calc.calculate_charges("msg_002", ChargeCode.BEN, Decimal("1000"))
        assert breakdown["sender_fee"] == Decimal("0.00")

    def test_ben_beneficiary_fee_nonzero(self, calc):
        breakdown = calc.calculate_charges("msg_002", ChargeCode.BEN, Decimal("1000"))
        assert breakdown["beneficiary_fee"] > Decimal("0")

    def test_ben_beneficiary_fee_is_decimal(self, calc):
        breakdown = calc.calculate_charges("msg_002", ChargeCode.BEN, Decimal("2000"))
        assert isinstance(breakdown["beneficiary_fee"], Decimal)


class TestOURCharges:
    def test_our_sender_fee_base_plus_pct(self, calc):
        amount = Decimal("10000")
        breakdown = calc.calculate_charges("msg_003", ChargeCode.OUR, amount)
        expected = OUR_FEE_BASE_GBP + (amount * OUR_FEE_PCT)
        assert breakdown["sender_fee"] == expected

    def test_our_beneficiary_fee_zero(self, calc):
        breakdown = calc.calculate_charges("msg_003", ChargeCode.OUR, Decimal("5000"))
        assert breakdown["beneficiary_fee"] == Decimal("0.00")

    def test_our_fee_is_decimal(self, calc):
        breakdown = calc.calculate_charges("msg_003", ChargeCode.OUR, Decimal("1000"))
        assert isinstance(breakdown["sender_fee"], Decimal)

    def test_our_fee_formula(self, calc):
        breakdown = calc.calculate_charges("msg_003", ChargeCode.OUR, Decimal("100000"))
        expected = Decimal("35.00") + Decimal("100000") * Decimal("0.001")
        assert breakdown["sender_fee"] == expected


class TestEDDSurcharge:
    def test_edd_surcharge_at_10k(self, calc):
        surcharge = calc.apply_edd_surcharge(Decimal("10000"))
        assert surcharge == Decimal("10.00")

    def test_edd_surcharge_above_10k(self, calc):
        surcharge = calc.apply_edd_surcharge(Decimal("50000"))
        assert surcharge == Decimal("10.00")

    def test_no_edd_surcharge_below_10k(self, calc):
        surcharge = calc.apply_edd_surcharge(Decimal("9999.99"))
        assert surcharge == Decimal("0.00")

    def test_edd_threshold_is_10k(self):
        assert Decimal("10000") == AML_EDD_THRESHOLD

    def test_edd_surcharge_is_decimal(self, calc):
        surcharge = calc.apply_edd_surcharge(Decimal("10000"))
        assert isinstance(surcharge, Decimal)


class TestGetTotalCharges:
    def test_total_includes_edd_for_large_amount(self, calc):
        total = calc.get_total_charges("msg_total", ChargeCode.SHA, Decimal("10000"))
        assert total == Decimal("35.00")  # SHA £25 + EDD £10

    def test_total_no_edd_below_threshold(self, calc):
        total = calc.get_total_charges("msg_total2", ChargeCode.SHA, Decimal("1000"))
        assert total == Decimal("25.00")  # SHA £25 only

    def test_total_is_decimal(self, calc):
        total = calc.get_total_charges("msg_t3", ChargeCode.OUR, Decimal("5000"))
        assert isinstance(total, Decimal)


class TestChargesBreakdown:
    def test_breakdown_empty_before_calc(self, calc):
        breakdown = calc.get_charges_breakdown("nonexistent")
        assert breakdown == {}

    def test_breakdown_populated_after_calc(self, calc):
        calc.calculate_charges("msg_bd", ChargeCode.SHA, Decimal("1000"))
        breakdown = calc.get_charges_breakdown("msg_bd")
        assert "sender_fee" in breakdown


class TestEstimateCorrespondentFees:
    def test_estimate_returns_decimal(self, calc):
        fee = calc.estimate_correspondent_fees("BARCGB22", "GBP", Decimal("1000"))
        assert isinstance(fee, Decimal)

    def test_estimate_stub_returns_15(self, calc):
        fee = calc.estimate_correspondent_fees("DEUTDEDB", "EUR", Decimal("5000"))
        assert fee == Decimal("15.00")
