"""
delivery_client.py — Webhook delivery client Protocol (ADR-034 Step 3).

Abstracts the transport that the async worker uses to actually push a webhook
payload to its target. Production binds to an HTTP client (httpx/aiohttp);
dev/test binds to InMemoryDeliveryClient with deterministic per-URL behaviour.

The worker remains transport-agnostic: it only cares about a DeliveryResult.
No exceptions cross the worker→port boundary as success; the worker traps and
maps exceptions to mark_failed(...).

Pure typing — no I/O, no side effects in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class DeliveryResult:
    """Outcome of a single webhook delivery attempt.

    success:     terminal-success flag; True → port.mark_delivered
    status_code: HTTP-like status code if the transport returned one, else None
    error:       human-readable error if !success; empty for success
    """

    success: bool
    status_code: int | None = None
    error: str | None = None


class WebhookDeliveryClient(Protocol):
    """Port for the actual delivery transport (HTTP in prod, in-memory in tests)."""

    async def deliver(
        self,
        target_url: str,
        payload: dict,
        timeout_s: float,
    ) -> DeliveryResult:
        """Attempt one delivery. MUST NOT raise on transport failure — return
        DeliveryResult(success=False, error=...). May raise only on programmer
        error (e.g. invalid argument types)."""
        ...
