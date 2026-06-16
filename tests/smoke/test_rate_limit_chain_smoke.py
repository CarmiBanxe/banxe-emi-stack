"""End-to-end smoke for the ADR-030 rate-limit chain (Step 5).

Exercises the full Port → DI → Adapter → Router → AuditEmitter →
BufferedAuditPort chain for the seven auth-surface endpoints from
ADR-030 §Endpoint × Limit Matrix:

  POST /auth/login           → identity_dimension=IP            severity=MAJOR
  POST /auth/token/refresh   → identity_dimension=jti           severity=WARNING
  POST /auth/sca/initiate    → identity_dimension=customer_id   severity=MAJOR  (hashed)
  POST /auth/sca/verify      → identity_dimension=challenge_id  severity=CRITICAL
  POST /auth/sca/resend      → identity_dimension=challenge_id  severity=WARNING
  GET  /auth/sca/methods/{id}→ identity_dimension=IP            severity=INFO
  POST /auth/token           → identity_dimension=client_id     severity=INFO

Implementation-deviation note (per Step 5 prompt instruction "assert actual
code thresholds, not ADR-030 §matrix values"):
  RedisRateLimiterAdapter uses a SINGLE global max_attempts threshold (env
  RATE_LIMIT_MAX_ATTEMPTS, default 10), not the ADR-030 §matrix per-endpoint
  values (5/min login, 30/min refresh, 10/min initiate, 5/attempt verify,
  3/min resend, 60/min methods, 60/min token). Closing this gap is a
  follow-up implementation step out of Step 5 scope. These smoke tests use
  small max_attempts (3–5) to trigger 429 quickly without per-endpoint
  threshold awareness; assertions are limited to the (dimension, severity)
  metadata that IS already per-endpoint correct via ENDPOINT_AUDIT_META.

No real Redis (in-memory dict in RedisRateLimiterAdapter). No real
SQLite (FakeBufferedAuditPort). No real network. No real time.sleep.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import HTTPException
import pytest

from api.routers import auth as auth_router
from services.auth.rate_limit_audit_emitter import (
    ENDPOINT_AUDIT_META,
    EVENT_AUTH_RATE_LIMIT_EXCEEDED,
    RateLimitAuditEmitter,
)
from services.auth.redis_rate_limiter import RedisRateLimiterAdapter

pytestmark = pytest.mark.smoke


class _FakeBufferedAuditPort:
    """In-memory BufferedAuditPort double — record(entry) appends."""

    def __init__(self) -> None:
        self.records: list[Any] = []

    def record(self, entry: Any) -> None:
        self.records.append(entry)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_attempts: int = 3,
) -> _FakeBufferedAuditPort:
    """Inject a fresh in-memory rate limiter + capturing audit emitter into
    api.routers.auth. Each test gets isolated state.
    """
    limiter = RedisRateLimiterAdapter(
        max_attempts=max_attempts,
        window_seconds=60,
        lockout_seconds=300,
    )
    fake_audit = _FakeBufferedAuditPort()
    emitter = RateLimitAuditEmitter(audit_port=fake_audit, clock=lambda: 1714000000.0)
    monkeypatch.setattr(auth_router, "_rate_limiter", limiter)
    monkeypatch.setattr(auth_router, "get_rate_limit_audit_emitter", lambda: emitter)
    return fake_audit


def _hammer_until_429(
    endpoint: str,
    client_id: str,
    *,
    client_ip: str | None = None,
    max_attempts: int = 3,
) -> int:
    """Call _check_rate_limit until it raises HTTP 429. Returns the call
    count at which 429 fired. Caps at max_attempts+5 to avoid infinite loops."""
    cap = max_attempts + 5
    for call_n in range(1, cap + 1):
        try:
            auth_router._check_rate_limit(
                client_id=client_id, endpoint=endpoint, client_ip=client_ip
            )
        except HTTPException as exc:
            assert exc.status_code == 429
            return call_n
    raise AssertionError(f"429 never fired within {cap} attempts on {endpoint}")


def test_smoke_auth_login_429_after_N_attempts_per_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = _wire(monkeypatch, max_attempts=3)
    fired_at = _hammer_until_429(
        "/auth/login", "203.0.113.42", client_ip="203.0.113.42", max_attempts=3
    )
    # With max_attempts=3 the 4th call should be the first 429.
    assert fired_at == 4
    assert len(audit.records) == 1
    assert audit.records[0].entity_id == "/auth/login"


def test_smoke_auth_login_429_emits_audit_event_with_ip_dimension_major_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = _wire(monkeypatch, max_attempts=2)
    _hammer_until_429("/auth/login", "203.0.113.5", client_ip="203.0.113.5", max_attempts=2)
    ev = audit.records[0]
    assert ev.event_type == EVENT_AUTH_RATE_LIMIT_EXCEEDED
    assert ev.severity == "MAJOR"  # ADR-030 HIGH → AuditEvent MAJOR
    assert ev.payload["identity_dimension"] == "IP"
    assert ev.payload["identity_value"] == "203.0.113.5"
    assert ev.payload["client_ip"] == "203.0.113.5"


def test_smoke_auth_refresh_429_per_jti_warning_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = _wire(monkeypatch, max_attempts=2)
    _hammer_until_429(
        "/auth/token/refresh",
        client_id="jti-prefix-xyz",
        client_ip="198.51.100.7",
        max_attempts=2,
    )
    ev = audit.records[0]
    assert ev.severity == "WARNING"  # ADR-030 MEDIUM → AuditEvent WARNING
    assert ev.payload["identity_dimension"] == "refresh_token_jti"
    assert ev.payload["identity_value"] == "jti-prefix-xyz"


def test_smoke_sca_initiate_429_per_customer_id_emits_hashed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = _wire(monkeypatch, max_attempts=2)
    raw_customer = "cust-banxe-77777"
    _hammer_until_429(
        "/auth/sca/initiate",
        client_id=raw_customer,
        client_ip="198.51.100.42",
        max_attempts=2,
    )
    ev = audit.records[0]
    assert ev.severity == "MAJOR"
    assert ev.payload["identity_dimension"] == "customer_id"
    # PII safety: customer_id is sha256[:16]-hashed in the audit payload
    expected = hashlib.sha256(raw_customer.encode("utf-8")).hexdigest()[:16]
    assert ev.payload["identity_value"] == expected
    assert ev.payload["identity_value"] != raw_customer


def test_smoke_sca_verify_429_per_challenge_id_critical_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PSD2 RTS Art.4 ≤5 boundary — the highest-severity rate-limit event."""
    audit = _wire(monkeypatch, max_attempts=2)
    _hammer_until_429(
        "/auth/sca/verify",
        client_id="ch-abc-123",
        client_ip="198.51.100.7",
        max_attempts=2,
    )
    ev = audit.records[0]
    assert ev.severity == "CRITICAL"
    assert ev.payload["identity_dimension"] == "challenge_id"
    assert ev.payload["identity_value"] == "ch-abc-123"  # not hashed


