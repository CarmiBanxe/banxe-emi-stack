"""ADR-033 Step 1: N8nTelegramAlertAdapter — routes alerts to n8n webhook.

n8n flow then forwards to Telegram. Default endpoint is the LAN n8n instance
on evo2 (192.168.0.72:5678). Override via ALERT_N8N_WEBHOOK_URL env var.
"""

from __future__ import annotations

from dataclasses import asdict
import os
from typing import Any

import httpx

from .alert_port import Alert, AlertRoutingPort

_DEFAULT_WEBHOOK_URL = "http://192.168.0.72:5678/webhook/kc-events"


class N8nTelegramAlertAdapter(AlertRoutingPort):
    def __init__(self, webhook_url: str | None = None, timeout: float = 10.0) -> None:
        self._webhook_url = (
            webhook_url or os.environ.get("ALERT_N8N_WEBHOOK_URL") or _DEFAULT_WEBHOOK_URL
        )
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send_alert(self, alert: Alert) -> bool:
        payload: dict[str, Any] = asdict(alert)
        payload["category"] = alert.category.value
        payload["severity"] = alert.severity.value
        payload["timestamp"] = alert.timestamp.isoformat()
        try:
            response = await self._client.post(self._webhook_url, json=payload)
        except httpx.HTTPError:
            return False
        return 200 <= response.status_code < 300

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(self._webhook_url)
        except httpx.HTTPError:
            return False
        return response.status_code < 500

    async def close(self) -> None:
        await self._client.aclose()
