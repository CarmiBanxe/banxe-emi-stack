"""
tests/test_transaction_monitor/test_alert_generator.py
IL-RTM-01 | banxe-emi-stack

Tests for AlertGenerator: severity mapping, explanation generation,
KB citation attachment, LOW auto-close, CRITICAL escalation.
"""

from __future__ import annotations

from decimal import Decimal

from services.transaction_monitor.alerts.alert_generator import AlertGenerator, score_to_severity
from services.transaction_monitor.alerts.explanation_engine import InMemoryKBPort
from services.transaction_monitor.models.alert import AlertSeverity
from services.transaction_monitor.models.risk_score import RiskScore
from services.transaction_monitor.models.transaction import TransactionEvent
from services.transaction_monitor.store.alert_store import InMemoryAlertStore


def _make_event(amount: str = "1000.00", sender_id: str = "cust-001") -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-ALERT-TEST",
        amount=Decimal(amount),
        sender_id=sender_id,
    )


class TestScoreToSeverity:
    def test_low_score_maps_to_low(self):
        assert score_to_severity(0.10) == AlertSeverity.LOW

    def test_medium_score_maps_to_medium(self):
        assert score_to_severity(0.45) == AlertSeverity.MEDIUM

    def test_high_score_maps_to_high(self):
        assert score_to_severity(0.70) == AlertSeverity.HIGH

    def test_critical_score_maps_to_critical(self):
        assert score_to_severity(0.85) == AlertSeverity.CRITICAL

    def test_exactly_at_medium_threshold(self):
        assert score_to_severity(0.30) == AlertSeverity.MEDIUM


class TestAlertGenerator:
    def setup_method(self):
        self.store = InMemoryAlertStore()
        self.generator = AlertGenerator(
            kb_port=InMemoryKBPort(),
            alert_store=self.store,
        )

    def test_generate_creates_alert(self):
        event = _make_event()
        rs = RiskScore(score=0.75)
        alert = self.generator.generate(event, rs)
        assert alert.transaction_id == "TXN-ALERT-TEST"
        assert alert.severity == AlertSeverity.HIGH

    def test_generate_stores_alert(self):
        event = _make_event()
        rs = RiskScore(score=0.60)
        alert = self.generator.generate(event, rs)
        assert self.store.get(alert.alert_id) is not None

    def test_generate_low_risk_action_is_auto_close(self):
        event = _make_event()
        rs = RiskScore(score=0.10)
        alert = self.generator.generate(event, rs)
        assert alert.recommended_action == "auto-close"
        assert alert.severity == AlertSeverity.LOW

    def test_generate_critical_action_is_escalate(self):
        event = _make_event()
        rs = RiskScore(score=0.95)
        alert = self.generator.generate(event, rs)
        assert alert.recommended_action == "escalate"
        assert alert.severity == AlertSeverity.CRITICAL

    def test_explanation_is_non_empty(self):
        event = _make_event()
        rs = RiskScore(score=0.55)
        alert = self.generator.generate(event, rs)
        assert len(alert.explanation) > 0
        assert "TXN-ALERT-TEST" in alert.explanation
