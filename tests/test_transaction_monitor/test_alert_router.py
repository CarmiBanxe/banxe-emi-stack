"""
tests/test_transaction_monitor/test_alert_router.py
IL-RTM-01 | banxe-emi-stack

Tests for AlertRouter: CRITICAL→Marble+MLRO, HIGH→Marble+analyst,
MEDIUM→analyst queue, LOW→auto-close. HITL invariant verification.
"""

from __future__ import annotations

from decimal import Decimal

from services.transaction_monitor.alerts.alert_router import AlertRouter, InMemoryMarblePort
from services.transaction_monitor.models.alert import AlertSeverity, AlertStatus, AMLAlert
from services.transaction_monitor.models.risk_score import RiskScore
from services.transaction_monitor.store.alert_store import InMemoryAlertStore


def _make_alert(severity: AlertSeverity, score: float) -> AMLAlert:
    rs = RiskScore(score=score)
    return AMLAlert(
        transaction_id="TXN-ROUTE-TEST",
        customer_id="cust-001",
        severity=severity,
        risk_score=rs,
        amount_gbp=Decimal("5000.00"),
    )


class TestAlertRouter:
    def setup_method(self):
        self.marble = InMemoryMarblePort()
        self.store = InMemoryAlertStore()
        self.router = AlertRouter(marble_port=self.marble, alert_store=self.store)

    def test_critical_creates_marble_case(self):
        alert = _make_alert(AlertSeverity.CRITICAL, 0.90)
        routed = self.router.route(alert)
        assert len(self.marble.cases_created) == 1
        assert routed.marble_case_id is not None

    def test_critical_assigns_to_mlro(self):
        alert = _make_alert(AlertSeverity.CRITICAL, 0.90)
        routed = self.router.route(alert)
        assert routed.assigned_to == "mlro@banxe.com"
        assert routed.status == AlertStatus.ESCALATED

    def test_high_creates_marble_case(self):
        alert = _make_alert(AlertSeverity.HIGH, 0.70)
        routed = self.router.route(alert)
        assert len(self.marble.cases_created) == 1
        assert routed.status == AlertStatus.REVIEWING

    def test_medium_no_marble_case(self):
        alert = _make_alert(AlertSeverity.MEDIUM, 0.45)
        routed = self.router.route(alert)
        assert len(self.marble.cases_created) == 0
        assert routed.status == AlertStatus.REVIEWING

    def test_low_auto_closed(self):
        alert = _make_alert(AlertSeverity.LOW, 0.10)
        routed = self.router.route(alert)
        assert routed.status == AlertStatus.AUTO_CLOSED
        assert routed.closed_at is not None
        assert len(self.marble.cases_created) == 0

    def test_audit_trail_populated_on_route(self):
        alert = _make_alert(AlertSeverity.HIGH, 0.75)
        routed = self.router.route(alert)
        assert len(routed.audit_trail) > 0

    def test_alert_saved_to_store_after_routing(self):
        alert = _make_alert(AlertSeverity.MEDIUM, 0.50)
        routed = self.router.route(alert)
        assert self.store.get(routed.alert_id) is not None
