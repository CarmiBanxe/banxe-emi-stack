"""ADR-033 Step 1: InMemoryAlertAdapter — test double for AlertRoutingPort."""

from __future__ import annotations

from .alert_port import Alert, AlertRoutingPort


class InMemoryAlertAdapter(AlertRoutingPort):
    def __init__(self, healthy: bool = True) -> None:
        self._healthy = healthy
        self.alerts: list[Alert] = []

    async def send_alert(self, alert: Alert) -> bool:
        if not self._healthy:
            return False
        self.alerts.append(alert)
        return True

    async def health_check(self) -> bool:
        return self._healthy
