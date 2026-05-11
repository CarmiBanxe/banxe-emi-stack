"""ADR-033 Step 1: AlertRoutingPort + Alert dataclass + enums.

Hexagonal port for security/compliance alerts. Adapters route alerts to
external sinks (n8n+Telegram, Slack, in-memory test double).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertCategory(str, Enum):
    AUTH_BRUTE_FORCE = "AUTH_BRUTE_FORCE"
    CLIENT_SECRET_EXPOSURE = "CLIENT_SECRET_EXPOSURE"  # noqa: S105 — enum label, not a secret
    TOKEN_REPLAY = "TOKEN_REPLAY"  # noqa: S105 — enum label, not a token
    ADMIN_USER_DELETE = "ADMIN_USER_DELETE"
    ADMIN_PASSWORD_RESET = "ADMIN_PASSWORD_RESET"  # noqa: S105 — enum label, not a password
    SAFEGUARDING_SHORTFALL = "SAFEGUARDING_SHORTFALL"
    GENERIC = "GENERIC"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Alert:
    category: AlertCategory
    severity: AlertSeverity
    title: str
    body: str
    source: str = "banxe-emi-stack"
    timestamp: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    owner: str = "CTIO"


class AlertRoutingPort(ABC):
    @abstractmethod
    async def send_alert(self, alert: Alert) -> bool: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
