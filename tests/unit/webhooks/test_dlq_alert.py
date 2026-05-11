"""
test_dlq_alert.py — TelegramDLQAlertHook tests (ADR-034 Step 4).

Verifies that the sync hook produces a CRITICAL Alert with the canonical
message body and routes it through the ADR-033 AlertRoutingPort.

ADR-034 is silent on alert-failure semantics; default (per Step 4 prompt)
is "swallow + don't crash the worker".
"""

from __future__ import annotations

from services.alerting.alert_port import (
    Alert,
    AlertCategory,
    AlertRoutingPort,
    AlertSeverity,
)
from services.alerting.in_memory_adapter import InMemoryAlertAdapter
from services.webhooks.dlq_alert import (
    TelegramDLQAlertHook,
    build_dlq_alert,
    format_dlq_message,
)
from services.webhooks.reliability_port import WebhookDeliveryRecord


def _make_dead_record() -> WebhookDeliveryRecord:
    return WebhookDeliveryRecord(
        event_id="ev-1",
        payload={"applicantId": "a1"},
        target_url="https://kc/hook",
        attempt=3,
        next_retry_at=1234.5,
        status="dead",
        last_error="upstream 500",
    )


def test_format_dlq_message_canonical_layout() -> None:
    msg = format_dlq_message(_make_dead_record())
    assert "WEBHOOK_DLQ" in msg
    assert "event_id=ev-1" in msg
    assert "target=https://kc/hook" in msg
    assert "attempts=3" in msg
    assert "last_error=upstream 500" in msg


def test_build_dlq_alert_is_critical_generic_with_metadata() -> None:
    alert: Alert = build_dlq_alert(_make_dead_record())
    assert alert.category == AlertCategory.GENERIC
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.title == "WEBHOOK_DLQ event_id=ev-1"
    assert alert.body == format_dlq_message(_make_dead_record())
    assert alert.metadata == {
        "event_id": "ev-1",
        "target_url": "https://kc/hook",
        "attempts": 3,
        "last_error": "upstream 500",
    }
    assert alert.owner == "CTIO"


async def test_dlq_hook_invokes_sender_in_async_context() -> None:
    """When called from inside a running loop, the hook schedules a task that
    eventually delivers the alert to the sink."""
    import asyncio

    sink = InMemoryAlertAdapter()
    hook = TelegramDLQAlertHook(alert_port=sink)
    hook(_make_dead_record())
    # Yield to let the scheduled task run.
    for _ in range(5):
        await asyncio.sleep(0)
    assert len(sink.alerts) == 1
    delivered = sink.alerts[0]
    assert delivered.severity == AlertSeverity.CRITICAL
    assert delivered.category == AlertCategory.GENERIC
    assert "event_id=ev-1" in delivered.body


def test_dlq_hook_swallows_sender_exceptions_no_crash_to_worker() -> None:
    """A broken async alert sink must not raise into the worker."""

    class BrokenSink(AlertRoutingPort):
        async def send_alert(self, alert: Alert) -> bool:
            raise RuntimeError("sink kaput")

        async def health_check(self) -> bool:
            return False

    hook = TelegramDLQAlertHook(alert_port=BrokenSink())
    # No running loop here → hook takes the asyncio.run branch + swallow.
    hook(_make_dead_record())  # must not raise
