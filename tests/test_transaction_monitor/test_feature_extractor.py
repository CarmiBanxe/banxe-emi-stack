"""
tests/test_transaction_monitor/test_feature_extractor.py
IL-RTM-01 | banxe-emi-stack

Tests for FeatureExtractor: all 10 features, boundary conditions,
jurisdction risk (I-02/I-03), round amount detection, crypto flag.
"""

from __future__ import annotations

from decimal import Decimal

from services.transaction_monitor.models.transaction import TransactionEvent, TransactionType
from services.transaction_monitor.scoring.feature_extractor import (
    FeatureExtractor,
    InMemoryVelocityPort,
)


def _make_event(
    amount: str = "1000.00",
    sender_jurisdiction: str = "GB",
    receiver_jurisdiction: str | None = None,
    transaction_type: TransactionType = TransactionType.PAYMENT,
    metadata: dict | None = None,
    customer_avg_amount: str | None = None,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-TEST",
        amount=Decimal(amount),
        sender_id="cust-001",
        sender_jurisdiction=sender_jurisdiction,
        receiver_jurisdiction=receiver_jurisdiction,
        transaction_type=transaction_type,
        metadata=metadata or {},
        customer_avg_amount=Decimal(customer_avg_amount) if customer_avg_amount else None,
    )


class TestFeatureExtractor:
    def setup_method(self):
        self.extractor = FeatureExtractor(velocity_port=InMemoryVelocityPort())

    def test_extract_returns_10_features(self):
        event = _make_event()
        features = self.extractor.extract(event)
        assert len(features) == 10

    def test_jurisdiction_risk_hard_blocked(self):
        event = _make_event(sender_jurisdiction="RU")
        features = self.extractor.extract(event)
        assert features["jurisdiction_risk"] == 1.0

    def test_jurisdiction_risk_greylist(self):
        event = _make_event(sender_jurisdiction="PK")  # Pakistan is on greylist
        features = self.extractor.extract(event)
        assert features["jurisdiction_risk"] == 0.7

    def test_jurisdiction_risk_safe(self):
        event = _make_event(sender_jurisdiction="DE")
        features = self.extractor.extract(event)
        assert features["jurisdiction_risk"] == 0.0

    def test_round_amount_flag(self):
        event = _make_event(amount="10000.00")
        features = self.extractor.extract(event)
        assert features["round_amount"] == 1.0

    def test_non_round_amount_no_flag(self):
        event = _make_event(amount="10047.23")
        features = self.extractor.extract(event)
        assert features["round_amount"] == 0.0

    def test_cross_border_flag(self):
        event = _make_event(sender_jurisdiction="GB", receiver_jurisdiction="AE")
        features = self.extractor.extract(event)
        assert features["cross_border"] == 1.0

    def test_no_cross_border_same_jurisdiction(self):
        event = _make_event(sender_jurisdiction="GB", receiver_jurisdiction="GB")
        features = self.extractor.extract(event)
        assert features["cross_border"] == 0.0

    def test_crypto_flag_for_onramp(self):
        event = _make_event(transaction_type=TransactionType.CRYPTO_ONRAMP)
        features = self.extractor.extract(event)
        assert features["crypto_flag"] == 1.0

    def test_pep_proximity_from_metadata(self):
        event = _make_event(metadata={"pep_connection": True})
        features = self.extractor.extract(event)
        assert features["pep_proximity"] == 0.9

    def test_amount_deviation_high(self):
        # amount=9000, avg=1000 → deviation=9x → capped to 1.0 (threshold=3x)
        event = _make_event(amount="9000.00", customer_avg_amount="1000.00")
        features = self.extractor.extract(event)
        assert features["amount_deviation"] >= 1.0

    def test_new_counterparty_flag(self):
        event = _make_event(metadata={"first_time_receiver": True})
        features = self.extractor.extract(event)
        assert features["new_counterparty"] == 1.0
