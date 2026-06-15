"""
test_rotation_audit_emitter.py — RotationAuditEmitter tests (ADR-032 Step 4).

Verifies that ROTATION_DUE / ROTATION_COMPLETED events are built per the
ADR-032 §matrix shape and forwarded to BufferedAuditPort.record() unchanged.

Uses a FakeBufferedAuditPort that captures the entry list. No real SQLite,
no real ClickHouse, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from src.safeguarding.audit_trail import AuditEvent

from services.secrets.factory import get_rotation_audit_emitter
from services.secrets.rotation_audit_emitter import (
    EVENT_ROTATION_COMPLETED,
    EVENT_ROTATION_DUE,
    RotationAuditEmitter,
)


class FakeBufferedAuditPort:
    """In-memory test double: captures every entry passed to record()."""

    def __init__(self) -> None:
        self.records: list[Any] = []

    def record(self, entry: Any) -> None:
        self.records.append(entry)


def _make_emitter(start_time: float = 1714000000.0):
    clock = [start_time]
    fake = FakeBufferedAuditPort()
    emitter = RotationAuditEmitter(audit_port=fake, clock=lambda: clock[0])
    return emitter, fake, clock


def test_emit_rotation_due_builds_canonical_event_with_payload_fields() -> None:
    emitter, fake, _clock = _make_emitter()
    emitter.emit_rotation_due(
        secret_type="KC_CLIENT_SECRET_BANXE_COMPLIANCE_API",
        owner="CTIO",
        previous_rotation_date="2026-02-11",
        next_due_date="2026-05-11",
        cadence_days=90,
    )
    assert len(fake.records) == 1
    ev: AuditEvent = fake.records[0]
    assert ev.event_type == EVENT_ROTATION_DUE
    assert ev.entity_id == "KC_CLIENT_SECRET_BANXE_COMPLIANCE_API"
    assert ev.actor == "SecretRotation"
    assert ev.severity == "WARNING"
    assert ev.payload == {
        "secret_type": "KC_CLIENT_SECRET_BANXE_COMPLIANCE_API",
        "owner": "CTIO",
        "previous_rotation_date": "2026-02-11",
        "next_due_date": "2026-05-11",
        "cadence_days": 90,
    }


def test_emit_rotation_completed_builds_canonical_event_with_approved_by() -> None:
    emitter, fake, _clock = _make_emitter()
    emitter.emit_rotation_completed(
        secret_type="GITHUB_PAT_RELEASE_BOT",
        owner="CTIO",
        approved_by="moriel.carmi",
        previous_rotation_date="2026-04-11",
        completed_at="2026-05-11T08:00:00+00:00",
        cadence_days=30,
    )
    assert len(fake.records) == 1
    ev: AuditEvent = fake.records[0]
    assert ev.event_type == EVENT_ROTATION_COMPLETED
    assert ev.entity_id == "GITHUB_PAT_RELEASE_BOT"
    assert ev.actor == "SecretRotation"
    assert ev.severity == "INFO"
    assert ev.payload == {
        "secret_type": "GITHUB_PAT_RELEASE_BOT",
        "owner": "CTIO",
        "approved_by": "moriel.carmi",
        "previous_rotation_date": "2026-04-11",
        "completed_at": "2026-05-11T08:00:00+00:00",
        "cadence_days": 30,
    }


def test_emit_rotation_due_handles_none_previous_rotation_date() -> None:
    """First-time rotation has no prior date — must serialise as None."""
    emitter, fake, _clock = _make_emitter()
    emitter.emit_rotation_due(
        secret_type="NEW_SECRET",
        owner="CTIO",
        previous_rotation_date=None,
        next_due_date="2026-05-11",
        cadence_days=90,
    )
    assert fake.records[0].payload["previous_rotation_date"] is None


def test_emit_uses_injected_clock_for_occurred_at_not_realtime() -> None:
    """The event timestamp must reflect the injected clock, not wall time."""
    fixed_ts = 1714000000.0  # 2024-04-24T22:13:20+00:00
    emitter, fake, _clock = _make_emitter(start_time=fixed_ts)
    emitter.emit_rotation_due(
        secret_type="X",
        owner="O",
        previous_rotation_date=None,
        next_due_date="2026-05-11",
        cadence_days=30,
    )
    expected = datetime.fromtimestamp(fixed_ts, tz=UTC)
    assert fake.records[0].occurred_at == expected


def test_emit_rotation_due_and_completed_can_coexist_for_same_secret() -> None:
    """Lifecycle: DUE event then COMPLETED — both land in audit buffer in order."""
    emitter, fake, _clock = _make_emitter()
    emitter.emit_rotation_due(
        secret_type="K",
        owner="O",
        previous_rotation_date="2026-02-11",
        next_due_date="2026-05-11",
        cadence_days=90,
    )
    emitter.emit_rotation_completed(
        secret_type="K",
        owner="O",
        approved_by="ops",
        previous_rotation_date="2026-02-11",
        completed_at="2026-05-11T08:00:00+00:00",
        cadence_days=90,
    )
    assert [r.event_type for r in fake.records] == [
        EVENT_ROTATION_DUE,
        EVENT_ROTATION_COMPLETED,
    ]
    assert fake.records[0].severity == "WARNING"
    assert fake.records[1].severity == "INFO"


def test_emitter_constants_match_adr032_event_type_names() -> None:
    """Guard against accidental rename — these strings appear in ClickHouse
    queries and operator runbooks per ADR-032 §Implementation-Plan item 2."""
    assert EVENT_ROTATION_DUE == "ROTATION_DUE"
    assert EVENT_ROTATION_COMPLETED == "ROTATION_COMPLETED"


def test_factory_get_rotation_audit_emitter_returns_singleton(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """@lru_cache singleton: two calls return the same instance.

    Redirect the buffered-audit SQLite path to tmp_path so the test does not
    touch the production default /tmp/banxe-audit-buffer.db.
    """
    monkeypatch.setenv("AUDIT_BUFFER_PATH", str(tmp_path / "audit.db"))
    # Clear both caches: the secrets emitter factory and the underlying
    # api.deps.get_buffered_audit_port singleton it resolves through.
    get_rotation_audit_emitter.cache_clear()
    from api.deps import get_buffered_audit_port

    get_buffered_audit_port.cache_clear()
    try:
        a = get_rotation_audit_emitter()
        b = get_rotation_audit_emitter()
        assert a is b
        assert isinstance(a, RotationAuditEmitter)
    finally:
        get_rotation_audit_emitter.cache_clear()
        get_buffered_audit_port.cache_clear()
