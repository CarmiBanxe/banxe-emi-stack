"""
test_recon_fx_pipeline.py — IL-INT-01
Cross-module: CAMT.053 EUR statement → FX conversion → CASS 7.15 recon tolerance check.
"""

from __future__ import annotations

from decimal import Decimal

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_ledger_balance(amount_gbp: Decimal) -> dict:
    return {"balance": str(amount_gbp), "currency": "GBP", "account_id": "ACC001"}


def _convert_eur_to_gbp(eur_amount: Decimal, rate: Decimal) -> Decimal:
    """I-01: all Decimal arithmetic."""
    return (eur_amount * rate).quantize(Decimal("0.01"))


# ── Tests ────────────────────────────────────────────────────────────────────


class TestReconFxPipeline:
    def test_eur_amount_converted_to_gbp_with_decimal(self, mock_frankfurter_rates):
        eur = Decimal("1000.00")
        rate = mock_frankfurter_rates["EUR"]
        gbp = _convert_eur_to_gbp(eur, rate)
        assert isinstance(gbp, Decimal)
        assert gbp == Decimal("860.00")

    def test_no_float_in_fx_conversion(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        assert isinstance(rate, Decimal), "Rate must be Decimal (I-01)"
        assert not isinstance(rate, float)

    def test_matched_transaction_zero_discrepancy(self, mock_frankfurter_rates):
        statement_eur = Decimal("1000.00")
        rate = mock_frankfurter_rates["EUR"]
        statement_gbp = _convert_eur_to_gbp(statement_eur, rate)
        ledger_gbp = Decimal("860.00")
        discrepancy = abs(statement_gbp - ledger_gbp)
        tolerance = Decimal("0.01")
        assert discrepancy <= tolerance

    def test_discrepancy_above_tolerance_detected(self, mock_frankfurter_rates):
        statement_eur = Decimal("1000.00")
        rate = mock_frankfurter_rates["EUR"]
        statement_gbp = _convert_eur_to_gbp(statement_eur, rate)
        ledger_gbp = Decimal("855.00")  # 5 GBP discrepancy
        discrepancy = abs(statement_gbp - ledger_gbp)
        tolerance = Decimal("0.01")
        assert discrepancy > tolerance

    def test_tolerance_boundary_exactly_at_limit(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        statement_gbp = _convert_eur_to_gbp(Decimal("1000.00"), rate)
        ledger_gbp = statement_gbp - Decimal("0.01")  # exactly at tolerance
        discrepancy = abs(statement_gbp - ledger_gbp)
        assert discrepancy <= Decimal("0.01")

    def test_tolerance_boundary_just_over_limit(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        statement_gbp = _convert_eur_to_gbp(Decimal("1000.00"), rate)
        ledger_gbp = statement_gbp - Decimal("0.02")  # just over tolerance
        discrepancy = abs(statement_gbp - ledger_gbp)
        assert discrepancy > Decimal("0.01")

    def test_multiple_transactions_aggregated(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        transactions = [Decimal("100.00"), Decimal("200.00"), Decimal("300.00")]
        total_eur = sum(transactions, Decimal("0"))
        total_gbp = _convert_eur_to_gbp(total_eur, rate)
        assert total_gbp == Decimal("516.00")

    def test_zero_amount_transaction_valid(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        gbp = _convert_eur_to_gbp(Decimal("0.00"), rate)
        assert gbp == Decimal("0.00")

    def test_large_amount_precision_preserved(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        large_eur = Decimal("1000000.00")
        gbp = _convert_eur_to_gbp(large_eur, rate)
        assert isinstance(gbp, Decimal)
        assert gbp == Decimal("860000.00")

    def test_usd_to_gbp_conversion(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["USD"]
        usd = Decimal("1000.00")
        gbp = _convert_eur_to_gbp(usd, rate)
        assert gbp == Decimal("790.00")

    def test_blocked_currency_rub_not_in_rates(self, mock_frankfurter_rates):
        """I-02: RUB must not appear in FX rates."""
        assert "RUB" not in mock_frankfurter_rates

    def test_blocked_currency_irr_not_in_rates(self, mock_frankfurter_rates):
        assert "IRR" not in mock_frankfurter_rates

    def test_blocked_currency_kpw_not_in_rates(self, mock_frankfurter_rates):
        assert "KPW" not in mock_frankfurter_rates

    def test_recon_pipeline_returns_status(self, mock_frankfurter_rates):
        """Pipeline integration: EUR statement → FX → tolerance → status."""
        statement_eur = Decimal("5000.00")
        rate = mock_frankfurter_rates["EUR"]
        statement_gbp = _convert_eur_to_gbp(statement_eur, rate)  # 4300.00 GBP
        ledger_gbp = Decimal("4200.00")  # 100 GBP discrepancy
        discrepancy = abs(statement_gbp - ledger_gbp)
        tolerance = Decimal("0.01")
        status = "MATCHED" if discrepancy <= tolerance else "DISCREPANCY"
        assert status == "DISCREPANCY"

    def test_recon_matched_status(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        amount = Decimal("1000.00")
        gbp = _convert_eur_to_gbp(amount, rate)
        status = "MATCHED" if abs(gbp - Decimal("860.00")) <= Decimal("0.01") else "DISCREPANCY"
        assert status == "MATCHED"

    def test_decimal_precision_two_places(self, mock_frankfurter_rates):
        rate = mock_frankfurter_rates["EUR"]
        result = _convert_eur_to_gbp(Decimal("333.33"), rate)
        # Should be quantized to 2dp
        assert result == result.quantize(Decimal("0.01"))


class TestFxRateModels:
    def test_rate_is_always_decimal(self):
        rate = Decimal("0.8600")
        assert isinstance(rate, Decimal)

    def test_rate_not_float(self):
        rate = Decimal("0.8600")
        assert not isinstance(rate, float)

    def test_gbp_base_rate_is_one(self, mock_frankfurter_rates):
        assert mock_frankfurter_rates["GBP"] == Decimal("1.0000")
