"""
services/transaction_monitor/alerts/alert_generator.py — Alert Generator
IL-RTM-01 | banxe-emi-stack

Creates AMLAlert objects from scored transactions.
Queries KB for regulation citations, generates human-readable explanations.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from services.transaction_monitor.alerts.explanation_engine import (
    ExplanationEngine,
    InMemoryKBPort,
    KBPort,
)
from services.transaction_monitor.models.alert import AlertSeverity, AMLAlert
from services.transaction_monitor.models.risk_score import RiskScore
from services.transaction_monitor.models.transaction import TransactionEvent
from services.transaction_monitor.store.alert_store import AlertStorePort, InMemoryAlertStore

logger = logging.getLogger("banxe.transaction_monitor.alert_generator")

# Score thresholds for severity mapping
_SEVERITY_THRESHOLDS = {
    AlertSeverity.CRITICAL: 0.80,
    AlertSeverity.HIGH: 0.60,
    AlertSeverity.MEDIUM: 0.30,
    AlertSeverity.LOW: 0.0,
}


def score_to_severity(
    score: float,
) -> AlertSeverity:  # nosemgrep: banxe-float-money — non-monetary score input
    """Map a risk score to AlertSeverity."""
    if score >= _SEVERITY_THRESHOLDS[AlertSeverity.CRITICAL]:
        return AlertSeverity.CRITICAL
    if score >= _SEVERITY_THRESHOLDS[AlertSeverity.HIGH]:
        return AlertSeverity.HIGH
    if score >= _SEVERITY_THRESHOLDS[AlertSeverity.MEDIUM]:
        return AlertSeverity.MEDIUM
    return AlertSeverity.LOW


def score_to_action(severity: AlertSeverity) -> str:
    mapping = {
        AlertSeverity.CRITICAL: "escalate",
        AlertSeverity.HIGH: "review",
        AlertSeverity.MEDIUM: "review",
        AlertSeverity.LOW: "auto-close",
    }
    return mapping[severity]


class AlertGenerator:
    """Creates AMLAlert from a scored TransactionEvent.

    Workflow:
    1. Map risk score to severity
    2. Extract KB regulation refs from risk factors
    3. Generate human-readable explanation
    4. Build and return AMLAlert
    """

    def __init__(
        self,
        kb_port: KBPort | None = None,
        alert_store: AlertStorePort | None = None,
    ) -> None:
        self._explanation_engine = ExplanationEngine(kb_port=kb_port or InMemoryKBPort())
        self._store = alert_store or InMemoryAlertStore()

    def generate(self, event: TransactionEvent, risk_score: RiskScore) -> AMLAlert:
        """Generate an AMLAlert for a scored transaction.

        Only generates alerts for medium, high, and critical risk.
        LOW risk events are still recorded but auto-closed.
        """
        severity = score_to_severity(risk_score.score)
        regulation_refs = self._explanation_engine.extract_regulation_refs(risk_score)
        explanation = self._explanation_engine.generate(event, risk_score, regulation_refs)
        recommended_action = score_to_action(severity)

        alert = AMLAlert(
            transaction_id=event.transaction_id,
            customer_id=event.sender_id,
            severity=severity,
            risk_score=risk_score,
            amount_gbp=event.amount if event.currency == "GBP" else Decimal("0"),
            explanation=explanation,
            regulation_refs=regulation_refs,
            recommended_action=recommended_action,
        )

        self._store.save(alert)
        logger.info(
            "Generated alert %s for transaction %s (severity: %s)",
            alert.alert_id,
            event.transaction_id,
            severity.value,
        )
        return alert
