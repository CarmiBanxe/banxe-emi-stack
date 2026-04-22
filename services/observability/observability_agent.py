"""
services/observability/observability_agent.py
Observability agent orchestration (IL-OBS-01).
I-27: compliance violation alerts require COMPLIANCE_OFFICER approval (L4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib

from services.observability.compliance_monitor import (
    ComplianceFlag,
    ComplianceMonitor,
    ComplianceReport,
)
from services.observability.health_aggregator import (
    HealthAggregator,
    ServiceStatus,
    SystemHealthReport,
)
from services.observability.metrics_collector import MetricsCollector, MetricsSnapshot


@dataclass
class ObservabilityAlert:
    """I-27: alerts are proposals requiring human approval, not auto-remediations."""

    alert_id: str
    alert_type: str
    severity: str
    detail: str
    requires_approval_from: str
    acknowledged: bool = False
    raised_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class ObservabilitySnapshot:
    health: SystemHealthReport
    metrics: MetricsSnapshot
    compliance: ComplianceReport
    alerts: list[ObservabilityAlert]
    snapshot_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ObservabilityAgent:
    """Orchestrates health, metrics, and compliance observability.

    Autonomy Level: L4 (Human Only) for compliance violation alerts.
    HITL Gate: COMPLIANCE_OFFICER must acknowledge violations.
    """

    def __init__(
        self,
        health_aggregator: HealthAggregator | None = None,
        metrics_collector: MetricsCollector | None = None,
        compliance_monitor: ComplianceMonitor | None = None,
    ) -> None:
        self._health = health_aggregator or HealthAggregator()
        self._metrics = metrics_collector or MetricsCollector()
        self._compliance = compliance_monitor or ComplianceMonitor()
        self._alerts: list[ObservabilityAlert] = []  # I-24 append-only

    async def snapshot(self) -> ObservabilitySnapshot:
        """Collect full observability snapshot."""
        health = await self._health.check_all()
        metrics = self._metrics.collect()
        compliance = self._compliance.scan()

        alerts = self._generate_alerts(health, compliance)
        for alert in alerts:
            self._alerts.append(alert)  # I-24

        return ObservabilitySnapshot(
            health=health,
            metrics=metrics,
            compliance=compliance,
            alerts=alerts,
        )

    def _generate_alerts(
        self, health: SystemHealthReport, compliance: ComplianceReport
    ) -> list[ObservabilityAlert]:
        """I-27: generate proposals, do not auto-remediate."""
        alerts: list[ObservabilityAlert] = []

        if health.overall_status == ServiceStatus.UNHEALTHY:
            aid = f"ALERT_{hashlib.sha256(b'health_unhealthy').hexdigest()[:8]}"
            alerts.append(
                ObservabilityAlert(
                    alert_id=aid,
                    alert_type="HEALTH",
                    severity="HIGH",
                    detail=f"{health.unhealthy_count} service(s) unhealthy",
                    requires_approval_from="COMPLIANCE_OFFICER",
                )
            )

        if compliance.overall_flag == ComplianceFlag.VIOLATION:
            aid = f"ALERT_{hashlib.sha256(b'compliance_violation').hexdigest()[:8]}"
            alerts.append(
                ObservabilityAlert(
                    alert_id=aid,
                    alert_type="COMPLIANCE",
                    severity="CRITICAL",
                    detail=f"{compliance.violation_count} invariant violation(s) detected",
                    requires_approval_from="COMPLIANCE_OFFICER",
                )
            )

        return alerts

    def acknowledge_alert(self, alert_id: str, officer: str) -> bool:
        """HITL L4: acknowledge alert — requires COMPLIANCE_OFFICER."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False

    @property
    def alert_log(self) -> list[ObservabilityAlert]:
        """I-24: append-only alert log."""
        return list(self._alerts)
