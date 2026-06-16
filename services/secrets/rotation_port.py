"""SecretRotationPort — abstract secret rotation interface (ADR-032, G-SEC-01).

Defines the port for managed secret rotation. Concrete adapters
(EnvSecretRotator) implement rotation for .env-based secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RotationResult:
    """Result of a secret rotation operation."""

    success: bool
    secret_id: str
    rotated_at: datetime
    next_due: datetime
    error: str | None = None


@dataclass(frozen=True)
class RotationStatus:
    """Current rotation status of a secret."""

    secret_id: str
    last_rotated: datetime | None
    next_due: datetime | None
    is_overdue: bool
    days_until_due: int


@dataclass(frozen=True)
class SecretMetadata:
    """Metadata for a managed secret."""

    secret_id: str
    managed: bool
    last_rotated: datetime | None
    rotation_interval_days: int


class SecretRotationPort(Protocol):
    """Abstract port for secret rotation operations (ADR-032)."""

    def rotate(self, secret_id: str) -> RotationResult: ...

    def get_rotation_status(self, secret_id: str) -> RotationStatus: ...

    def list_secrets(self) -> list[SecretMetadata]: ...

    def check_overdue(self) -> list[SecretMetadata]: ...
