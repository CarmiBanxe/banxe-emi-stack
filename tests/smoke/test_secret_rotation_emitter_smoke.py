"""
test_secret_rotation_emitter_smoke.py — End-to-end smoke for ADR-032 Step 4
RotationAuditEmitter wired through ADR-027 BufferedAuditPort (Step 5).

Exercises the canonical event lifecycle (ROTATION_DUE → ROTATION_COMPLETED)
without real SQLite, real ClickHouse, or real network. Validates that the
factory singleton + emitter glue keep the contract stable end-to-end.
"""

from __future__ import annotations

from typing import Any

import pytest

from services.secrets.factory import get_rotation_audit_emitter
from services.secrets.rotation_audit_emitter import (
    EVENT_ROTATION_COMPLETED,
    EVENT_ROTATION_DUE,
    RotationAuditEmitter,
)

pytestmark = pytest.mark.smoke


class FakeBufferedAuditPort:
    """In-memory test double matching BufferedAuditPort.record(entry) shape."""

    def __init__(self) -> None:
        self.records: list[Any] = []

    def record(self, entry: Any) -> None:
        self.records.append(entry)


def _emitter():
    fake = FakeBufferedAuditPort()
    clock = [1714000000.0]
    return (
        RotationAuditEmitter(audit_port=fake, clock=lambda: clock[0]),
        fake,
        clock,
    )


def test_smoke_emit_rotation_due_lands_in_buffered_audit_port() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit_rotation_due(
        secret_type="KC_CLIENT_SECRET_BANXE_COMPLIANCE_API",
        owner="CTIO",
        previous_rotation_date="2026-02-11",
        next_due_date="2026-05-11",
        cadence_days=90,
    )
    assert len(fake.records) == 1
    ev = fake.records[0]
    assert ev.event_type == EVENT_ROTATION_DUE
    assert ev.severity == "WARNING"
    assert ev.entity_id == "KC_CLIENT_SECRET_BANXE_COMPLIANCE_API"
    assert ev.payload["cadence_days"] == 90


def test_smoke_emit_rotation_completed_lands_in_buffered_audit_port() -> None:
    emitter, fake, _clock = _emitter()
    emitter.emit_rotation_completed(
        secret_type="GITHUB_PAT_RELEASE_BOT",
        owner="CTIO",
        approved_by="moriel.carmi",
        previous_rotation_date="2026-04-11",
        completed_at="2026-05-11T08:00:00+00:00",
        cadence_days=30,
    )
    assert len(fake.records) == 1
    ev = fake.records[0]
    assert ev.event_type == EVENT_ROTATION_COMPLETED
    assert ev.severity == "INFO"
    assert ev.entity_id == "GITHUB_PAT_RELEASE_BOT"
    assert ev.payload["approved_by"] == "moriel.carmi"


def test_smoke_emit_full_cycle_due_then_completed_for_same_secret_type() -> None:
    emitter, fake, _clock = _emitter()
    secret = "SUMSUB_WEBHOOK_SECRET"
    emitter.emit_rotation_due(
        secret_type=secret,
        owner="CTIO",
        previous_rotation_date="2025-11-12",
        next_due_date="2026-05-11",
        cadence_days=180,
    )
    emitter.emit_rotation_completed(
        secret_type=secret,
        owner="CTIO",
        approved_by="ops",
        previous_rotation_date="2025-11-12",
        completed_at="2026-05-11T08:00:00+00:00",
        cadence_days=180,
    )
    assert [r.event_type for r in fake.records] == [
        EVENT_ROTATION_DUE,
        EVENT_ROTATION_COMPLETED,
    ]
    # Both events share entity_id == secret_type for ClickHouse partitioning by entity.
    assert all(r.entity_id == secret for r in fake.records)


def test_smoke_factory_emitter_uses_shared_audit_port_singleton(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Two factory invocations resolve to the SAME emitter (lru_cache) and that
    emitter holds the shared BufferedAuditPort singleton from api.deps."""
    monkeypatch.setenv("AUDIT_BUFFER_PATH", str(tmp_path / "audit.db"))
    from api.deps import get_buffered_audit_port

    get_rotation_audit_emitter.cache_clear()
    get_buffered_audit_port.cache_clear()
    try:
        a = get_rotation_audit_emitter()
        b = get_rotation_audit_emitter()
        assert a is b
        # Underlying audit_port is the api.deps singleton
        assert a._audit is get_buffered_audit_port()  # type: ignore[attr-defined]
    finally:
        get_rotation_audit_emitter.cache_clear()
        get_buffered_audit_port.cache_clear()
