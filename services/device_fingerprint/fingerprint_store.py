"""
services/device_fingerprint/fingerprint_store.py
FingerprintStorePort Protocol + InMemoryFingerprintStore (IL-FRAUD-01).

Hexagonal port for device fingerprint persistence and session binding.
I-24: All stores are append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True)
class SessionBinding:
    """Immutable session-to-device binding (I-24)."""

    session_id: str
    device_id: str
    customer_id: str
    ip_address_hash: str  # Hashed IP — no raw PII (I-24)
    geo_country: str
    bound_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class FingerprintStorePort(Protocol):
    """Port for device fingerprint and session storage."""

    def save_session_binding(self, binding: SessionBinding) -> None: ...

    def get_session_bindings(self, customer_id: str) -> list[SessionBinding]: ...

    def get_recent_sessions(self, customer_id: str, limit: int = 10) -> list[SessionBinding]: ...


class InMemoryFingerprintStore:
    """In-memory stub implementing FingerprintStorePort for tests."""

    def __init__(self) -> None:
        self._bindings: list[SessionBinding] = []

    def save_session_binding(self, binding: SessionBinding) -> None:
        self._bindings.append(binding)

    def get_session_bindings(self, customer_id: str) -> list[SessionBinding]:
        return [b for b in self._bindings if b.customer_id == customer_id]

    def get_recent_sessions(self, customer_id: str, limit: int = 10) -> list[SessionBinding]:
        customer_bindings = [b for b in self._bindings if b.customer_id == customer_id]
        return customer_bindings[-limit:]

    @property
    def bindings(self) -> list[SessionBinding]:
        return list(self._bindings)
