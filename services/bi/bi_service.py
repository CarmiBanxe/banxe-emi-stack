"""
services/bi/bi_service.py
BI Service Implementation — InMemory Stub + Base Service
GAP-043 L-bi | IL-CBS-GAP043-BI-2026-06-30

InMemoryBIService for testing and development.
Real Superset adapter to be implemented in production.
I-01: Decimal-safe (no float for financial values).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class InMemoryBIService:
    """InMemory BI service stub for testing.

    Implements BIPort protocol structurally (duck-typing).
    Production: replace with SupersetBIAdapter calling REST API.
    """

    def __init__(self) -> None:
        """Initialize InMemory BI service."""
        self._datasources = [
            "reporting_analytics",
            "safeguarding",
            "clickhouse_audit",
        ]
        self._status = "ok"

    def get_status(self) -> dict[str, str]:
        """Get BI service status.

        Returns:
            {
              "status": "ok",
              "provider": "superset",
              "version": "4.1.1",
            }
        """
        return {
            "status": self._status,
            "provider": "superset",
            "version": "4.1.1",
        }

    def list_datasources(self) -> list[str]:
        """List connected data sources.

        Returns:
            list of datasource names configured in Superset
        """
        return list(self._datasources)

    def set_status(self, status: str) -> None:
        """Set service status (for testing).

        Args:
            status: "ok" or "error"
        """
        self._status = status

    def add_datasource(self, name: str) -> None:
        """Add datasource (for testing).

        Args:
            name: datasource name
        """
        if name not in self._datasources:
            self._datasources.append(name)

    def reset(self) -> None:
        """Reset to default state (for testing)."""
        self._datasources = [
            "reporting_analytics",
            "safeguarding",
            "clickhouse_audit",
        ]
        self._status = "ok"
