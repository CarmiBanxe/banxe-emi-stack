"""Integration tests for ADR-030 Step 4 — 429 path emits AUTH_RATE_LIMIT_EXCEEDED.

These exercise api/routers/auth._check_rate_limit directly with a stubbed
rate limiter that forces the not-allowed branch, and a stubbed
get_rate_limit_audit_emitter that captures the AuditEvent that would have
been pushed to BufferedAuditPort. No real Redis, no real SQLite, no real
HTTP server — pure function-level integration of the router 429 path with
the audit emitter contract.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import HTTPException
import pytest

from api.routers import auth as auth_router
from services.auth.rate_limit_audit_emitter import (
    EVENT_AUTH_RATE_LIMIT_EXCEEDED,
    RateLimitAuditEmitter,
)


class _FakeRateLimiter:
    """Forces not-allowed path on every check; tracks invocations."""

    def __init__(self, retry_after: int = 60) -> None:
        self._retry = retry_after
        self.checks: list[tuple[str, str]] = []

    def check_rate(self, client_id: str, endpoint: str):
        self.checks.append((client_id, endpoint))

        class _Result:
            allowed = False
            retry_after = self._retry  # noqa: B023

        return _Result()

    def record_attempt(self, *_a: Any, **_kw: Any) -> None:  # pragma: no cover
        pass


class _FakeAuditPort:
    def __init__(self) -> None:
        self.records: list[Any] = []

    def record(self, entry: Any) -> None:
        self.records.append(entry)


@pytest.fixture
def _wire_429_capture(monkeypatch: pytest.MonkeyPatch):
    """Wire a forced-block rate limiter + capturing audit port into the router."""
    fake_audit = _FakeAuditPort()
    emitter = RateLimitAuditEmitter(audit_port=fake_audit, clock=lambda: 1714000000.0)

    monkeypatch.setattr(auth_router, "_rate_limiter", _FakeRateLimiter())
    monkeypatch.setattr(auth_router, "get_rate_limit_audit_emitter", lambda: emitter)
    return fake_audit


def test_429_on_auth_login_emits_audit_event_with_ip_dimension(
    _wire_429_capture: _FakeAuditPort,
) -> None:
    with pytest.raises(HTTPException) as excinfo:
        auth_router._check_rate_limit(
            client_id="203.0.113.42",
            endpoint="/auth/login",
            client_ip="203.0.113.42",
        )
    assert excinfo.value.status_code == 429
    assert len(_wire_429_capture.records) == 1
    ev = _wire_429_capture.records[0]
    assert ev.event_type == EVENT_AUTH_RATE_LIMIT_EXCEEDED
    assert ev.entity_id == "/auth/login"
    assert ev.severity == "MAJOR"  # ADR-030 §matrix HIGH → AuditEvent MAJOR
    assert ev.payload["identity_dimension"] == "IP"
    assert ev.payload["identity_value"] == "203.0.113.42"
    assert ev.payload["client_ip"] == "203.0.113.42"


def test_429_on_sca_verify_emits_audit_event_with_challenge_id_dimension_critical_severity(
    _wire_429_capture: _FakeAuditPort,
) -> None:
    with pytest.raises(HTTPException) as excinfo:
        auth_router._check_rate_limit(
            client_id="ch-abc-123",
            endpoint="/auth/sca/verify",
            client_ip="198.51.100.7",
        )
    assert excinfo.value.status_code == 429
    assert len(_wire_429_capture.records) == 1
    ev = _wire_429_capture.records[0]
    assert ev.severity == "CRITICAL"  # ADR-030 §matrix CRITICAL → CRITICAL
    assert ev.payload["identity_dimension"] == "challenge_id"
    assert ev.payload["identity_value"] == "ch-abc-123"  # NOT hashed
    assert ev.payload["client_ip"] == "198.51.100.7"


def test_429_on_sca_initiate_emits_audit_event_with_customer_id_dimension_hashed(
    _wire_429_capture: _FakeAuditPort,
) -> None:
    raw_customer = "cust-banxe-77777"
    expected_hash = hashlib.sha256(raw_customer.encode("utf-8")).hexdigest()[:16]

    with pytest.raises(HTTPException) as excinfo:
        auth_router._check_rate_limit(
            client_id=raw_customer,
            endpoint="/auth/sca/initiate",
            client_ip="198.51.100.42",
        )
    assert excinfo.value.status_code == 429
    ev = _wire_429_capture.records[0]
    assert ev.severity == "MAJOR"
    assert ev.payload["identity_dimension"] == "customer_id"
    # PII safety — raw customer_id MUST be sha256[:16]-hashed
    assert ev.payload["identity_value"] == expected_hash
    assert ev.payload["identity_value"] != raw_customer


def test_audit_emitter_failure_does_not_break_429_response_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken emitter (raises on emit) must not block the 429 path."""

    class _BrokenEmitter:
        def emit_rate_limit_exceeded(self, **_kw: Any) -> None:
            raise RuntimeError("audit-sink offline")

    monkeypatch.setattr(auth_router, "_rate_limiter", _FakeRateLimiter())
    monkeypatch.setattr(
        auth_router,
        "get_rate_limit_audit_emitter",
        lambda: _BrokenEmitter(),
    )

    with pytest.raises(HTTPException) as excinfo:
        auth_router._check_rate_limit(
            client_id="1.2.3.4",
            endpoint="/auth/login",
            client_ip="1.2.3.4",
        )
    # 429 still raised even though emitter blew up — the suppress around
    # the emitter call in _emit_rate_limit_audit keeps the 429 path safe.
    assert excinfo.value.status_code == 429
