"""
test_fraud_adapter.py — Tests for MockFraudAdapter (S5-22 / S5-26)
PSR APP 2024 | FCA CONC 13 | banxe-emi-stack

Tests cover:
  - Score classification (LOW/MEDIUM/HIGH/CRITICAL)
  - Blocked country → CRITICAL immediately
  - High-value thresholds (£10k EDD individual, £50k EDD corporate, £100k CRITICAL)
  - APP scam heuristic (PSR APP 2024 first-time payee + unusual amount)
  - 100ms SLA (mock well within)
  - FraudScoringPort protocol satisfied
  - get_fraud_adapter() factory
"""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from services.fraud.fraud_port import (
    AppScamIndicator,
    FraudRisk,
    FraudScoringRequest,
)
from services.fraud.mock_fraud_adapter import MockFraudAdapter
from services.fraud.sardine_adapter import get_fraud_adapter


def _req(**kwargs) -> FraudScoringRequest:
    defaults = dict(
        transaction_id="txn-001",
        customer_id="cust-001",
        amount=Decimal("100"),
        currency="GBP",
        destination_account="GB29NWBK60161331926819",
        destination_sort_code="60-16-13",
        destination_country="GB",
        payment_rail="FPS",
        first_transaction_to_payee=False,
        amount_unusual=False,
    )
    defaults.update(kwargs)
    return FraudScoringRequest(**defaults)


@pytest.fixture
def adapter() -> MockFraudAdapter:
    return MockFraudAdapter()


class TestLowRisk:
    def test_small_known_payee(self, adapter):
        result = adapter.score(_req(amount=Decimal("50"), first_transaction_to_payee=False))
        assert result.risk == FraudRisk.LOW
        assert result.score < 40
        assert result.block is False
        assert result.hold_for_review is False

    def test_provider_is_mock(self, adapter):
        result = adapter.score(_req())
        assert result.provider == "mock"

    def test_transaction_id_preserved(self, adapter):
        result = adapter.score(_req(transaction_id="txn-xyz"))
        assert result.transaction_id == "txn-xyz"


class TestMediumRisk:
    def test_over_1000_first_payee(self, adapter):
        result = adapter.score(_req(amount=Decimal("1500"), first_transaction_to_payee=True))
        assert result.risk == FraudRisk.MEDIUM
        assert 40 <= result.score < 70
        assert result.block is False
        assert result.hold_for_review is False

    def test_over_1000_known_payee(self, adapter):
        result = adapter.score(_req(amount=Decimal("2000"), first_transaction_to_payee=False))
        assert result.risk == FraudRisk.MEDIUM

    def test_factors_populated(self, adapter):
        result = adapter.score(_req(amount=Decimal("1500")))
        assert len(result.factors) > 0


class TestHighRisk:
    def test_edd_threshold(self, adapter):
        result = adapter.score(_req(amount=Decimal("10000"), first_transaction_to_payee=True))
        assert result.risk == FraudRisk.HIGH
        assert 70 <= result.score < 85
        assert result.hold_for_review is True
        assert result.block is False

    def test_first_payee_unusual_amount(self, adapter):
        result = adapter.score(_req(
            amount=Decimal("10000"),
            first_transaction_to_payee=True,
            amount_unusual=True,
        ))
        assert result.risk in (FraudRisk.HIGH, FraudRisk.CRITICAL)
        assert result.hold_for_review is True

    def test_high_risk_country(self, adapter):
        result = adapter.score(_req(
            amount=Decimal("5000"),
            destination_country="NG",  # not in high-risk list but not blocked
        ))
        assert result.risk == FraudRisk.MEDIUM  # 5k + not-first + not-unusual

    def test_fatf_country_raises_score(self, adapter):
        result = adapter.score(_req(
            amount=Decimal("5000"),
            destination_country="SY",  # FATF greylist
        ))
        assert result.score >= 35  # 15 (amount) + 20 (country)


class TestCriticalRisk:
    def test_blocked_country_immediate_critical(self, adapter):
        for country in ["RU", "BY", "IR", "KP", "CU"]:
            result = adapter.score(_req(destination_country=country))
            assert result.risk == FraudRisk.CRITICAL, f"Expected CRITICAL for {country}"
            assert result.block is True
            assert result.score >= 90

    def test_very_high_value(self, adapter):
        # CRITICAL threshold is £100,000 (scheme-level, entity-independent)
        result = adapter.score(_req(amount=Decimal("100000")))
        assert result.risk == FraudRisk.CRITICAL
        assert result.block is True
        assert result.score == 100 or result.score >= 85

    def test_blocked_country_no_score_pollution(self, adapter):
        # Blocked country should return immediately (score=95), ignore other factors
        result = adapter.score(_req(destination_country="RU", amount=Decimal("1")))
        assert result.block is True
        assert result.app_scam_indicator == AppScamIndicator.NONE


class TestAppScamDetection:
    def test_investment_scam_signal(self, adapter):
        result = adapter.score(_req(
            amount=Decimal("15000"),
            first_transaction_to_payee=True,
            amount_unusual=True,
        ))
        assert result.app_scam_indicator == AppScamIndicator.INVESTMENT_SCAM

    def test_no_scam_normal_payee(self, adapter):
        result = adapter.score(_req(
            amount=Decimal("500"),
            first_transaction_to_payee=False,
            amount_unusual=False,
        ))
        assert result.app_scam_indicator == AppScamIndicator.NONE

    def test_first_payee_no_unusual_no_scam_signal(self, adapter):
        # First payee but low amount → MEDIUM risk, no APP scam signal
        result = adapter.score(_req(amount=Decimal("200"), first_transaction_to_payee=True))
        assert result.app_scam_indicator == AppScamIndicator.NONE


class TestSlaCompliance:
    def test_under_100ms(self, adapter):
        """S5-22: fraud score must be returned within 100ms."""
        req = _req(amount=Decimal("50000"), destination_country="SY")
        t0 = time.monotonic()
        result = adapter.score(req)
        elapsed_ms = (time.monotonic() - t0) * 1000
        assert elapsed_ms < 100, f"Fraud scoring took {elapsed_ms:.1f}ms — exceeded 100ms SLA"
        assert result.latency_ms < 100

    def test_health_returns_true(self, adapter):
        assert adapter.health() is True


class TestFactory:
    def test_mock_adapter_default(self, monkeypatch):
        monkeypatch.delenv("FRAUD_ADAPTER", raising=False)
        adapter = get_fraud_adapter()
        assert isinstance(adapter, MockFraudAdapter)

    def test_mock_adapter_explicit(self, monkeypatch):
        monkeypatch.setenv("FRAUD_ADAPTER", "mock")
        adapter = get_fraud_adapter()
        assert isinstance(adapter, MockFraudAdapter)

    def test_sardine_adapter_raises_without_keys(self, monkeypatch):
        monkeypatch.setenv("FRAUD_ADAPTER", "sardine")
        monkeypatch.delenv("SARDINE_CLIENT_ID", raising=False)
        monkeypatch.delenv("SARDINE_SECRET_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="SARDINE_CLIENT_ID"):
            get_fraud_adapter()
