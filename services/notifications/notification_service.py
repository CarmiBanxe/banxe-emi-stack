"""
services/notifications/notification_service.py — Notification orchestration service
IL-047 | S17-03 | banxe-emi-stack

Subscribes to domain events from EventBus and dispatches notifications
via the NotificationPort adapter (Mock / SendGrid / Twilio).

Responsibilities:
  1. Map BanxeEventType → NotificationType + channel + template_vars
  2. Resolve recipient (customer_id → email/phone/telegram)
  3. Enforce GDPR consent gate for marketing notifications
  4. Delegate to NotificationPort.send()
  5. Return NotificationResult for caller

FCA compliance:
  - COBS 2.2A: clear, fair, non-misleading customer communications
  - GDPR Art.6: lawful basis per notification type
  - I-24: all results logged (handled by adapter)
"""
from __future__ import annotations

import logging
from typing import Optional

from services.events.event_bus import BanxeEventType, DomainEvent, InMemoryEventBus
from services.notifications.notification_port import (
    NotificationChannel,
    NotificationPort,
    NotificationRecipient,
    NotificationRequest,
    NotificationResult,
    NotificationType,
)

logger = logging.getLogger(__name__)


# ── Message templates (COBS 2.2: clear, fair, not misleading) ─────────────────

_TEMPLATES: dict[NotificationType, dict] = {
    NotificationType.PAYMENT_SENT: {
        "subject": "Payment sent: {currency}{amount} to {creditor_name}",
        "body": (
            "Your payment of {currency}{amount} to {creditor_name} "
            "has been sent via {rail}. Reference: {reference}."
        ),
    },
    NotificationType.PAYMENT_FAILED: {
        "subject": "Payment failed: {currency}{amount}",
        "body": (
            "Your payment of {currency}{amount} to {creditor_name} "
            "could not be processed. Reason: {failure_reason}. "
            "Please contact support if you need assistance."
        ),
    },
    NotificationType.PAYMENT_RECEIVED: {
        "subject": "You received {currency}{amount}",
        "body": (
            "{currency}{amount} has been credited to your account "
            "from {debtor_name}. Reference: {reference}."
        ),
    },
    NotificationType.PAYMENT_FROZEN: {
        "subject": "Payment held for review",
        "body": (
            "A payment has been placed on hold for compliance review. "
            "Our team will contact you within 1 business day. "
            "Reference: {reference}."
        ),
    },
    NotificationType.KYC_APPROVED: {
        "subject": "Identity verified — your account is now active",
        "body": (
            "Great news! Your identity has been verified. "
            "Your Banxe account is now fully active."
        ),
    },
    NotificationType.KYC_REJECTED: {
        "subject": "Identity verification unsuccessful",
        "body": (
            "We were unable to verify your identity. "
            "Reason: {rejection_reason}. "
            "Please contact support to discuss next steps."
        ),
    },
    NotificationType.KYC_EDD_REQUIRED: {
        "subject": "Additional verification required",
        "body": (
            "We need some additional information to complete your verification. "
            "Please log in to provide the required documents."
        ),
    },
    NotificationType.CUSTOMER_WELCOME: {
        "subject": "Welcome to Banxe",
        "body": (
            "Welcome to Banxe! Your account has been created. "
            "Complete your identity verification to start transacting."
        ),
    },
    NotificationType.CUSTOMER_ACTIVATED: {
        "subject": "Your Banxe account is active",
        "body": "Your account is fully set up and ready to use.",
    },
    NotificationType.SAFEGUARDING_SHORTFALL: {
        "subject": "[MLRO ALERT] Safeguarding discrepancy detected",
        "body": (
            "URGENT: Safeguarding reconciliation identified a discrepancy. "
            "Internal balance: {internal_balance}. "
            "External balance: {external_balance}. "
            "Delta: {delta}. Date: {recon_date}. "
            "FCA CASS 7.15.29R action required within 1 business day."
        ),
    },
    NotificationType.AGREEMENT_PENDING: {
        "subject": "Action required: review and sign your agreement",
        "body": (
            "A new terms and conditions agreement is ready for your review. "
            "Please log in to sign your agreement."
        ),
    },
    NotificationType.COMPLAINT_RECEIVED: {
        "subject": "We have received your complaint",
        "body": (
            "Thank you for contacting us. We have received your complaint "
            "(ref: {complaint_ref}) and will respond within 5 business days "
            "as required by FCA DISP 1."
        ),
    },
    NotificationType.COMPLAINT_RESOLVED: {
        "subject": "Your complaint has been resolved",
        "body": (
            "Your complaint (ref: {complaint_ref}) has been resolved. "
            "We hope you are satisfied with the outcome. "
            "If not, you may refer this to the Financial Ombudsman Service."
        ),
    },
}


# ── Event → notification mapping ───────────────────────────────────────────────

