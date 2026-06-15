"""
inmemory_delivery_client.py — Deterministic dev/test double for WebhookDeliveryClient.

Per-URL programmable behaviour:
  "success" → DeliveryResult(success=True, status_code=200)
  "fail"    → DeliveryResult(success=False, status_code=500, error="injected fail")
  "raise"   → raises RuntimeError (worker should map this to mark_failed)

All calls are recorded in an attempt log keyed by target_url for assertions.
No network. No real I/O.
"""

from __future__ import annotations

from services.webhooks.delivery_client import DeliveryResult, WebhookDeliveryClient


class InMemoryDeliveryClient(WebhookDeliveryClient):
    """In-memory delivery client for tests."""

    def __init__(self, behavior: dict[str, str] | None = None) -> None:
        # target_url → "success" | "fail" | "raise". Unknown URLs default to "success".
        self._behavior: dict[str, str] = dict(behavior or {})
        # target_url → list of (payload, timeout_s) tuples, in call order.
        self.attempts: dict[str, list[tuple[dict, float]]] = {}

    def set_behavior(self, target_url: str, behavior: str) -> None:
        self._behavior[target_url] = behavior

    async def deliver(
        self,
        target_url: str,
        payload: dict,
        timeout_s: float,
    ) -> DeliveryResult:
        self.attempts.setdefault(target_url, []).append((dict(payload), timeout_s))
        kind = self._behavior.get(target_url, "success")
        if kind == "success":
            return DeliveryResult(success=True, status_code=200, error=None)
        if kind == "fail":
            return DeliveryResult(success=False, status_code=500, error="injected fail")
        if kind == "raise":
            raise RuntimeError(f"injected raise for {target_url}")
        raise ValueError(f"unknown behaviour {kind!r} for {target_url}")