def test_smoke_sca_resend_429_per_challenge_id_warning_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = _wire(monkeypatch, max_attempts=2)
    _hammer_until_429(
        "/auth/sca/resend",
        client_id="ch-resend-1",
        client_ip="198.51.100.7",
        max_attempts=2,
    )
    ev = audit.records[0]
    assert ev.severity == "WARNING"
    assert ev.payload["identity_dimension"] == "challenge_id"


def test_smoke_sca_methods_429_per_ip_info_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = _wire(monkeypatch, max_attempts=2)
    _hammer_until_429(
        "/auth/sca/methods",
        client_id="203.0.113.10",
        client_ip="203.0.113.10",
        max_attempts=2,
    )
    ev = audit.records[0]
    assert ev.severity == "INFO"
    assert ev.payload["identity_dimension"] == "IP"


def test_smoke_429_audit_emitter_failure_does_not_break_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken audit emitter must NOT block the 429 response — the
    contextlib.suppress guard around _emit_rate_limit_audit keeps the
    delivery path safe."""

    class _BrokenEmitter:
        def emit_rate_limit_exceeded(self, **_kw: Any) -> None:
            raise RuntimeError("audit sink offline")

    limiter = RedisRateLimiterAdapter(max_attempts=1, window_seconds=60, lockout_seconds=300)
    monkeypatch.setattr(auth_router, "_rate_limiter", limiter)
    monkeypatch.setattr(auth_router, "get_rate_limit_audit_emitter", lambda: _BrokenEmitter())

    # First call allowed, second call 429 (broken emitter must not block 429)
    auth_router._check_rate_limit(client_id="1.2.3.4", endpoint="/auth/login", client_ip="1.2.3.4")
    with pytest.raises(HTTPException) as excinfo:
        auth_router._check_rate_limit(
            client_id="1.2.3.4", endpoint="/auth/login", client_ip="1.2.3.4"
        )
    assert excinfo.value.status_code == 429


def test_smoke_full_matrix_coverage_seven_endpoints_emit_distinct_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-pass loop over ENDPOINT_AUDIT_META: every matrix endpoint
    produces an AuditEvent whose (dimension, severity) matches the matrix."""
    audit = _wire(monkeypatch, max_attempts=1)
    # Distinct client_id per endpoint so the in-memory rate-limit windows
    # do not bleed across endpoints
    for endpoint, (dimension, severity) in ENDPOINT_AUDIT_META.items():
        client_id = f"client-{endpoint.replace('/', '-')}"
        # Burn 1st attempt (allowed), then the 2nd must 429.
        auth_router._check_rate_limit(
            client_id=client_id, endpoint=endpoint, client_ip="198.51.100.99"
        )
        with pytest.raises(HTTPException):
            auth_router._check_rate_limit(
                client_id=client_id, endpoint=endpoint, client_ip="198.51.100.99"
            )
    # One audit record per matrix entry
    assert len(audit.records) == len(ENDPOINT_AUDIT_META) == 7
    by_endpoint = {r.entity_id: r for r in audit.records}
    for endpoint, (dimension, severity) in ENDPOINT_AUDIT_META.items():
        rec = by_endpoint[endpoint]
        assert rec.severity == severity, (
            f"severity mismatch at {endpoint}: got {rec.severity!r}, expected {severity!r}"
        )
        assert rec.payload["identity_dimension"] == dimension


def test_smoke_within_limit_no_audit_event_emitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calls that stay below the threshold MUST NOT emit any audit event."""
    audit = _wire(monkeypatch, max_attempts=5)
    # 4 calls < max_attempts=5 → all allowed, zero audit emissions
    for _ in range(4):
        auth_router._check_rate_limit(
            client_id="203.0.113.99",
            endpoint="/auth/login",
            client_ip="203.0.113.99",
        )
    assert audit.records == []
