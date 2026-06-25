"""Compliance service client (IL-CKS-01) for regulatory event logging."""

import logging
from datetime import UTC, datetime
from typing import Dict

import httpx

logger = logging.getLogger(__name__)


class ComplianceClient:
    """Client for compliance-service (IL-CKS-01)."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self._event_log: list[dict] = []  # I-24 append-only

    async def log_regulatory_event(self, event_type: str, details: Dict) -> Dict:
        """Log a regulatory event to compliance service.

        BT-015: Logs locally and returns {} until compliance integration is provisioned (P1).
        I-24: appends to event_log for traceability.
        """
        self._event_log.append(
            {
                "method": "log_regulatory_event",
                "event_type": event_type,
                "queued_at": datetime.now(UTC).isoformat(),
                "provisioned": False,
            }
        )
        logger.warning("ComplianceClient.log_regulatory_event: not provisioned (P1). event_type=%s", event_type)
        return {}

    async def notify_breach(self, breach_data: Dict) -> Dict:
        """Notify compliance service of safeguarding breach.

        BT-015: Logs breach locally at CRITICAL and returns {} until provisioned (P1).
        I-24: appends breach_type to event_log.
        """
        self._event_log.append(
            {
                "method": "notify_breach",
                "breach_type": breach_data.get("breach_type"),
                "queued_at": datetime.now(UTC).isoformat(),
                "provisioned": False,
            }
        )
        logger.critical(
            "ComplianceClient.notify_breach: not provisioned (P1). breach=%s", breach_data.get("breach_type")
        )
        return {}

    async def close(self) -> None:
        await self._client.aclose()
