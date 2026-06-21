"""services/auth/login_history.py — Advisory login-history audit surface (MIG genuine-gap #2).

Descriptive, config-as-data **login-history audit** surface (semantic port for the legacy
`login-history.service.ts`). Advisory / sandbox / read-only: it records descriptive login-audit entries
(event, outcome, masked IP, descriptive user ref, source). It does NOT perform live authentication, does
NOT call AuthApplicationService / SCA (it is an audit sibling, not a duplicate of the auth flow), calls
NO Midaz LedgerPort, touches NO KYC/KYB/AML, mutates NO ledger/state.

PII discipline: IP is **masked** (last octet redacted) before storage; no raw PII retained.
Time discipline: ``timestamp`` is **passed in by the caller** — this module never calls a wall-clock
(no ``datetime.now`` / ``Date.now``), keeping it deterministic and replay-safe. Fail-closed (unknown
event_id -> None). No monetary numerics, no float (I-01 trivially).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import secrets

SANDBOX_SOURCE = "sandbox-mock"


class LoginOutcome(str, Enum):
    """Descriptive outcome of a login attempt (audit metadata)."""

    SUCCESS = "success"
    FAILURE = "failure"
    MFA_REQUIRED = "mfa_required"
    LOCKED = "locked"
    EXPIRED = "expired"


def mask_ip(ip: str) -> str:
    """Mask an IP for PII-safe audit storage (no raw IP retained)."""
    if ":" in ip:  # IPv6 — keep first hextet group only
        head = ip.split(":", 1)[0]
        return f"{head}:****"
    parts = ip.split(".")
    if len(parts) == 4:  # IPv4 — redact last octet
        return f"{parts[0]}.{parts[1]}.{parts[2]}.x"
    return "****"  # unknown shape -> fully masked (fail-closed)


@dataclass(frozen=True)
class LoginHistoryRecord:
    """Descriptive login-audit record (PII-masked; timestamp supplied by caller)."""

    event_id: str
    login_event: str  # e.g. "password_login", "sca_step", "token_refresh"
    timestamp: str  # ISO-8601 supplied by caller (never wall-clock here)
    masked_ip: str  # PII-masked (mask_ip applied)
    user_ref: str  # descriptive/opaque reference (not raw PII)
    outcome: LoginOutcome
    source: str = SANDBOX_SOURCE


class LoginHistoryPort(ABC):
    """Read-only advisory login-history audit contract (descriptive; fail-closed)."""

    @abstractmethod
    def record(
        self,
        *,
        login_event: str,
        timestamp: str,
        ip: str,
        user_ref: str,
        outcome: LoginOutcome,
    ) -> LoginHistoryRecord:
        """Record a descriptive login-audit entry (IP masked; timestamp supplied; no live auth)."""

    @abstractmethod
    def list_history(self) -> list[LoginHistoryRecord]: ...

    @abstractmethod
    def get_event(self, event_id: str) -> LoginHistoryRecord | None:
        """Return the audit record for event_id, or None if unknown (fail-closed)."""


class SandboxLoginHistoryProvider(LoginHistoryPort):
    """Sandbox config-as-data provider (mock-safe; no live auth, no Midaz, no KYC; PII-masked)."""

    def __init__(self) -> None:
        self._by_id: dict[str, LoginHistoryRecord] = {}

    def record(
        self,
        *,
        login_event: str,
        timestamp: str,
        ip: str,
        user_ref: str,
        outcome: LoginOutcome,
    ) -> LoginHistoryRecord:
        rec = LoginHistoryRecord(
            event_id=f"LH-{secrets.token_hex(6)}",
            login_event=login_event,
            timestamp=timestamp,  # caller-supplied; no wall-clock here
            masked_ip=mask_ip(ip),  # PII-masked before storage
            user_ref=user_ref,
            outcome=outcome,
            source=SANDBOX_SOURCE,
        )
        self._by_id[rec.event_id] = rec
        return rec

    def list_history(self) -> list[LoginHistoryRecord]:
        return list(self._by_id.values())

    def get_event(self, event_id: str) -> LoginHistoryRecord | None:
        return self._by_id.get(event_id)  # fail-closed
