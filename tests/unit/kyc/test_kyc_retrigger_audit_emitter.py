"""Unit tests for KycRetriggerAuditEmitter (ADR-028 Step 4).

FakeBufferedAuditPort captures every entry passed to record(). No real
SQLite, no real ClickHouse, no network. Injected clock for reproducible
occurred_at assertions.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any

import pytest

from services.kyc.factory import get_kyc_retrigger_audit_emitter
from services.kyc.kyc_retrigger_audit_emitter import (
    EVENT_KYC_REVERIFICATION_TRIGGERED,
    TRIGGER_SEVERITY,
    KycRetriggerAuditEmitter,
)


class FakeBufferedAuditPort:
    def __init__(self) -> None:
        self.records: list[Any] = []

    def record(self, entry: Any) -> None:
        self.records.append(entry)


def _emitter(start_time: float = 1714000000.0):
    clock = [start_time]
    fake = FakeBufferedAuditPort()
    return (
        KycRetriggerAuditEmitter(audit_port=fake, clock=lambda: clock[0]),
        fake,
        clock,
    )


def test_emit_builds_canonical_event_with_KYC_REVERIFICATION_TRIGGERED_type() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit(
        customer_id="cust-001",
        trigger_type="role_changed",
        trigger_payload={"old_role": "BENEFICIARY", "new_role": "DIRECTOR"},
        requested_by="lifecycle-observer",
    )
    assert len(fake.records) == 1
    ev = fake.records[0]
    assert ev.event_type == EVENT_KYC_REVERIFICATION_TRIGGERED
    assert ev.actor == "lifecycle-observer"
    assert ev.payload["trigger_type"] == "role_changed"
    assert ev.payload["trigger_payload"] == {
        "old_role": "BENEFICIARY",
        "new_role": "DIRECTOR",
    }


def test_emit_uses_customer_id_as_entity_id_plain() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit(
        customer_id="cust-banxe-12345",
        trigger_type="role_changed",
        trigger_payload={},
    )
    assert fake.records[0].entity_id == "cust-banxe-12345"


def test_emit_hashes_customer_id_in_payload_for_pii() -> None:
    emitter, fake, _clock = _emitter()
    raw = "cust-banxe-12345"
    emitter.emit(
        customer_id=raw,
        trigger_type="role_changed",
        trigger_payload={},
    )
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    assert fake.records[0].payload["customer_id"] == expected
    assert fake.records[0].payload["customer_id"] != raw
    assert len(fake.records[0].payload["customer_id"]) == 16


def test_emit_severity_critical_for_sanctions_match() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit("cust", "sanctions_match", {})
    assert fake.records[0].severity == "CRITICAL"


def test_emit_severity_critical_for_role_changed() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit("cust", "role_changed", {})
    assert fake.records[0].severity == "CRITICAL"


def test_emit_severity_major_for_beneficial_owner_changed() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit("cust", "beneficial_owner_changed", {})
    assert fake.records[0].severity == "MAJOR"


def test_emit_severity_major_for_jurisdiction_changed() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit("cust", "jurisdiction_changed", {})
    assert fake.records[0].severity == "MAJOR"


def test_emit_severity_warning_for_periodic_review_due() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit("cust", "periodic_review_due", {})
    assert fake.records[0].severity == "WARNING"


def test_emit_unknown_trigger_type_raises_value_error() -> None:
    emitter, _fake, _clock = _emitter()
    with pytest.raises(ValueError, match="unknown trigger_type"):
        emitter.emit("cust", "totally_made_up_trigger", {})


def test_emit_uses_injected_clock_for_occurred_at_not_realtime() -> None:
    fixed = 1714000000.0
    emitter, fake, _clock = _emitter(start_time=fixed)
    emitter.emit("cust", "role_changed", {})
    assert fake.records[0].occurred_at == datetime.fromtimestamp(fixed, tz=UTC)


def test_emit_default_actor_is_lifecycle_fsm_when_requested_by_none() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit("cust", "role_changed", {})  # no requested_by
    assert fake.records[0].actor == "LifecycleFSM"


def test_trigger_severity_map_covers_all_5_canonical_trigger_types() -> None:
    assert set(TRIGGER_SEVERITY) == {
        "sanctions_match",
        "role_changed",
        "beneficial_owner_changed",
        "jurisdiction_changed",
        "periodic_review_due",
    }
    # Only severities from the AuditEvent vocabulary
    assert set(TRIGGER_SEVERITY.values()) <= {"INFO", "WARNING", "MAJOR", "CRITICAL"}


def test_factory_get_kyc_retrigger_audit_emitter_returns_singleton(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("AUDIT_BUFFER_PATH", str(tmp_path / "audit.db"))
    from api.deps import get_buffered_audit_port

    get_kyc_retrigger_audit_emitter.cache_clear()
    get_buffered_audit_port.cache_clear()
    try:
        a = get_kyc_retrigger_audit_emitter()
        b = get_kyc_retrigger_audit_emitter()
        assert a is b
        assert isinstance(a, KycRetriggerAuditEmitter)
        assert a._audit is get_buffered_audit_port()  # type: ignore[attr-defined]
    finally:
        get_kyc_retrigger_audit_emitter.cache_clear()
        get_buffered_audit_port.cache_clear()
