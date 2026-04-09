"""
test_aml_thresholds.py — AML threshold sets: INDIVIDUAL vs COMPANY
MLR 2017 | POCA 2002 | Geniusto v5 dual-entity rules
"""

from __future__ import annotations

from decimal import Decimal

from services.aml.aml_thresholds import (
    COMPANY_THRESHOLDS,
    INDIVIDUAL_THRESHOLDS,
    get_thresholds,
)


class TestThresholdValues:
    def test_individual_edd_is_10k(self):
        assert INDIVIDUAL_THRESHOLDS.edd_trigger == Decimal("10000")

    def test_company_edd_is_50k(self):
        assert COMPANY_THRESHOLDS.edd_trigger == Decimal("50000")

    def test_company_limits_higher_than_individual(self):
        assert (
            COMPANY_THRESHOLDS.velocity_daily_amount > INDIVIDUAL_THRESHOLDS.velocity_daily_amount
        )
        assert (
            COMPANY_THRESHOLDS.velocity_monthly_amount
            > INDIVIDUAL_THRESHOLDS.velocity_monthly_amount
        )

    def test_individual_sar_auto_50k(self):
        assert INDIVIDUAL_THRESHOLDS.sar_auto_single == Decimal("50000")

    def test_company_sar_auto_250k(self):
        assert COMPANY_THRESHOLDS.sar_auto_single == Decimal("250000")

    def test_get_thresholds_individual(self):
        t = get_thresholds("INDIVIDUAL")
        assert t.entity_type == "INDIVIDUAL"

    def test_get_thresholds_company(self):
        t = get_thresholds("COMPANY")
        assert t.entity_type == "COMPANY"

    def test_get_thresholds_unknown_defaults_to_individual(self):
        t = get_thresholds("ROBOT")
        assert t.entity_type == "INDIVIDUAL"


class TestEDDRequired:
    def test_individual_9999_no_edd(self):
        assert not INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("9999"))

    def test_individual_10000_edd(self):
        assert INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("10000"))

    def test_company_49999_no_edd(self):
        assert not COMPANY_THRESHOLDS.requires_edd(Decimal("49999"))

    def test_company_50000_edd(self):
        assert COMPANY_THRESHOLDS.requires_edd(Decimal("50000"))

    def test_pep_individual_lower_threshold(self):
        # PEP gets EDD at 50% = £5,000
        pep_threshold = INDIVIDUAL_THRESHOLDS.edd_for_pep()
        assert pep_threshold == Decimal("5000.00")
        assert INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("5000"), is_pep=True)
        assert not INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("4999"), is_pep=True)

    def test_pep_company_lower_threshold(self):
        pep_threshold = COMPANY_THRESHOLDS.edd_for_pep()
        assert pep_threshold == Decimal("25000.00")
        assert COMPANY_THRESHOLDS.requires_edd(Decimal("25000"), is_pep=True)


class TestSARRequired:
    def test_individual_below_50k_no_sar(self):
        assert not INDIVIDUAL_THRESHOLDS.requires_sar_consideration(Decimal("49999"))

    def test_individual_50k_sar(self):
        assert INDIVIDUAL_THRESHOLDS.requires_sar_consideration(Decimal("50000"))

    def test_company_below_250k_no_sar(self):
        assert not COMPANY_THRESHOLDS.requires_sar_consideration(Decimal("249999"))

    def test_company_250k_sar(self):
        assert COMPANY_THRESHOLDS.requires_sar_consideration(Decimal("250000"))


class TestVelocityBreach:
    def test_individual_daily_amount_breach(self):
        # £25k limit
        assert INDIVIDUAL_THRESHOLDS.is_velocity_daily_breach(Decimal("25000"), 1)

    def test_individual_daily_count_breach(self):
        # 10 tx limit
        assert INDIVIDUAL_THRESHOLDS.is_velocity_daily_breach(Decimal("1000"), 10)

    def test_individual_daily_no_breach(self):
        assert not INDIVIDUAL_THRESHOLDS.is_velocity_daily_breach(Decimal("5000"), 3)

    def test_company_daily_higher_limit(self):
        # £500k limit — £25k should NOT breach for company
        assert not COMPANY_THRESHOLDS.is_velocity_daily_breach(Decimal("25000"), 3)

    def test_company_daily_breach(self):
        assert COMPANY_THRESHOLDS.is_velocity_daily_breach(Decimal("500000"), 1)

    def test_individual_monthly_breach(self):
        assert INDIVIDUAL_THRESHOLDS.is_velocity_monthly_breach(Decimal("100000"), 10)

    def test_company_monthly_no_breach_at_individual_threshold(self):
        # Company monthly limit = £2M
        assert not COMPANY_THRESHOLDS.is_velocity_monthly_breach(Decimal("100000"), 10)


class TestStructuringSignal:
    def test_individual_structuring_detected(self):
        # 3 txs totalling £9,000 in 24h — structuring signal
        assert INDIVIDUAL_THRESHOLDS.is_structuring_signal(3, Decimal("9000"))

    def test_individual_structuring_below_count(self):
        # Only 2 txs — not enough
        assert not INDIVIDUAL_THRESHOLDS.is_structuring_signal(2, Decimal("9000"))

    def test_individual_structuring_below_total(self):
        # 3 txs but only £5,000 total
        assert not INDIVIDUAL_THRESHOLDS.is_structuring_signal(3, Decimal("5000"))

    def test_company_structuring_higher_threshold(self):
        # Company structuring: 5 txs / £45k
        assert not COMPANY_THRESHOLDS.is_structuring_signal(3, Decimal("9000"))
        assert COMPANY_THRESHOLDS.is_structuring_signal(5, Decimal("45000"))


class TestFraudAdapterEntityAware:
    """Smoke tests: MockFraudAdapter uses entity-type-aware EDD thresholds."""

    def _make_request(self, amount: str, entity_type: str):
        from services.fraud.fraud_port import FraudScoringRequest

        return FraudScoringRequest(
            transaction_id="tx-test",
            customer_id="cust-001",
            amount=Decimal(amount),
            currency="GBP",
            destination_account="12345678",
            destination_sort_code="20-00-00",
            destination_country="GB",
            payment_rail="FPS",
            entity_type=entity_type,
        )

    def test_individual_15k_scores_high(self):
        from services.fraud.mock_fraud_adapter import MockFraudAdapter

        adapter = MockFraudAdapter()
        result = adapter.score(self._make_request("15000", "INDIVIDUAL"))
        # £15k ≥ £10k EDD threshold for individual → score 50 → MEDIUM
        assert result.score >= 50
        assert any("EDD" in f for f in result.factors)

    def test_company_15k_does_not_trigger_edd(self):
        from services.fraud.mock_fraud_adapter import MockFraudAdapter

        adapter = MockFraudAdapter()
        result = adapter.score(self._make_request("15000", "COMPANY"))
        # £15k < £50k EDD threshold for company → no EDD factor
        assert not any("EDD" in f for f in result.factors)

    def test_company_55k_triggers_edd(self):
        from services.fraud.mock_fraud_adapter import MockFraudAdapter

        adapter = MockFraudAdapter()
        result = adapter.score(self._make_request("55000", "COMPANY"))
        # £55k ≥ £50k EDD for company
        assert any("EDD" in f for f in result.factors)

    def test_entity_type_in_factor_label(self):
        from services.fraud.mock_fraud_adapter import MockFraudAdapter

        adapter = MockFraudAdapter()
        result = adapter.score(self._make_request("15000", "INDIVIDUAL"))
        assert any("INDIVIDUAL" in f for f in result.factors)
