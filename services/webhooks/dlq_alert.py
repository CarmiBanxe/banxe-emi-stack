"""
dlq_alert.py — DLQ exhaustion alert hook (ADR-034 Step 4).

Bridges the sync DLQ-exhaustion callback expected by the redis adapter to the
async ADR-033 AlertRoutingPort. Builds a canonical CRITICAL alert and fires
it on the running event loop (production worker) or via asyncio.run (sync
test or one-shot caller).

Failure behaviour: alert-send exceptions are swallowed. ADR-034 is silent on
alert-sink failure semantics; default is "best-effort, never break delivery".

Canonical message body:
  "WEBHOOK_DLQ event_id=<id> target=<url> attempts=<n> last_error=<err>"
"""

from __future__ import annotations

import asyncio
import contextlib

from services.alerting.alert_port import (
    Alert,
    AlertCategory,
    AlertRoutingPort,
    AlertSeverity,
)
from services.webhooks.reliability_port import WebhookDeliveryRecord


def format_dlq_message(record: WebhookDeliveryRecord) -> str:
    """Canonical one-line DLQ alert body."""
    return (
        f"WEBHOOK_DLQ event_id={record.event_id} "
        f"target={record.target_url} "
        f"attempts={record.attempt} "
        f"last_error={record.last_error}"
    )


def build_dlq_alert(record: WebhookDeliveryRecord) -> Alert:
    return Alert(
        category=AlertCategory.GENERIC,
        severity=AlertSeverity.CRITICAL,
        title=f"WEBHOOK_DLQ event_id={record.event_id}",
        body=format_dlq_message(record),
        metadata={
            "event_id": record.event_id,
            "target_url": record.target_url,
            "attempts": record.attempt,
            "last_error": record.last_error,
        },
        owner="CTIO",
    )


class TelegramDLQAlertHook:
    """Sync hook → async AlertRoutingPort.send_alert.

    If invoked from inside a running event loop, schedules a fire-and-forget
    task. Otherwise creates a one-shot loop via asyncio.run and awaits.
    """

    def __init__(self, alert_port: AlertRoutingPort) -> None:
        self._alert_port = alert_port

    def __call__(self, record: WebhookDeliveryRecord) -> None:
        alert = build_dlq_alert(record)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — caller is fully synchronous.
            with contextlib.suppress(Exception):
                asyncio.run(self._alert_port.send_alert(alert))
            return
        with contextlib.suppress(Exception):
            loop.create_task(self._alert_port.send_alert(alert))
