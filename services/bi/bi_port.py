"""
services/bi/bi_port.py
BI Service Port — Protocol Definition (Hexagonal Pattern)
GAP-043 L-bi | IL-CBS-GAP043-BI-2026-06-30

Protocol DI for BI presentation layer (Superset integration).
Enforces structural contracts between BI service and domain logic.
I-01: All amounts/scores as Decimal (never float).
I-24: Audit trail for BI operations (append-only).
"""

from __future__ import annotations

from typing import Protocol


class BIPort(Protocol):
    """Protocol for BI presentation layer (Superset).

    Contracts:
    - get_status() → dict with provider, version, health status
    - list_datasources() → list of connected data sources
    - get_dashboard_count() → count of active dashboards (optional)
    """

    def get_status(self) -> dict[str, str]:
        """Get BI service status.

        Returns:
            dict with keys:
              - status: "ok" | "error"
              - provider: "superset"
              - version: semver string
              - message: optional error description

        Raises:
            BIServiceError: on critical failures
        """
        ...

    def list_datasources(self) -> list[str]:
        """List connected data sources.

        Returns:
            list of datasource names (e.g., ["reporting_analytics", "clickhouse_audit"])
            Empty list if no datasources are configured.

        Raises:
            BIServiceError: on query failures
        """
        ...
