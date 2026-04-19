"""
services/user_preferences/models.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

Domain models, protocols, and in-memory stubs for User Preferences & Settings.
Protocol DI: Port (Protocol) → InMemory stub (tests) → Real adapter (production)
GDPR: consent withdrawal and data erasure always HITL-gated (I-27).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol
import uuid

# ── Enums ────────────────────────────────────────────────────────────────────


class PreferenceCategory(str, Enum):
    NOTIFICATIONS = "NOTIFICATIONS"
    DISPLAY = "DISPLAY"
    PRIVACY = "PRIVACY"
    SECURITY = "SECURITY"
    ACCESSIBILITY = "ACCESSIBILITY"


class NotificationChannel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"
    TELEGRAM = "TELEGRAM"
    WEBHOOK = "WEBHOOK"


class Language(str, Enum):
    EN = "EN"
    FR = "FR"
    RU = "RU"
    DE = "DE"
    ES = "ES"
    AR = "AR"
    ZH = "ZH"


class Theme(str, Enum):
    LIGHT = "LIGHT"
    DARK = "DARK"
    HIGH_CONTRAST = "HIGH_CONTRAST"
    SYSTEM = "SYSTEM"


class ConsentType(str, Enum):
    MARKETING = "MARKETING"
    ANALYTICS = "ANALYTICS"
    ESSENTIAL = "ESSENTIAL"
    THIRD_PARTY = "THIRD_PARTY"
    DATA_SHARING = "DATA_SHARING"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserPreference:
    user_id: str
    category: PreferenceCategory
    key: str
    value: str
    updated_at: datetime
    updated_by: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class ConsentRecord:
    id: str
    user_id: str
    consent_type: ConsentType
    status: str  # "GRANTED" | "WITHDRAWN"
    granted_at: datetime
    ip_address: str
    channel: str
    withdrawn_at: datetime | None = None


@dataclass(frozen=True)
class NotificationPrefs:
    user_id: str
    channel: NotificationChannel
    enabled: bool
    frequency_cap_per_day: int
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None


@dataclass(frozen=True)
class LocaleSettings:
    user_id: str
    language: Language
    timezone: str
    date_format: str
    currency_format: str
    number_format: str


@dataclass(frozen=True)
class DataExportRequest:
    id: str
    user_id: str
    status: str  # "PENDING" | "COMPLETED" | "FAILED"
    format: str
    requested_at: datetime
    export_hash: str | None = None
    completed_at: datetime | None = None


# ── Protocols ────────────────────────────────────────────────────────────────


class PreferencePort(Protocol):
    def get(self, user_id: str, category: PreferenceCategory, key: str) -> str | None: ...
    def set(self, user_id: str, category: PreferenceCategory, key: str, value: str) -> None: ...
    def list_user(self, user_id: str) -> list[UserPreference]: ...


class ConsentPort(Protocol):
    def save(self, record: ConsentRecord) -> None: ...
    def get_latest(self, user_id: str, consent_type: ConsentType) -> ConsentRecord | None: ...
    def list_user(self, user_id: str) -> list[ConsentRecord]: ...


class NotificationPort(Protocol):
    def get(self, user_id: str, channel: NotificationChannel) -> NotificationPrefs | None: ...
    def save(self, prefs: NotificationPrefs) -> None: ...
    def list_user(self, user_id: str) -> list[NotificationPrefs]: ...


class AuditPort(Protocol):
    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryPreferencePort:
    def __init__(self) -> None:
        self._store: dict[str, UserPreference] = {}
        self._seed()

    def _seed(self) -> None:
        now = datetime.now(UTC)
        seed_prefs = [
            UserPreference(
                user_id="USR-001",
                category=PreferenceCategory.DISPLAY,
                key="theme",
                value=Theme.DARK.value,
                updated_at=now,
                updated_by="system",
            ),
            UserPreference(
                user_id="USR-001",
                category=PreferenceCategory.NOTIFICATIONS,
                key="email_enabled",
                value="true",
                updated_at=now,
                updated_by="system",
            ),
            UserPreference(
                user_id="USR-001",
                category=PreferenceCategory.PRIVACY,
                key="analytics",
                value="false",
                updated_at=now,
                updated_by="system",
            ),
        ]
        for p in seed_prefs:
            self._store[f"{p.user_id}:{p.category.value}:{p.key}"] = p

    def get(self, user_id: str, category: PreferenceCategory, key: str) -> str | None:
        record = self._store.get(f"{user_id}:{category.value}:{key}")
        return record.value if record else None

    def set(self, user_id: str, category: PreferenceCategory, key: str, value: str) -> None:
        now = datetime.now(UTC)
        pref = UserPreference(
            user_id=user_id,
            category=category,
            key=key,
            value=value,
            updated_at=now,
            updated_by="system",
        )
        self._store[f"{user_id}:{category.value}:{key}"] = pref

    def list_user(self, user_id: str) -> list[UserPreference]:
        return [p for p in self._store.values() if p.user_id == user_id]


class InMemoryConsentPort:
    def __init__(self) -> None:
        self._records: list[ConsentRecord] = []

    def save(self, record: ConsentRecord) -> None:
        self._records.append(record)

    def get_latest(self, user_id: str, consent_type: ConsentType) -> ConsentRecord | None:
        matches = [
            r for r in self._records if r.user_id == user_id and r.consent_type == consent_type
        ]
        return matches[-1] if matches else None

    def list_user(self, user_id: str) -> list[ConsentRecord]:
        return [r for r in self._records if r.user_id == user_id]


class InMemoryNotificationPort:
    def __init__(self) -> None:
        self._store: dict[str, NotificationPrefs] = {}

    def get(self, user_id: str, channel: NotificationChannel) -> NotificationPrefs | None:
        return self._store.get(f"{user_id}:{channel.value}")

    def save(self, prefs: NotificationPrefs) -> None:
        self._store[f"{prefs.user_id}:{prefs.channel.value}"] = prefs

    def list_user(self, user_id: str) -> list[NotificationPrefs]:
        return [p for p in self._store.values() if p.user_id == user_id]


class InMemoryAuditPort:
    def __init__(self) -> None:
        self._log: list[dict] = []

    def log(self, action: str, resource_id: str, details: dict, outcome: str) -> None:
        self._log.append(
            {
                "action": action,
                "resource_id": resource_id,
                "details": details,
                "outcome": outcome,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def entries(self) -> list[dict]:
        return list(self._log)
