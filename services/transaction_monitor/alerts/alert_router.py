"""
services/transaction_monitor/alerts/alert_router.py — Alert Router
IL-RTM-01 | banxe-emi-stack

Routes AML alerts to appropriate destinations:
  CRITICAL (>0.8) → Marble case + MLRO notification
  HIGH (0.6-0.8)  → Marble case + analyst queue
  MEDIUM (0.3-0.6)→ Auto-enrichment + analyst review within 48h
  LOW (<0.3)      → Auto-close with audit log

HITL invariant: CRITICAL alerts require human (MLRO) review before close.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from services.transaction_monitor.models.alert import AlertSeverity, AlertStatus, AMLAlert
from services.transaction_monitor.store.alert_store import AlertStorePort, InMemoryAlertStore

logger = logging.getLogger("banxe.transaction_monitor.router")


# ── Marble Port (Protocol DI) ──────────────────────────────────────────────


@runtime_checkable
class MarblePort(Protocol):
    """Interface for Marble case management."""

    def create_case(self, alert_id: str, data: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryMarblePort:
    """Test stub — records case creation."""

    def __init__(self) -> None:
        self.cases_created: list[dict[str, Any]] = []
        self._counter = 1

    def create_case(self, alert_id: str, data: dict[str, Any]) -> dict[str, Any]:
        case = {
            "case_id": f"CASE-{self._counter:04d}",
            "alert_id": alert_id,
            "status": "open",
        }
        self.cases_created.append(case)
        self._counter += 1
        return case


class HTTPMarblePort:
    """Production Marble HTTP port."""

    def __init__(self, marble_url: str = "http://localhost:5002") -> None:
        self._url = marble_url

    def create_case(self, alert_id: str, data: dict[str, Any]) -> dict[str, Any]:
        import httpx

        with httpx.Client(base_url=self._url, timeout=10.0) as client:
            r = client.post(
                "/api/v1/cases",
                json={"alert_id": alert_id, **data},
            )
            r.raise_for_status()
            return r.json()


# ── Alert Router ───────────────────────────────────────────────────────────


class AlertRouter:
    """Routes alerts to reviewers and external systems.

    HITL invariant: CRITICAL and HIGH alerts are never auto-closed.
    Only LOW alerts are auto-closed (with full audit log).
    """

    def __init__(
        self,
        marble_port: MarblePort | None = None,
        alert_store: AlertStorePort | None = None,
    ) -> None:
        self._marble = marble_port or InMemoryMarblePort()
        self._store = alert_store or InMemoryAlertStore()

    def route(self, alert: AMLAlert) -> AMLAlert:
        """Route alert based on severity. Returns updated alert.

        Routing rules:
        - CRITICAL: Marble case + immediate MLRO flag + 4h deadline
        - HIGH: Marble case + analyst queue
        - MEDIUM: Auto-enrichment, analyst review
        - LOW: Auto-close with audit log
        """
        if alert.severity == AlertSeverity.CRITICAL:
            return self._route_critical(alert)
        if alert.severity == AlertSeverity.HIGH:
            return self._route_high(alert)
        if alert.severity == AlertSeverity.MEDIUM:
            return self._route_medium(alert)
        return self._route_low(alert)

    def _route_critical(self, alert: AMLAlert) -> AMLAlert:
        """CRITICAL: create Marble case, assign to MLRO."""
        case = self._marble.create_case(
            alert.alert_id,
            {
                "severity": "critical",
                "transaction_id": alert.transaction_id,
                "customer_id": alert.customer_id,
                "risk_score": alert.risk_score.score,
                "explanation": alert.explanation[:500],
            },
        )
        alert.marble_case_id = case.get("case_id")
        alert.assigned_to = "mlro@banxe.com"
        alert.status = AlertStatus.ESCALATED
        alert.audit_trail.append(
            {
                "action": "routed_critical",
                "marble_case_id": case.get("case_id"),
                "assigned_to": "mlro@banxe.com",
            }
        )
        self._store.save(alert)
        logger.warning(
            "CRITICAL alert %s → Marble case %s, MLRO assigned",
            alert.alert_id,
            case.get("case_id"),
        )
        return alert

    def _route_high(self, alert: AMLAlert) -> AMLAlert:
        """HIGH: create Marble case, assign to analyst queue."""
        case = self._marble.create_case(
            alert.alert_id,
            {
                "severity": "high",
                "transaction_id": alert.transaction_id,
                "customer_id": alert.customer_id,
                "risk_score": alert.risk_score.score,
            },
        )
        alert.marble_case_id = case.get("case_id")
        alert.assigned_to = "analyst-queue@banxe.com"
        alert.status = AlertStatus.REVIEWING
        alert.audit_trail.append(
            {
                "action": "routed_high",
                "marble_case_id": case.get("case_id"),
            }
        )
        self._store.save(alert)
        logger.info("HIGH alert %s → Marble case %s", alert.alert_id, case.get("case_id"))
        return alert

    def _route_medium(self, alert: AMLAlert) -> AMLAlert:
        """MEDIUM: flag for analyst review, no Marble case yet."""
        alert.assigned_to = "analyst-queue@banxe.com"
        alert.status = AlertStatus.REVIEWING
        alert.audit_trail.append({"action": "routed_medium", "assigned_to": "analyst-queue"})
        self._store.save(alert)
        logger.info("MEDIUM alert %s → analyst queue", alert.alert_id)
        return alert

    def _route_low(self, alert: AMLAlert) -> AMLAlert:
        """LOW: auto-close with audit log entry."""
        from datetime import UTC, datetime

        alert.status = AlertStatus.AUTO_CLOSED
        alert.closed_at = datetime.now(UTC)
        alert.closure_reason = "Auto-closed: risk score below threshold (low risk)"
        alert.audit_trail.append(
            {
                "action": "auto_closed",
                "reason": alert.closure_reason,
                "risk_score": alert.risk_score.score,
            }
        )
        self._store.save(alert)
        logger.info(
            "LOW alert %s auto-closed (score: %.2f)", alert.alert_id, alert.risk_score.score
        )
        return alert
