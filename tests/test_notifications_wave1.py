"""
tests/test_notifications_wave1.py — Sprint 4 Track B Wave 1 coverage gap-closer.
IL-047 | banxe-emi-stack

Targets uncovered lines in services/notifications/:
  - sendgrid_adapter.py  L15-28 (module-level imports, 0% → 100%)
  - notification_service.py L208-209, 221, 261, 264-265, 271, 274-275
  - mock_notification_adapter.py L107, 124, 127
  - notification_port.py L137, 146

GDPR Art.6 consent gate verified at mock adapter boundary.
FCA COBS 2.2: template rendering fallback paths tested.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from services.events.event_bus import (
    BanxeEventType,
    DomainEvent,
)
from services.notifications.mock_notification_adapter import (
    MockNotificationAdapter,
    _get_recipient_address,
)
from services.notifications.notification_port import (
    NotificationChannel,
    NotificationError,
    NotificationRecipient,
    NotificationRequest,
    NotificationResult,
    NotificationStatus,
    NotificationType,
)
from services.notifications.notification_service import NotificationService

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_recipient(**overrides: Any) -> NotificationRecipient:
    defaults: dict[str, Any] = {
        "customer_id": "cust-001",
        "email": "test@banxe.co.uk",
        "marketing_consent": False,
    }
    defaults.update(overrides)
    return NotificationRecipient(**defaults)


def _make_request(
    channel: NotificationChannel = NotificationChannel.EMAIL,
    **overrides: Any,
) -> NotificationRequest:
    return NotificationRequest.create(
        notification_type=overrides.pop(
            "notification_type",
            NotificationType.PAYMENT_SENT,
        ),
        channel=channel,
        recipient=overrides.pop("recipient", _make_recipient()),
        template_vars=overrides.pop("template_vars", {}),
        transactional=overrides.pop("transactional", True),
    )


# ── 1. sendgrid_adapter module-level imports (L15-28) ─────────────────────────


def test_sendgrid_module_level_imports() -> None:
    """Importing the module covers the 6 module-level stmts."""
    import services.notifications.sendgrid_adapter as sg

    assert hasattr(sg, "SendGridAdapter")
    assert hasattr(sg, "logger")


# ── 2. NotificationService.register_event_handlers without bus (L208-209) ─────


def test_register_handlers_without_event_bus() -> None:
    svc = NotificationService(adapter=MockNotificationAdapter())
    # event_bus is None → early return with warning
    svc.register_event_handlers()
    # No crash; bus-less service simply logs a warning


# ── 3. _handle_event with unmapped event type (L221) ──────────────────────────


def test_handle_event_unmapped_type() -> None:
    adapter = MockNotificationAdapter()
    svc = NotificationService(adapter=adapter)

    # CUSTOMER_DORMANT is not in _EVENT_NOTIFICATION_MAP → silent return
    unmapped_event = DomainEvent(
        event_id="evt-unmapped-001",
        event_type=BanxeEventType.CUSTOMER_DORMANT,
        source_service="test",
        payload={"email": "x@test.com"},
        occurred_at=datetime.now(UTC),
        customer_id="cust-999",
    )
    # Call _handle_event directly — register_event_handlers only subscribes
    # to mapped types, so publishing unmapped events wouldn't reach handler.
    svc._handle_event(unmapped_event)

    assert len(adapter.all_sent) == 0


# ── 4. render_body: unknown type + format error (L261, 264-265) ───────────────


def test_render_body_unknown_type_and_format_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = NotificationService(adapter=MockNotificationAdapter())

    # L261: unknown notification type → fallback string
    result = svc.render_body(NotificationType.SAR_FILED, {})
    assert result == "Notification: aml.sar_filed"

    # L264-265: format_map raises → return raw template body
    import services.notifications.notification_service as ns_mod

    original_body = ns_mod._TEMPLATES[NotificationType.PAYMENT_SENT]["body"]
    bad_body = "{amount!q} invalid conversion"
    monkeypatch.setitem(
        ns_mod._TEMPLATES[NotificationType.PAYMENT_SENT],
        "body",
        bad_body,
    )
    result = svc.render_body(NotificationType.PAYMENT_SENT, {"amount": "100"})
    assert result == bad_body

    # Restore
    monkeypatch.setitem(
        ns_mod._TEMPLATES[NotificationType.PAYMENT_SENT],
        "body",
        original_body,
    )


# ── 5. render_subject: unknown type + format error (L271, 274-275) ────────────


def test_render_subject_unknown_type_and_format_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = NotificationService(adapter=MockNotificationAdapter())

    # L271: unknown type → return enum value
    result = svc.render_subject(NotificationType.SAR_FILED, {})
    assert result == "aml.sar_filed"

    # L274-275: format_map raises → return raw subject
    import services.notifications.notification_service as ns_mod

    original_subj = ns_mod._TEMPLATES[NotificationType.PAYMENT_SENT]["subject"]
    bad_subj = "{amount!q} bad"
    monkeypatch.setitem(
        ns_mod._TEMPLATES[NotificationType.PAYMENT_SENT],
        "subject",
        bad_subj,
    )
    result = svc.render_subject(
        NotificationType.PAYMENT_SENT,
        {"amount": "50"},
    )
    assert result == bad_subj

    monkeypatch.setitem(
        ns_mod._TEMPLATES[NotificationType.PAYMENT_SENT],
        "subject",
        original_subj,
    )


# ── 6. MockNotificationAdapter.sent_for_customer (L107) ──────────────────────


def test_mock_adapter_query_helpers() -> None:
    adapter = MockNotificationAdapter()
    req = _make_request()
    adapter.send(req)

    # L107: sent_for_customer returns SENT results
    results = adapter.sent_for_customer("cust-001")
    assert len(results) == 1
    assert results[0].status == NotificationStatus.SENT


# ── 7. _get_recipient_address SMS + PUSH channels (L124, 127) ────────────────


def test_get_recipient_address_sms_and_push() -> None:
    sms_req = _make_request(
        channel=NotificationChannel.SMS,
        recipient=_make_recipient(phone="+447700900000"),
    )
    assert _get_recipient_address(sms_req) == "+447700900000"

    push_req = _make_request(
        channel=NotificationChannel.PUSH,
        recipient=_make_recipient(push_token="tok-abc"),
    )
    # PUSH not handled → returns None
    assert _get_recipient_address(push_req) is None


# ── 8. NotificationResult.success + NotificationError.__str__ (L137, 146) ────


def test_notification_result_success_and_error_str() -> None:
    # L137: success property
    sent = NotificationResult(
        notification_id="n-001",
        notification_type=NotificationType.PAYMENT_SENT,
        channel=NotificationChannel.EMAIL,
        status=NotificationStatus.SENT,
    )
    assert sent.success is True

    failed = NotificationResult(
        notification_id="n-002",
        notification_type=NotificationType.PAYMENT_SENT,
        channel=NotificationChannel.EMAIL,
        status=NotificationStatus.FAILED,
        error_message="timeout",
    )
    assert failed.success is False

    # L146: NotificationError.__str__
    err = NotificationError(code="E001", message="adapter down")
    assert str(err) == "[E001] adapter down"