_EVENT_NOTIFICATION_MAP: dict[
    BanxeEventType,
    tuple[NotificationType, NotificationChannel, bool],  # type, channel, transactional
] = {
    BanxeEventType.PAYMENT_COMPLETED: (
        NotificationType.PAYMENT_SENT, NotificationChannel.EMAIL, True
    ),
    BanxeEventType.PAYMENT_FAILED: (
        NotificationType.PAYMENT_FAILED, NotificationChannel.EMAIL, True
    ),
    BanxeEventType.KYC_APPROVED: (
        NotificationType.KYC_APPROVED, NotificationChannel.EMAIL, True
    ),
    BanxeEventType.KYC_REJECTED: (
        NotificationType.KYC_REJECTED, NotificationChannel.EMAIL, True
    ),
    BanxeEventType.KYC_EDD_REQUIRED: (
        NotificationType.KYC_EDD_REQUIRED, NotificationChannel.EMAIL, True
    ),
    BanxeEventType.CUSTOMER_CREATED: (
        NotificationType.CUSTOMER_WELCOME, NotificationChannel.EMAIL, True
    ),
    BanxeEventType.CUSTOMER_ACTIVATED: (
        NotificationType.CUSTOMER_ACTIVATED, NotificationChannel.EMAIL, True
    ),
    BanxeEventType.SAFEGUARDING_SHORTFALL: (
        NotificationType.SAFEGUARDING_SHORTFALL, NotificationChannel.TELEGRAM, True
    ),
    BanxeEventType.AGREEMENT_CREATED: (
        NotificationType.AGREEMENT_PENDING, NotificationChannel.EMAIL, True
    ),
}


class NotificationService:
    """
    Orchestrates notification dispatch in response to domain events.

    Usage:
        adapter = MockNotificationAdapter()
        bus = InMemoryEventBus()
        svc = NotificationService(adapter=adapter, event_bus=bus)
        svc.register_event_handlers()
        # Events published to bus now trigger notifications automatically.
    """

    def __init__(
        self,
        adapter: NotificationPort,
        event_bus: Optional[InMemoryEventBus] = None,
    ) -> None:
        self._adapter = adapter
        self._event_bus = event_bus

    def register_event_handlers(self) -> None:
        """Subscribe to all relevant domain events on the event bus."""
        if self._event_bus is None:
            logger.warning(
                "No event bus provided — event-driven notifications disabled"
            )
            return
        for event_type in _EVENT_NOTIFICATION_MAP:
            self._event_bus.subscribe(event_type, self._handle_event)
        logger.info(
            "NotificationService subscribed to %d event types",
            len(_EVENT_NOTIFICATION_MAP),
        )

    def _handle_event(self, event: DomainEvent) -> None:
        """Internal EventBus handler — translates domain event to notification."""
        mapping = _EVENT_NOTIFICATION_MAP.get(event.event_type)
        if mapping is None:
            return

        notif_type, channel, transactional = mapping
        recipient = self._build_recipient(event)
        template_vars = event.payload

        request = NotificationRequest.create(
            notification_type=notif_type,
            channel=channel,
            recipient=recipient,
            template_vars=template_vars,
            transactional=transactional,
            correlation_id=event.event_id,
        )
        result = self.send(request)
        logger.info(
            "Event %s → notification %s [%s]",
            event.event_type, notif_type, result.status,
        )

    def send(self, request: NotificationRequest) -> NotificationResult:
        """
        Directly send a notification (bypassing event bus).
        Use for programmatic dispatch (e.g. from API endpoints).
        """
        result = self._adapter.send(request)
        return result

    def get_delivery_status(
        self, notification_id: str
    ) -> Optional[NotificationResult]:
        return self._adapter.get_delivery_status(notification_id)

    def render_body(
        self, notification_type: NotificationType, template_vars: dict
    ) -> str:
        """
        Render notification body from template + vars.
        FCA COBS 2.2: returned string must be clear, fair, not misleading.
        """
        template = _TEMPLATES.get(notification_type)
        if template is None:
            return f"Notification: {notification_type.value}"
        try:
            return template["body"].format_map(
                _SafeFormatDict(template_vars)
            )
        except Exception:
            return template["body"]

    def render_subject(
        self, notification_type: NotificationType, template_vars: dict
    ) -> str:
        """Render notification subject from template + vars."""
        template = _TEMPLATES.get(notification_type)
        if template is None:
            return notification_type.value
        try:
            return template.get("subject", "").format_map(
                _SafeFormatDict(template_vars)
            )
        except Exception:
            return template.get("subject", notification_type.value)

    def _build_recipient(self, event: DomainEvent) -> NotificationRecipient:
        """
        Build recipient from event payload.
        In production: would fetch from customer profile service.
        In sandbox: uses payload fields directly.
        """
        payload = event.payload
        return NotificationRecipient(
            customer_id=event.customer_id,
            email=payload.get("customer_email") or payload.get("email"),
            phone=payload.get("customer_phone") or payload.get("phone"),
            telegram_chat_id=payload.get("telegram_chat_id"),
            marketing_consent=payload.get("marketing_consent", False),
        )

    def health(self) -> bool:
        return self._adapter.health()


class _SafeFormatDict(dict):
    """dict subclass: returns '{key}' for missing keys instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"
