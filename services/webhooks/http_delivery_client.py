"""
http_delivery_client.py — httpx-backed WebhookDeliveryClient (ADR-034 Step 4).

Single HTTP POST per delivery attempt. Returns a DeliveryResult; never raises
on transport failure — retry policy is the Port's responsibility, not the
client's.

Mapping:
  2xx                 → DeliveryResult(success=True, status_code=<int>)
  non-2xx             → DeliveryResult(success=False, status_code=<int>,
                                       error="http <code>")
  httpx.HTTPError     → DeliveryResult(success=False, status_code=None,
                                       error="<exc-class>: <msg>")
"""

from __future__ import annotations

import httpx

from services.webhooks.delivery_client import DeliveryResult, WebhookDeliveryClient


class HttpWebhookDeliveryClient(WebhookDeliveryClient):
    """Real HTTP delivery client backed by httpx.AsyncClient."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client if client is not None else httpx.AsyncClient()
        self._owns_client = client is None

    async def deliver(
        self,
        target_url: str,
        payload: dict,
        timeout_s: float,
    ) -> DeliveryResult:
        try:
            response = await self._client.post(
                target_url,
                json=payload,
                timeout=timeout_s,
            )
        except httpx.HTTPError as exc:
            return DeliveryResult(
                success=False,
                status_code=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        if 200 <= response.status_code < 300:
            return DeliveryResult(
                success=True,
                status_code=response.status_code,
                error=None,
            )
        return DeliveryResult(
            success=False,
            status_code=response.status_code,
            error=f"http {response.status_code}",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
