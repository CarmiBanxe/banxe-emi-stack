"""
services/notifications/notification_port.py — Notification hexagonal port
IL-047 | S17-03 | banxe-emi-stack

Defines the canonical types and NotificationPort Protocol.
All notification adapters (Mock, SendGrid, Twilio) implement NotificationPort.
Business logic depends ONLY on this interface.

FCA compliance:
  - FCA COBS 2.2: communications must be clear, fair and not misleading
  - GDPR Art.6(1)(b): transactional notifications lawful (contract performance)
  - GDPR Art.6(1)(a): marketing requires explicit consent
  - I-24: all sent notifications logged to ClickHouse (5yr retention)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol
import uuid

# ── Enumerations ───────────────────────────────────────────────────────────────


class NotificationChannel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    TELEGRAM = "TELEGRAM"
    PUSH = "PUSH"


class NotificationType(str, Enum):
    # Payment events
    PAYMENT_SENT = "payment.sent"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_FROZEN = "payment.frozen"

    # KYC / Customer lifecycle
    KYC_APPROVED = "kyc.approved"
    KYC_REJECTED = "kyc.rejected"
    KYC_EDD_REQUIRED = "kyc.edd_required"
    CUSTOMER_WELCOME = "customer.welcome"
    CUSTOMER_ACTIVATED = "customer.activated"
    CUSTOMER_DORMANT = "customer.dormant"
    CUSTOMER_OFFBOARDED = "customer.offboarded"

    # Compliance / internal
    SAFEGUARDING_SHORTFALL = "safeguarding.shortfall"  # MLRO only
    SAR_FILED = "aml.sar_filed"  # MLRO only — never to customer
    AGREEMENT_PENDING = "agreement.pending_signature"

    # Operational
    COMPLAINT_RECEIVED = "complaint.received"
    COMPLAINT_RESOLVED = "complaint.resolved"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    SUPPRESSED = "SUPPRESSED"  # Opt-out / consent not given


# ── Domain types ───────────────────────────────────────────────────────────────


@dataclass
class NotificationRecipient:
    """Target for a notification."""

    customer_id: str | None
    email: str | None = None
    phone: str | None = None
    telegram_chat_id: str | None = None
    push_token: str | None = None
    # FCA: marketing_consent must be True for any marketing channel
    marketing_consent: bool = False


@dataclass(frozen=True)
class NotificationRequest:
    """
    Instruction to send a notification to a customer or operator.

    FCA COBS 2.2: template must produce clear, fair, non-misleading content.
    GDPR: transactional=True → lawful basis is contract (no consent needed).
           transactional=False → marketing, requires marketing_consent=True.
    """

    notification_id: str
    notification_type: NotificationType
    channel: NotificationChannel
    recipient: NotificationRecipient
    template_vars: dict = field(default_factory=dict)
    transactional: bool = True  # False = marketing (GDPR consent required)
    correlation_id: str | None = None  # Links to originating event_id

    @classmethod
    def create(
        cls,
        notification_type: NotificationType,
        channel: NotificationChannel,
        recipient: NotificationRecipient,
        template_vars: dict,
        transactional: bool = True,
        correlation_id: str | None = None,
    ) -> NotificationRequest:
        return cls(
            notification_id=str(uuid.uuid4()),
            notification_type=notification_type,
            channel=channel,
            recipient=recipient,
            template_vars=template_vars,
            transactional=transactional,
            correlation_id=correlation_id,
        )


@dataclass
class NotificationResult:
    """Result of a send attempt."""

    notification_id: str
    notification_type: NotificationType
    channel: NotificationChannel
    status: NotificationStatus
    provider_reference: str | None = None  # SendGrid message ID, etc.
    error_message: str | None = None
    sent_at: datetime | None = None

    @property
    def success(self) -> bool:
        return self.status == NotificationStatus.SENT


@dataclass
class NotificationError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ── Port (interface) ───────────────────────────────────────────────────────────


class NotificationPort(Protocol):
    """
    Hexagonal port for notification dispatch.

    Implementations:
      - MockNotificationAdapter  — in-memory, for tests + dev
      - SendGridAdapter          — email via SendGrid (production)
      - TwilioAdapter            — SMS (production, future)
    """

    def send(self, request: NotificationRequest) -> NotificationResult:
        """Dispatch a single notification. Idempotent by notification_id."""
        ...

    def get_delivery_status(self, notification_id: str) -> NotificationResult | None:
        """Fetch current delivery status. Returns None if not found."""
        ...

    def health(self) -> bool:
        """True if the provider is reachable."""
        ...
