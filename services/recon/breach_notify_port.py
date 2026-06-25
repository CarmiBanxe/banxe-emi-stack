"""
services/recon/breach_notify_port.py
BreachNotifyPort — Protocol DI for safeguarding.breach.detected event.

D-recon spec §4: when ReconciliationEngine detects a shortfall it emits
`safeguarding.breach.detected` via this port to the K-gabriel workflow,
where a HITL sign-off gate blocks any autonomous FCA submission (I-27).

I-01: All monetary fields are Decimal — never float.
I-24: N8nBreachNotifyAdapter logs every emission; audit trail in engine.
I-27: Downstream K-gabriel is HITL-gated; this port only fires the event.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
import os
from typing import Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

_N8N_TIMEOUT = 5.0


@dataclass(frozen=True)
class BreachEvent:
    """Payload for `safeguarding.breach.detected` (D-recon spec §4).

    I-01: client_funds_total, safeguarding_total, shortfall are Decimal.
    """

    event_type: str  # always "safeguarding.breach.detected"
    recon_id: str
    recon_date: str  # ISO-8601 date string
    currency: str
    client_funds_total: Decimal
    safeguarding_total: Decimal
    shortfall: Decimal  # abs(client_funds - safeguarding); always positive
    detected_at: str  # ISO-8601 datetime UTC
    requires_approval_from: str  # "MLRO"


@runtime_checkable
class BreachNotifyPort(Protocol):
    """Port for emitting `safeguarding.breach.detected` to K-gabriel / n8n.

    Implementations MUST be fail-open: log on error, never raise, so a
    failed notification never breaks the reconciliation audit trail.
    """

    def notify(self, event: BreachEvent) -> None: ...


class InMemoryBreachNotifyPort:
    """Test stub — records all events in order for assertion."""

    def __init__(self) -> None:
        self.events: list[BreachEvent] = []

    def notify(self, event: BreachEvent) -> None:
        self.events.append(event)


class N8nBreachNotifyAdapter:
    """Sends `safeguarding.breach.detected` to n8n :5678 via HTTP POST.

    URL resolution order:
      1. ``webhook_url`` constructor arg (for tests / explicit wiring)
      2. ``N8N_BREACH_NOTIFY_URL`` environment variable
      3. ``N8N_WEBHOOK_URL`` environment variable (legacy fallback)

    If no URL is available, the call is a no-op (logged as WARNING).
    All failures are fail-open: logged as ERROR, never raised.

    Args:
        webhook_url: Optional override URL. Skips env-var lookup when set.
    """

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url

    def _resolved_url(self) -> str | None:
        if self._webhook_url:
            return self._webhook_url
        return os.getenv("N8N_BREACH_NOTIFY_URL") or os.getenv("N8N_WEBHOOK_URL")

    def notify(self, event: BreachEvent) -> None:
        url = self._resolved_url()
        if not url:
            logger.warning(
                "N8nBreachNotifyAdapter: N8N_BREACH_NOTIFY_URL not configured — "
                "breach event not forwarded (recon_id=%s, shortfall=%s)",
                event.recon_id,
                event.shortfall,
            )
            return

        payload = {
            "event_type": event.event_type,
            "recon_id": event.recon_id,
            "recon_date": event.recon_date,
            "currency": event.currency,
            "client_funds_total": str(event.client_funds_total),
            "safeguarding_total": str(event.safeguarding_total),
            "shortfall": str(event.shortfall),
            "detected_at": event.detected_at,
            "requires_approval_from": event.requires_approval_from,
        }
        try:
            resp = httpx.post(url, json=payload, timeout=_N8N_TIMEOUT)
            resp.raise_for_status()
            logger.info(
                "BreachNotifyPort: safeguarding.breach.detected forwarded to n8n "
                "(recon_id=%s, shortfall=%s %s)",
                event.recon_id,
                event.shortfall,
                event.currency,
            )
        except Exception as exc:
            logger.error(
                "N8nBreachNotifyAdapter.notify failed (recon_id=%s): %s. "
                "Breach event NOT forwarded — FCA audit trail in engine intact.",
                event.recon_id,
                exc,
            )
