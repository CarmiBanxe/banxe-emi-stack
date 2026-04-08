"""
tests/test_notification_service.py — NotificationService + MockAdapter unit tests
IL-047 | S17-03 | banxe-emi-stack
"""
import pytest

from services.events.event_bus import BanxeEventType, DomainEvent, InMemoryEventBus
from services.notifications.mock_notification_adapter import MockNotificationAdapter
from services.notifications.notification_port import (
    NotificationChannel,
    NotificationRecipient,
    NotificationRequest,
    NotificationStatus,
    NotificationType,
)
from services.notifications.notification_service import NotificationService


@pytest.fixture()
def adapter() -> MockNotificationAdapter:
    return MockNotificationAdapter()


@pytest.fixture()
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture()
def svc(adapter, bus) -> NotificationService:
    s = NotificationService(adapter=adapter, event_bus=bus)
    s.register_event_handlers()
    return s


def _make_recipient(email: str = "alice@example.com") -> NotificationRecipient:
    return NotificationRecipient(
        customer_id="cust-001",
        email=email,
        marketing_consent=True,
    )


def _make_request(
    notif_type: NotificationType = NotificationType.PAYMENT_SENT,
    channel: NotificationChannel = NotificationChannel.EMAIL,
    recipient: NotificationRecipient | None = None,
    transactional: bool = True,
) -> NotificationRequest:
    return NotificationRequest.create(
        notification_type=notif_type,
        channel=channel,
        recipient=recipient or _make_recipient(),
        template_vars={"amount": "100.00", "currency": "£", "creditor_name": "Bob"},
        transactional=transactional,
    )


# ── MockNotificationAdapter ───────────────────────────────────────────────────

def test_send_returns_sent_status(adapter):
    req = _make_request()
    result = adapter.send(req)
    assert result.status == NotificationStatus.SENT


def test_send_records_notification_id(adapter):
    req = _make_request()
    result = adapter.send(req)
    assert result.notification_id == req.notification_id


def test_send_sets_provider_reference(adapter):
    req = _make_request()
    result = adapter.send(req)
    assert result.provider_reference is not None
    assert result.provider_reference.startswith("mock-")


def test_send_sets_sent_at(adapter):
    req = _make_request()
    result = adapter.send(req)
    assert result.sent_at is not None


def test_send_bounce_pattern_triggers_bounce(adapter):
    recipient = NotificationRecipient(
        customer_id="cust-bad",
        email="bounce@example.com",
    )
    req = _make_request(recipient=recipient)
    result = adapter.send(req)
    assert result.status == NotificationStatus.BOUNCED


def test_marketing_without_consent_suppressed(adapter):
    recipient = NotificationRecipient(
        customer_id="cust-001",
        email="alice@example.com",
        marketing_consent=False,
    )
    req = _make_request(
        notif_type=NotificationType.CUSTOMER_WELCOME,
        transactional=False,
        recipient=recipient,
    )
    result = adapter.send(req)
    assert result.status == NotificationStatus.SUPPRESSED


def test_marketing_with_consent_sent(adapter):
    recipient = NotificationRecipient(
        customer_id="cust-001",
        email="alice@example.com",
        marketing_consent=True,
    )
    req = _make_request(transactional=False, recipient=recipient)
    result = adapter.send(req)
    assert result.status == NotificationStatus.SENT


def test_get_delivery_status_returns_result(adapter):
    req = _make_request()
    adapter.send(req)
    result = adapter.get_delivery_status(req.notification_id)
    assert result is not None
    assert result.notification_id == req.notification_id


def test_get_delivery_status_unknown_returns_none(adapter):
    assert adapter.get_delivery_status("no-such-id") is None


def test_adapter_health_returns_true(adapter):
    assert adapter.health() is True


def test_count_by_channel(adapter):
    adapter.send(_make_request(channel=NotificationChannel.EMAIL))
    adapter.send(_make_request(channel=NotificationChannel.EMAIL))
    assert adapter.count_by_channel(NotificationChannel.EMAIL) == 2


def test_count_by_status_sent(adapter):
    adapter.send(_make_request())
    assert adapter.count_by_status(NotificationStatus.SENT) == 1


def test_reset_clears_all(adapter):
    adapter.send(_make_request())
    adapter.reset()
    assert adapter.all_sent == []


# ── NotificationService ───────────────────────────────────────────────────────

def test_service_send_success(svc, adapter):
    req = _make_request()
    result = svc.send(req)
    assert result.status == NotificationStatus.SENT


def test_service_health(svc):
    assert svc.health() is True


def test_event_triggers_notification(svc, adapter, bus):
    event = DomainEvent.create(
        event_type=BanxeEventType.PAYMENT_COMPLETED,
        source_service="payment_service",
        payload={
            "customer_email": "alice@example.com",
            "amount": "100.00",
            "currency": "GBP",
        },
        customer_id="cust-001",
    )
    bus.publish(event)
    assert adapter.count_by_status(NotificationStatus.SENT) == 1


def test_kyc_approved_event_triggers_notification(svc, adapter, bus):
    event = DomainEvent.create(
        event_type=BanxeEventType.KYC_APPROVED,
        source_service="kyc_service",
        payload={"customer_email": "alice@example.com"},
        customer_id="cust-001",
    )
    bus.publish(event)
    assert adapter.count_by_status(NotificationStatus.SENT) >= 1


def test_render_body_payment_sent(svc):
    body = svc.render_body(
        NotificationType.PAYMENT_SENT,
        {"amount": "50.00", "currency": "£", "creditor_name": "Bob", "rail": "FPS", "reference": "REF-1"},
    )
    assert "50.00" in body
    assert "Bob" in body


def test_render_body_missing_vars_safe(svc):
    body = svc.render_body(NotificationType.PAYMENT_SENT, {})
    assert body  # Should not raise, just leaves placeholders


def test_render_subject_contains_key_info(svc):
    subject = svc.render_subject(
        NotificationType.PAYMENT_SENT,
        {"currency": "£", "amount": "100.00", "creditor_name": "Alice"},
    )
    assert "100.00" in subject or "Alice" in subject or "sent" in subject.lower()


def test_get_delivery_status_after_send(svc):
    req = _make_request()
    svc.send(req)
    result = svc.get_delivery_status(req.notification_id)
    assert result is not None
