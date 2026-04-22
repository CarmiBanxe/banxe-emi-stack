"""
services/observability/health_aggregator.py
Health aggregator for all P0 services (IL-OBS-01).
I-24: HealthLog is append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class ServiceHealth:
    service: str
    status: ServiceStatus
    message: str
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class SystemHealthReport:
    overall_status: ServiceStatus
    services: list[ServiceHealth]
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def healthy_count(self) -> int:
        return sum(1 for s in self.services if s.status == ServiceStatus.HEALTHY)

    @property
    def unhealthy_count(self) -> int:
        return sum(1 for s in self.services if s.status == ServiceStatus.UNHEALTHY)


class HealthCheckPort(Protocol):
    """Port for checking service health (Protocol DI pattern)."""

    async def ping(self, service: str) -> bool: ...


class InMemoryHealthCheckPort:
    """In-memory stub — all services healthy by default."""

    def __init__(self, overrides: dict[str, bool] | None = None) -> None:
        self._overrides: dict[str, bool] = overrides or {}

    async def ping(self, service: str) -> bool:
        return self._overrides.get(service, True)


class HealthAggregator:
    """Aggregates health of all P0 stack services.

    Services checked: postgres, clickhouse, redis, frankfurter, pgaudit, api.
    """

    SERVICES = ["postgres", "clickhouse", "redis", "frankfurter", "pgaudit", "api"]

    def __init__(self, port: HealthCheckPort | None = None) -> None:
        self._port: HealthCheckPort = port or InMemoryHealthCheckPort()
        self._log: list[SystemHealthReport] = []  # I-24 append-only

    async def check_all(self) -> SystemHealthReport:
        service_healths: list[ServiceHealth] = []
        for svc in self.SERVICES:
            try:
                ok = await self._port.ping(svc)
                status = ServiceStatus.HEALTHY if ok else ServiceStatus.UNHEALTHY
                msg = "OK" if ok else f"{svc} did not respond"
            except Exception as exc:
                status = ServiceStatus.UNHEALTHY
                msg = str(exc)
            service_healths.append(ServiceHealth(service=svc, status=status, message=msg))

        unhealthy_count = sum(1 for s in service_healths if s.status == ServiceStatus.UNHEALTHY)
        degraded_count = sum(1 for s in service_healths if s.status == ServiceStatus.DEGRADED)

        if unhealthy_count > 0:
            overall = ServiceStatus.UNHEALTHY
        elif degraded_count > 0:
            overall = ServiceStatus.DEGRADED
        else:
            overall = ServiceStatus.HEALTHY

        report = SystemHealthReport(overall_status=overall, services=service_healths)
        self._log.append(report)  # I-24
        return report

    async def check_service(self, service: str) -> ServiceHealth:
        """Check health of a single named service."""
        if service not in self.SERVICES:
            return ServiceHealth(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message=f"Unknown service: {service}",
            )
        try:
            ok = await self._port.ping(service)
            status = ServiceStatus.HEALTHY if ok else ServiceStatus.UNHEALTHY
            msg = "OK" if ok else f"{service} did not respond"
        except Exception as exc:
            status = ServiceStatus.UNHEALTHY
            msg = str(exc)
        return ServiceHealth(service=service, status=status, message=msg)

    @property
    def health_log(self) -> list[SystemHealthReport]:
        """I-24: append-only health log."""
        return list(self._log)
