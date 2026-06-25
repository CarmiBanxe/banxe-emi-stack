"""
services/observability/metrics_collector.py
Metrics collector for platform observability (IL-OBS-01).
BT-008: push_to_grafana() logs intent (I-24); no-op until Grafana is provisioned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class MetricsSnapshot:
    test_count: int
    endpoint_count: int
    mcp_tool_count: int
    passport_count: int
    coverage_pct: Decimal  # I-01: always Decimal
    collected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class MetricsCollector:
    """Collects platform metrics for observability dashboard.

    BT-008: push_to_grafana() is a stub — requires real Grafana instance.
    """

    # Sprint 38 baseline (after integration tests added)
    _BASELINE = {
        "test_count": 8100,
        "endpoint_count": 453,
        "mcp_tool_count": 228,
        "passport_count": 57,
        "coverage_pct": Decimal("82.5"),
    }

    def __init__(self, overrides: dict | None = None) -> None:
        self._config = {**self._BASELINE, **(overrides or {})}
        self._grafana_log: list[dict] = []  # I-24 append-only push attempts

    def collect(self) -> MetricsSnapshot:
        """Collect current platform metrics."""
        return MetricsSnapshot(
            test_count=self._config["test_count"],
            endpoint_count=self._config["endpoint_count"],
            mcp_tool_count=self._config["mcp_tool_count"],
            passport_count=self._config["passport_count"],
            coverage_pct=Decimal(str(self._config["coverage_pct"])),
        )

    def push_to_grafana(self, snapshot: MetricsSnapshot) -> None:
        """BT-008: Log push intent — no-op until Grafana is provisioned (P1).

        I-24: appends to grafana_log for traceability.
        Real push wired at P1 via GRAFANA_URL env var + HTTP adapter.
        """
        self._grafana_log.append(
            {
                "event": "grafana_push.queued",
                "test_count": snapshot.test_count,
                "coverage_pct": str(snapshot.coverage_pct),
                "collected_at": snapshot.collected_at,
                "queued_at": datetime.now(UTC).isoformat(),
                "delivered": False,
            }
        )

    @property
    def grafana_log(self) -> list[dict]:
        return list(self._grafana_log)
