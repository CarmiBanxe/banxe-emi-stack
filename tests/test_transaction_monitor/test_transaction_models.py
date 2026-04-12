"""
tests/test_transaction_monitor/test_transaction_models.py
IL-RTM-01 | banxe-emi-stack

Tests for TransactionEvent, RiskScore, RiskFactor, and AMLAlert models.
"""

from __future__ import annotations

from decimal import Decimal

from services.transaction_monitor.models.alert import AlertSeverity, AlertStatus, AMLAlert
from services.transaction_monitor.models.risk_score import RiskScore, classify_score
from services.transaction_monitor.models.transaction import TransactionEvent, TransactionType


class TestTransactionEvent:
    def test_amount_is_decimal(self):
        event = TransactionEvent(
            transaction_id="TXN-001",
            amount=Decimal("15200.00"),
            sender_id="cust-001",
        )
        assert isinstance(event.amount, Decimal)
        assert event.amount == Decimal("15200.00")

    def test_default_currency_is_gbp(self):
        event = TransactionEvent(
            transaction_id="TXN-002",
            amount=Decimal("500.00"),
            sender_id="cust-002",
        )
        assert event.currency == "GBP"

    def test_default_jurisdiction_is_gb(self):
        event = TransactionEvent(
            transaction_id="TXN-003",
            amount=Decimal("100.00"),
            sender_id="cust-003",
        )
        assert event.sender_jurisdiction == "GB"

    def test_transaction_types_enum(self):
        event = TransactionEvent(
            transaction_id="TXN-004",
            amount=Decimal("200.00"),
            sender_id="cust-004",
            transaction_type=TransactionType.CRYPTO_ONRAMP,
        )
        assert event.transaction_type == TransactionType.CRYPTO_ONRAMP


class TestRiskScore:
    def test_score_classification_low(self):
        rs = RiskScore(score=0.15)
        assert rs.classification == "low"

    def test_score_classification_medium(self):
        rs = RiskScore(score=0.45)
        assert rs.classification == "medium"

    def test_score_classification_high(self):
        rs = RiskScore(score=0.70)
        assert rs.classification == "high"

    def test_score_classification_critical(self):
        rs = RiskScore(score=0.85)
        assert rs.classification == "critical"

    def test_classify_score_function(self):
        assert classify_score(0.0) == "low"
        assert classify_score(0.30) == "medium"
        assert classify_score(0.60) == "high"
        assert classify_score(0.80) == "critical"


class TestAMLAlert:
    def test_alert_has_review_deadline(self):
        rs = RiskScore(score=0.75)
        alert = AMLAlert(
            transaction_id="TXN-005",
            customer_id="cust-005",
            severity=AlertSeverity.HIGH,
            risk_score=rs,
            amount_gbp=Decimal("5000.00"),
        )
        assert alert.review_deadline is not None

    def test_amount_gbp_is_decimal(self):
        rs = RiskScore(score=0.5)
        alert = AMLAlert(
            transaction_id="TXN-006",
            customer_id="cust-006",
            severity=AlertSeverity.MEDIUM,
            risk_score=rs,
            amount_gbp=Decimal("3000.00"),
        )
        assert isinstance(alert.amount_gbp, Decimal)

    def test_default_status_is_open(self):
        rs = RiskScore(score=0.4)
        alert = AMLAlert(
            transaction_id="TXN-007",
            customer_id="cust-007",
            severity=AlertSeverity.MEDIUM,
            risk_score=rs,
            amount_gbp=Decimal("1000.00"),
        )
        assert alert.status == AlertStatus.OPEN
