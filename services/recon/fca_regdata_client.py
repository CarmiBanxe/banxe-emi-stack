"""
fca_regdata_client.py — FCA RegData API client
FCA CASS 15.12: breach notification within 1 business day.

Production client submits breach records to FCA RegData API.
Sandbox/test environments use MockFCARegDataClient (no real API calls).

FCA RegData API documentation: https://regdata.fca.org.uk/api/docs
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from services.recon.breach_detector import BreachRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationResult:
    """Result of an FCA RegData breach notification submission."""

    success: bool
    fca_reference: str  # FCA-assigned reference number (empty string if failed)
    submitted_at: str   # ISO-8601 datetime of submission
    error: str | None = None  # Error message if success=False


class FCARegDataClientProtocol(Protocol):
    """Protocol for FCA RegData API (test injection point)."""

    def submit_breach_notification(self, breach: BreachRecord) -> NotificationResult:
        """Submit a safeguarding breach notification to FCA RegData.

        FCA CASS 15.12: must be submitted within 1 business day of detection.
        """
        ...


class FCARegDataClient:
    """
    Production FCA RegData API client.

    Submits breach notifications to FCA RegData portal.
    Requires FCA_REGDATA_URL, FCA_REGDATA_API_KEY, FCA_FIRM_REFERENCE in env.

    Phase 0 (sandbox): All these env vars are empty → MockFCARegDataClient is used.
    Phase 1 (production): Set env vars → this client submits to real FCA API.
    """

    def __init__(self) -> None:
        self._url = os.environ.get("FCA_REGDATA_URL", "https://regdata.fca.org.uk")
        self._api_key = os.environ.get("FCA_REGDATA_API_KEY", "")
        self._firm_ref = os.environ.get("FCA_FIRM_REFERENCE", "")

    def submit_breach_notification(self, breach: BreachRecord) -> NotificationResult:
        """
        Submit a safeguarding breach notification to FCA RegData API.

        Endpoint: POST /api/v1/notifications/safeguarding-breach
        Auth: Bearer token via FCA_REGDATA_API_KEY
        FCA basis: CASS 15.12, PS25/12

        Returns NotificationResult with FCA reference number on success.
        """
        submitted_at = datetime.now(UTC).isoformat()

        if not self._api_key:
            logger.error(
                "FCA_REGDATA_API_KEY not set — cannot submit breach notification for %s",
                breach.account_id,
            )
            return NotificationResult(
                success=False,
                fca_reference="",
                submitted_at=submitted_at,
                error="FCA_REGDATA_API_KEY not configured",
            )

        payload = {
            "firmReference": self._firm_ref,
            "notificationType": "SAFEGUARDING_BREACH",
            "fcaBasis": "CASS 15.12 / PS25/12",
            "accountId": breach.account_id,
            "accountType": breach.account_type,
            "currency": breach.currency,
            "discrepancyAmount": str(breach.discrepancy),
            "daysOutstanding": breach.days_outstanding,
            "firstDetected": breach.first_seen.isoformat(),
            "latestDate": breach.latest_date.isoformat(),
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self._url}/api/v1/notifications/safeguarding-breach",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "X-Firm-Reference": self._firm_ref,
                    },
                )
                response.raise_for_status()
                result_data = response.json()
                fca_ref = result_data.get("referenceNumber", result_data.get("reference", ""))
                logger.info(
                    "FCA breach notification submitted: account=%s fca_ref=%s",
                    breach.account_id,
                    fca_ref,
                )
                return NotificationResult(
                    success=True,
                    fca_reference=fca_ref,
                    submitted_at=submitted_at,
                )

        except httpx.HTTPStatusError as exc:
            error_msg = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error(
                "FCA RegData submission failed for %s: %s",
                breach.account_id,
                error_msg,
            )
            return NotificationResult(
                success=False,
                fca_reference="",
                submitted_at=submitted_at,
                error=error_msg,
            )
        except httpx.RequestError as exc:
            error_msg = f"Connection error: {exc}"
            logger.error(
                "FCA RegData connection failed for %s: %s",
                breach.account_id,
                error_msg,
            )
            return NotificationResult(
                success=False,
                fca_reference="",
                submitted_at=submitted_at,
                error=error_msg,
            )


class MockFCARegDataClient:
    """
    Sandbox/test stub — does NOT call FCA RegData API.

    Records notifications for test assertion.
    Use in all non-production environments.

    Usage:
        client = MockFCARegDataClient()
        result = client.submit_breach_notification(breach)
        assert result.success is True
        assert len(client.notifications) == 1
    """

    def __init__(self) -> None:
        self.notifications: list[dict] = []

    def submit_breach_notification(self, breach: BreachRecord) -> NotificationResult:
        """Record a mock breach notification and return a fake FCA reference."""
        submitted_at = datetime.now(UTC).isoformat()
        mock_ref = f"FCA-SANDBOX-{breach.account_id[:8].upper()}-{breach.latest_date.strftime('%Y%m%d')}"

        self.notifications.append(
            {
                "breach_account_id": breach.account_id,
                "account_type": breach.account_type,
                "currency": breach.currency,
                "discrepancy": str(breach.discrepancy),
                "days_outstanding": breach.days_outstanding,
                "fca_reference": mock_ref,
                "submitted_at": submitted_at,
                "is_mock": True,
            }
        )

        logger.info(
            "MockFCARegDataClient: recorded notification for %s (ref=%s) — SANDBOX ONLY",
            breach.account_id,
            mock_ref,
        )

        return NotificationResult(
            success=True,
            fca_reference=mock_ref,
            submitted_at=submitted_at,
        )
