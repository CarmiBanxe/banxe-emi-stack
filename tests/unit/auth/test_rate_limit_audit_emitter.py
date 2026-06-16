"""Unit tests for RateLimitAuditEmitter (ADR-030 Step 4).

Deterministic FakeBufferedAuditPort captures every entry passed to record().
No real SQLite, no real ClickHouse, no network. Injected clock for
reproducible occurred_at assertions.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any

import pytest

from services.auth.rate_limit_audit_emitter import (
    ENDPOINT_AUDIT_META,
    EVENT_AUTH_RATE_LIMIT_EXCEEDED,
    RateLimitAuditEmitter,
    hash_identity_if_pii,
    lookup_endpoint_meta,
)
from services.auth.rate_limiter_factory import get_rate_limit_audit_emitter


class FakeBufferedAuditPort:
    """In-memory test double matching BufferedAuditPort.record(entry)."""

    def __init__(self) -> None:
        self.records: list[Any] = []

    def record(self, entry: Any) -> None:
        self.records.append(entry)


def _emitter(start_time: float = 1714000000.0):
    clock = [start_time]
    fake = FakeBufferedAuditPort()
    return (
        RateLimitAuditEmitter(audit_port=fake, clock=lambda: clock[0]),
        fake,
        clock,
    )


def test_emit_builds_canonical_event_with_AUTH_RATE_LIMIT_EXCEEDED_type() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit_rate_limit_exceeded(
        endpoint="/auth/login",
        identity_dimension="IP",
        identity_value="203.0.113.42",
        client_ip="203.0.113.42",
        limit="retry_after=60s",
        severity="MAJOR",
    )
    assert len(fake.records) == 1
    ev = fake.records[0]
    assert ev.event_type == EVENT_AUTH_RATE_LIMIT_EXCEEDED
    assert ev.entity_id == "/auth/login"
    assert ev.actor == "RateLimiter"
    assert ev.severity == "MAJOR"
    assert ev.payload["identity_dimension"] == "IP"
    assert ev.payload["identity_value"] == "203.0.113.42"
    assert ev.payload["client_ip"] == "203.0.113.42"
    assert ev.payload["limit"] == "retry_after=60s"
    assert ev.payload["severity_label"] == "MAJOR"


def test_emit_records_to_audit_port_each_call_appends() -> None:
    emitter, fake, _clock = _emitter()
    for _ in range(3):
        emitter.emit_rate_limit_exceeded(
            endpoint="/auth/sca/verify",
            identity_dimension="challenge_id",
            identity_value="ch-1",
            client_ip="203.0.113.10",
            limit="x",
            severity="CRITICAL",
        )
    assert len(fake.records) == 3
    assert all(r.event_type == EVENT_AUTH_RATE_LIMIT_EXCEEDED for r in fake.records)


def test_emit_uses_injected_clock_for_occurred_at_not_realtime() -> None:
    fixed_ts = 1714000000.0
    emitter, fake, _clock = _emitter(start_time=fixed_ts)
    emitter.emit_rate_limit_exceeded(
        endpoint="/auth/login",
        identity_dimension="IP",
        identity_value="1.2.3.4",
        client_ip="1.2.3.4",
        limit="x",
        severity="MAJOR",
    )
    assert fake.records[0].occurred_at == datetime.fromtimestamp(fixed_ts, tz=UTC)


def test_emit_hashes_account_id_identity_value() -> None:
    emitter, fake, _clock = _emitter()
    raw = "user-12345@banxe.io"
    emitter.emit_rate_limit_exceeded(
        endpoint="/auth/login",
        identity_dimension="account_id",
        identity_value=raw,
        client_ip="1.2.3.4",
        limit="x",
        severity="MAJOR",
    )
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    assert fake.records[0].payload["identity_value"] == expected
    assert fake.records[0].payload["identity_value"] != raw


def test_emit_hashes_customer_id_identity_value() -> None:
    emitter, fake, _clock = _emitter()
    raw = "cust-banxe-77777"
    emitter.emit_rate_limit_exceeded(
        endpoint="/auth/sca/initiate",
        identity_dimension="customer_id",
        identity_value=raw,
        client_ip="1.2.3.4",
        limit="x",
        severity="MAJOR",
    )
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    assert fake.records[0].payload["identity_value"] == expected


def test_emit_does_not_hash_ip_identity_value() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit_rate_limit_exceeded(
        endpoint="/auth/login",
        identity_dimension="IP",
        identity_value="198.51.100.7",
        client_ip="198.51.100.7",
        limit="x",
        severity="MAJOR",
    )
    assert fake.records[0].payload["identity_value"] == "198.51.100.7"


def test_emit_does_not_hash_challenge_id_identity_value() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit_rate_limit_exceeded(
        endpoint="/auth/sca/verify",
        identity_dimension="challenge_id",
        identity_value="ch-abc-123",
        client_ip="1.2.3.4",
        limit="x",
        severity="CRITICAL",
    )
    assert fake.records[0].payload["identity_value"] == "ch-abc-123"


def test_emit_does_not_hash_refresh_token_jti_identity_value() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit_rate_limit_exceeded(
        endpoint="/auth/token/refresh",
        identity_dimension="refresh_token_jti",
        identity_value="jti-xyz-789",
        client_ip="1.2.3.4",
        limit="x",
        severity="WARNING",
    )
    assert fake.records[0].payload["identity_value"] == "jti-xyz-789"


def test_emit_severity_propagates_to_event_severity_field() -> None:
    # ADR-030 §matrix severity HIGH/MEDIUM/CRITICAL/LOW translates to
    # AuditEvent vocabulary MAJOR/WARNING/CRITICAL/INFO at the caller's end.
    emitter, fake, _clock = _emitter()
    for sev in ("INFO", "WARNING", "MAJOR", "CRITICAL"):
        emitter.emit_rate_limit_exceeded(
            endpoint="/auth/login",
            identity_dimension="IP",
            identity_value="1.2.3.4",
            client_ip="1.2.3.4",
            limit="x",
            severity=sev,
        )
    assert [r.severity for r in fake.records] == [
        "INFO",
        "WARNING",
        "MAJOR",
        "CRITICAL",
    ]


def test_lookup_endpoint_meta_returns_adr030_matrix_dimension_and_severity() -> None:
    # Spot-check a few rows of ADR-030 §Endpoint × Limit Matrix
    assert lookup_endpoint_meta("/auth/login") == ("IP", "MAJOR")
    assert lookup_endpoint_meta("/auth/sca/verify") == ("challenge_id", "CRITICAL")
    assert lookup_endpoint_meta("/auth/sca/resend") == ("challenge_id", "WARNING")
    assert lookup_endpoint_meta("/auth/token/refresh") == (
        "refresh_token_jti",
        "WARNING",
    )
    assert lookup_endpoint_meta("/auth/sca/methods") == ("IP", "INFO")
    assert lookup_endpoint_meta("/nonexistent") is None
    # Matrix has exactly 7 entries (matches ADR-030 matrix line count)
    assert len(ENDPOINT_AUDIT_META) == 7


def test_hash_identity_if_pii_helper_directly() -> None:
    assert hash_identity_if_pii("IP", "1.2.3.4") == "1.2.3.4"
    raw = "cust-1"
    assert (
        hash_identity_if_pii("customer_id", raw) == (hashlib.sha256(raw.encode()).hexdigest()[:16])
    )
    assert (
        hash_identity_if_pii("account_id", raw) == (hashlib.sha256(raw.encode()).hexdigest()[:16])
    )
    # 16 hex chars
    assert len(hash_identity_if_pii("customer_id", raw)) == 16


def test_factory_get_rate_limit_audit_emitter_returns_singleton(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """@lru_cache singleton; two calls return the same instance, isolated
    to a tmp SQLite path so production /tmp/banxe-audit-buffer.db is untouched."""
    monkeypatch.setenv("AUDIT_BUFFER_PATH", str(tmp_path / "audit.db"))
    from api.deps import get_buffered_audit_port

    get_rate_limit_audit_emitter.cache_clear()
    get_buffered_audit_port.cache_clear()
    try:
        a = get_rate_limit_audit_emitter()
        b = get_rate_limit_audit_emitter()
        assert a is b
        assert isinstance(a, RateLimitAuditEmitter)
        # The emitter holds the SHARED audit port singleton
        assert a._audit is get_buffered_audit_port()  # type: ignore[attr-defined]
    finally:
        get_rate_limit_audit_emitter.cache_clear()
        get_buffered_audit_port.cache_clear()
