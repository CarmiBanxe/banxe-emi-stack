"""
services/notification_hub/models.py
IL-NHB-01 | Phase 18

Domain models, enums, protocols, and in-memory stubs for the Notification Hub.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

# ─── Enums ────────────────────────────────────────────────────────────────────


class Channel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"
    TELEGRAM = "TELEGRAM"
    WEBHOOK = "WEBHOOK"


class NotificationCategory(str, Enum):
    PAYMENT = "PAYMENT"
    KYC = "KYC"
    AML = "AML"
    COMPLIANCE = "COMPLIANCE"
    OPERATIONAL = "OPERATIONAL"
    MARKETING = "MARKETING"
    SECURITY = "SECURITY"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"


class Language(str, Enum):
    EN = "EN"
    FR = "FR"
    RU = "RU"


class Priority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ─── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationTemplate:
    id: str
    name: str
    category: NotificationCategory
    channel: Channel
    language: Language
    subject: str
    body: str
    version: str


@dataclass(frozen=True)
class NotificationPreference:
    entity_id: str
    channel: Channel
    category: NotificationCategory
    opt_in: bool
    updated_at: datetime


@dataclass(frozen=True)
class NotificationRequest:
    id: str
    entity_id: str
    category: NotificationCategory
    channel: Channel
    template_id: str
    context: dict  # type: ignore[type-arg]
    priority: Priority
    created_at: datetime
    actor: str


@dataclass(frozen=True)
class DeliveryRecord:
    id: str
    request_id: str
    entity_id: str
    channel: Channel
    status: DeliveryStatus
    attempted_at: datetime
    delivered_at: datetime | None
    failure_reason: str | None
    retry_count: int
    rendered_subject: str | None
    rendered_body: str


# ─── Protocols ────────────────────────────────────────────────────────────────


@runtime_checkable
class TemplateStorePort(Protocol):
    async def get(self, template_id: str) -> NotificationTemplate | None: ...

    async def list_templates(
        self,
        category: NotificationCategory | None = None,
        channel: Channel | None = None,
    ) -> list[NotificationTemplate]: ...

    async def save(self, template: NotificationTemplate) -> None: ...


@runtime_checkable
class PreferenceStorePort(Protocol):
    async def get(
        self,
        entity_id: str,
        channel: Channel,
        category: NotificationCategory,
    ) -> NotificationPreference | None: ...

    async def save(self, pref: NotificationPreference) -> None: ...

    async def list_by_entity(self, entity_id: str) -> list[NotificationPreference]: ...


@runtime_checkable
class DeliveryStorePort(Protocol):
    async def save(self, record: DeliveryRecord) -> None: ...

    async def get(self, record_id: str) -> DeliveryRecord | None: ...

    async def list_by_entity(self, entity_id: str) -> list[DeliveryRecord]: ...

    async def list_failed(self) -> list[DeliveryRecord]: ...


@runtime_checkable
class ChannelAdapterPort(Protocol):
    async def send(self, record: DeliveryRecord) -> bool: ...


# ─── Seed templates ───────────────────────────────────────────────────────────


_SEED_TEMPLATES = [
    NotificationTemplate(
        id="tmpl-payment-confirmed",
        name="Payment Confirmed",
        category=NotificationCategory.PAYMENT,
        channel=Channel.EMAIL,
        language=Language.EN,
        subject="Your payment of {{ amount }} {{ currency }} has been confirmed",
        body=(
            "Dear {{ name }},\n\n"
            "Your payment of {{ amount }} {{ currency }} to {{ beneficiary }}"
            " has been confirmed.\n\nRef: {{ reference }}"
        ),
        version="v1",
    ),
    NotificationTemplate(
        id="tmpl-kyc-approved",
        name="KYC Approved",
        category=NotificationCategory.KYC,
        channel=Channel.EMAIL,
        language=Language.EN,
        subject="Your identity verification is complete",
        body=("Dear {{ name }},\n\nYour KYC verification has been approved. You can now transact."),
        version="v1",
    ),
    NotificationTemplate(
        id="tmpl-security-alert",
        name="Security Alert",
        category=NotificationCategory.SECURITY,
        channel=Channel.SMS,
        language=Language.EN,
        subject="",
        body="BANXE ALERT: {{ message }}. If this wasn't you, call +44800123456.",
        version="v1",
    ),
]


# ─── In-memory stubs ──────────────────────────────────────────────────────────


class InMemoryTemplateStore:
    """In-memory template store seeded with built-in templates."""

    def __init__(self) -> None:
        self._store: dict[str, NotificationTemplate] = {t.id: t for t in _SEED_TEMPLATES}

    async def get(self, template_id: str) -> NotificationTemplate | None:
        return self._store.get(template_id)

    async def list_templates(
        self,
        category: NotificationCategory | None = None,
        channel: Channel | None = None,
    ) -> list[NotificationTemplate]:
        results = list(self._store.values())
        if category is not None:
            results = [t for t in results if t.category == category]
        if channel is not None:
            results = [t for t in results if t.channel == channel]
        return results

    async def save(self, template: NotificationTemplate) -> None:
        self._store[template.id] = template


class InMemoryPreferenceStore:
    """In-memory preference store keyed by (entity_id, channel, category)."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, Channel, NotificationCategory], NotificationPreference] = {}

    async def get(
        self,
        entity_id: str,
        channel: Channel,
        category: NotificationCategory,
    ) -> NotificationPreference | None:
        return self._store.get((entity_id, channel, category))

    async def save(self, pref: NotificationPreference) -> None:
        self._store[(pref.entity_id, pref.channel, pref.category)] = pref

    async def list_by_entity(self, entity_id: str) -> list[NotificationPreference]:
        return [p for (eid, _c, _cat), p in self._store.items() if eid == entity_id]


class InMemoryDeliveryStore:
    """In-memory delivery record store backed by a list."""

    def __init__(self) -> None:
        self._records: list[DeliveryRecord] = []

    async def save(self, record: DeliveryRecord) -> None:
        self._records = [r for r in self._records if r.id != record.id]
        self._records.append(record)

    async def get(self, record_id: str) -> DeliveryRecord | None:
        for record in self._records:
            if record.id == record_id:
                return record
        return None

    async def list_by_entity(self, entity_id: str) -> list[DeliveryRecord]:
        return [r for r in self._records if r.entity_id == entity_id]

    async def list_failed(self) -> list[DeliveryRecord]:
        return [r for r in self._records if r.status == DeliveryStatus.FAILED]


class InMemoryChannelAdapter:
    """Simulates channel dispatch — returns success/failure based on config."""

    def __init__(self, *, should_succeed: bool = True) -> None:
        self._should_succeed = should_succeed

    async def send(self, record: DeliveryRecord) -> bool:
        return self._should_succeed
