"""FCA safeguarding breach notification port + adapters.

CASS 7.15.29G — breach must be notified within 1 business day of discovery.
PS23/3 §3.49  — enhanced breach notification requirements from 7 May 2026.

Dispatch flow:
  1. N8nFcaBreachNotifier → POST to n8n /webhook/fca-breach-alert
     n8n workflow: sends Telegram/email to MLRO + CEO (L2: alert → human)
  2. FCA Connect portal submission is HITL-only (CFO must manually confirm).
     This adapter triggers the MLRO alert; the portal step is gated by I-27.

Protocol DI:
  FcaNotificationPort (Protocol) → N8nFcaBreachNotifier (real)
                                  → InMemoryFcaNotifier  (tests)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import logging
import os
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_N8N_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class FcaNotificationPayload:
    """Immutable breach notification payload (I-01: Decimal for monetary fields)."""

    reference: str  # e.g. "BREACH-2026-06-26-CRITICAL"
    severity: str  # "MINOR" | "MAJOR" | "CRITICAL"
    consecutive_days: int
    shortfall_gbp: Decimal | None  # None when breach has no monetary shortfall
    description: str
    breach_date: date
    raised_at: datetime


@runtime_checkable
class FcaNotificationPort(Protocol):
    """Port for dispatching FCA safeguarding breach notifications."""

    def notify(self, payload: FcaNotificationPayload) -> None:
        """Dispatch breach notification. Must never raise (log errors instead)."""
        ...


class N8nFcaBreachNotifier:
    """POST to n8n /webhook/fca-breach-alert.

    n8n workflow routes the alert to Telegram (MLRO + CEO) and optionally
    email. FCA Connect portal submission is a separate HITL step.

    Env var: N8N_FCA_WEBHOOK_URL  (required in production)
    """

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url or os.environ.get("N8N_FCA_WEBHOOK_URL", "")

    def notify(self, payload: FcaNotificationPayload) -> None:
        if not self._webhook_url:
            logger.error(
                "N8N_FCA_WEBHOOK_URL not set — FCA breach notification NOT dispatched: %s",
                payload.reference,
            )
            return

        body = {
            "reference": payload.reference,
            "severity": payload.severity,
            "consecutive_days": payload.consecutive_days,
            "shortfall_gbp": str(payload.shortfall_gbp) if payload.shortfall_gbp else None,
            "description": payload.description,
            "breach_date": payload.breach_date.isoformat(),
            "raised_at": payload.raised_at.isoformat(),
        }

        try:
            import httpx  # noqa: PLC0415

            response = httpx.post(
                self._webhook_url,
                json=body,
                timeout=_N8N_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            logger.critical(
                "FCA breach notification dispatched via n8n: %s (HTTP %d)",
                payload.reference,
                response.status_code,
            )
        except Exception as exc:
            logger.error(
                "FCA breach notification FAILED for %s — n8n unreachable: %s",
                payload.reference,
                exc,
            )


class InMemoryFcaNotifier:
    """Test stub — records all notifications without sending.

    Inspect .notifications to assert payload contents in unit tests.
    """

    def __init__(self) -> None:
        self.notifications: list[FcaNotificationPayload] = []

    def notify(self, payload: FcaNotificationPayload) -> None:
        self.notifications.append(payload)
        logger.debug("InMemoryFcaNotifier: recorded %s", payload.reference)

    def clear(self) -> None:
        self.notifications.clear()
