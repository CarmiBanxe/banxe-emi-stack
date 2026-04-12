"""
services/transaction_monitor/store/alert_store.py — Alert Store
IL-RTM-01 | banxe-emi-stack

Protocol DI for alert persistence. InMemoryAlertStore for tests.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from services.transaction_monitor.models.alert import AlertSeverity, AlertStatus, AMLAlert

logger = logging.getLogger("banxe.transaction_monitor.alert_store")


@runtime_checkable
class AlertStorePort(Protocol):
    """Interface for alert storage."""

    def save(self, alert: AMLAlert) -> None: ...
    def get(self, alert_id: str) -> AMLAlert | None: ...
    def list_alerts(
        self,
        severity: AlertSeverity | None = None,
        status: AlertStatus | None = None,
        customer_id: str | None = None,
        limit: int = 50,
    ) -> list[AMLAlert]: ...
    def count_by_severity(self) -> dict[str, int]: ...


class InMemoryAlertStore:
    """In-memory alert store for tests and development."""

    def __init__(self) -> None:
        self._alerts: dict[str, AMLAlert] = {}

    def save(self, alert: AMLAlert) -> None:
        self._alerts[alert.alert_id] = alert

    def get(self, alert_id: str) -> AMLAlert | None:
        return self._alerts.get(alert_id)

    def list_alerts(
        self,
        severity: AlertSeverity | None = None,
        status: AlertStatus | None = None,
        customer_id: str | None = None,
        limit: int = 50,
    ) -> list[AMLAlert]:
        alerts = list(self._alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if status:
            alerts = [a for a in alerts if a.status == status]
        if customer_id:
            alerts = [a for a in alerts if a.customer_id == customer_id]
        return sorted(alerts, key=lambda a: a.created_at, reverse=True)[:limit]

    def count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in AlertSeverity}
        for alert in self._alerts.values():
            counts[alert.severity.value] = counts.get(alert.severity.value, 0) + 1
        return counts
