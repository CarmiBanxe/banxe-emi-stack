"""
rate_limit_audit_emitter.py — AUTH_RATE_LIMIT_EXCEEDED audit emitter
(ADR-030 §Implementation-Plan item 4).

Bridges the rate-limit 429 path to the ADR-027 BufferedAuditPort ring buffer.
Pure event-builder + delegator. The buffer port already swallows internal
errors per ADR-027, so no try/except is layered here.

Event shape (per ADR-030 §Endpoint × Limit Matrix):
  event_type:  "AUTH_RATE_LIMIT_EXCEEDED"
  entity_id:   endpoint path (e.g. "/auth/login")
  actor:       "RateLimiter"
  severity:    AuditEvent vocabulary INFO | WARNING | MAJOR | CRITICAL
               (ADR-030 §matrix HIGH/MEDIUM/CRITICAL/LOW mapped to
                MAJOR/WARNING/CRITICAL/INFO — see _SEVERITY_MAP below)
  payload:     endpoint, identity_dimension, identity_value
               (account_id / customer_id are hashed to sha256[:16] for PII
                safety; IP / challenge_id / refresh_token_jti / client_id
                are stored plain), client_ip, limit, severity_label
  occurred_at: datetime.fromtimestamp(injected_clock(), tz=UTC)

Severity-mapping deviation note: the original Step 4 prompt suggested
"CRITICAL → ERROR, HIGH/MEDIUM/LOW → WARNING". The actual AuditEvent
vocabulary in src/safeguarding/audit_trail.py is {INFO, WARNING, MAJOR,
CRITICAL} — no ERROR. This module follows the repo vocabulary verbatim
(prompt: "verify mapping from existing audit_trail.py before coding").
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import hashlib
import time
from typing import TYPE_CHECKING

from src.safeguarding.audit_trail import AuditEvent

if TYPE_CHECKING:
    from src.safeguarding.buffered_audit_port import BufferedAuditPort


EVENT_AUTH_RATE_LIMIT_EXCEEDED = "AUTH_RATE_LIMIT_EXCEEDED"
_ACTOR = "RateLimiter"

# Identity dimensions whose value is treated as PII and must be hashed
# before being persisted in the audit trail.
_HASHED_DIMENSIONS: frozenset[str] = frozenset({"account_id", "customer_id"})

# ADR-030 §Endpoint × Limit Matrix → (identity_dimension, AuditEvent.severity)
# severity values translate ADR-030 HIGH→MAJOR, MEDIUM→WARNING,
# CRITICAL→CRITICAL, LOW→INFO (per audit_trail.AuditEvent docstring).
ENDPOINT_AUDIT_META: dict[str, tuple[str, str]] = {
    "/auth/login": ("IP", "MAJOR"),
    "/auth/token/refresh": ("refresh_token_jti", "WARNING"),
    "/auth/sca/initiate": ("customer_id", "MAJOR"),
    "/auth/sca/verify": ("challenge_id", "CRITICAL"),
    "/auth/sca/resend": ("challenge_id", "WARNING"),
    "/auth/sca/methods": ("IP", "INFO"),
    "/auth/token": ("client_id", "INFO"),
}


def lookup_endpoint_meta(endpoint: str) -> tuple[str, str] | None:
    """Return (identity_dimension, severity) for the given endpoint, or None
    if the endpoint is not in the ADR-030 matrix."""
    return ENDPOINT_AUDIT_META.get(endpoint)


def hash_identity_if_pii(dimension: str, value: str) -> str:
    """sha256[:16] hex for PII dimensions (account_id, customer_id);
    pass-through for non-PII dimensions (IP, challenge_id, refresh_token_jti,
    client_id)."""
    if dimension in _HASHED_DIMENSIONS:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return value


class RateLimitAuditEmitter:
    """Build and forward AUTH_RATE_LIMIT_EXCEEDED events to BufferedAuditPort."""

    def __init__(
        self,
        audit_port: BufferedAuditPort,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._audit = audit_port
        self._clock = clock

    def emit_rate_limit_exceeded(
        self,
        endpoint: str,
        identity_dimension: str,
        identity_value: str,
        client_ip: str,
        limit: str,
        severity: str,
    ) -> None:
        event = AuditEvent(
            event_type=EVENT_AUTH_RATE_LIMIT_EXCEEDED,
            entity_id=endpoint,
            actor=_ACTOR,
            payload={
                "endpoint": endpoint,
                "identity_dimension": identity_dimension,
                "identity_value": hash_identity_if_pii(identity_dimension, identity_value),
                "client_ip": client_ip,
                "limit": limit,
                "severity_label": severity,
            },
            severity=severity,
            occurred_at=datetime.fromtimestamp(self._clock(), tz=UTC),
        )
        self._audit.record(event)
