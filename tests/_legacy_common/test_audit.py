"""Tests for services/_legacy_common/audit.py (BaseAuditRecord + AuditTrail)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError
import pytest

from services._legacy_common.audit import AuditTrail, BaseAuditRecord


def _record(**kwargs: object) -> BaseAuditRecord:
    defaults: dict[str, object] = {
        "record_id": "rec-001",
        "customer_id": "cust-abc",
        "event_type": "CREATED",
        "occurred_at": datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC),
        "status_from": None,
        "status_to": "PENDING",
        "metadata": None,
    }
    defaults.update(kwargs)
    return BaseAuditRecord(**defaults)  # type: ignore[arg-type]


# ── BaseAuditRecord ────────────────────────────────────────────────────────────


def test_base_audit_record_stores_all_fields() -> None:
    rec = _record()
    assert rec.record_id == "rec-001"
    assert rec.customer_id == "cust-abc"
    assert rec.event_type == "CREATED"
    assert rec.status_from is None
    assert rec.status_to == "PENDING"
    assert rec.metadata is None


def test_base_audit_record_with_status_from() -> None:
    rec = _record(status_from="PENDING", status_to="ACTIVE", event_type="ACTIVATED")
    assert rec.status_from == "PENDING"
    assert rec.status_to == "ACTIVE"


def test_base_audit_record_with_metadata() -> None:
    meta = {"note": "test", "score": 42}
    rec = _record(metadata=meta)
    assert rec.metadata == {"note": "test", "score": 42}


def test_base_audit_record_is_frozen() -> None:
    rec = _record()
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        rec.event_type = "MUTATED"  # type: ignore[misc]


def test_base_audit_record_equality_by_value() -> None:
    rec1 = _record()
    rec2 = _record()
    assert rec1 == rec2


def test_base_audit_record_inequality_on_event_type() -> None:
    rec1 = _record(event_type="CREATED")
    rec2 = _record(event_type="UPDATED")
    assert rec1 != rec2


def test_base_audit_record_metadata_default_is_none() -> None:
    rec = _record()
    assert rec.metadata is None


def test_base_audit_record_accepts_nested_metadata() -> None:
    rec = _record(metadata={"flags": {"pep": True, "hv": False}})
    assert rec.metadata is not None
    assert rec.metadata["flags"]["pep"] is True


# ── AuditTrail ────────────────────────────────────────────────────────────────


def test_audit_trail_starts_empty() -> None:
    trail = AuditTrail()
    assert trail.records() == []


def test_audit_trail_add_single_record() -> None:
    trail = AuditTrail()
    rec = _record()
    trail.add(rec)
    assert len(trail.records()) == 1
    assert trail.records()[0] == rec


def test_audit_trail_add_multiple_records_preserves_order() -> None:
    trail = AuditTrail()
    r1 = _record(event_type="CREATED", status_to="PENDING")
    r2 = _record(event_type="SUBMITTED", status_from="PENDING", status_to="REVIEW")
    r3 = _record(event_type="APPROVED", status_from="REVIEW", status_to="APPROVED")
    trail.add(r1)
    trail.add(r2)
    trail.add(r3)
    result = trail.records()
    assert result[0].event_type == "CREATED"
    assert result[1].event_type == "SUBMITTED"
    assert result[2].event_type == "APPROVED"


def test_audit_trail_records_returns_copy_not_reference() -> None:
    trail = AuditTrail()
    trail.add(_record())
    copy1 = trail.records()
    copy1.clear()
    assert len(trail.records()) == 1


def test_audit_trail_external_mutation_does_not_affect_trail() -> None:
    trail = AuditTrail()
    trail.add(_record(event_type="CREATED"))
    snapshot = trail.records()
    extra = _record(event_type="INJECTED")
    snapshot.append(extra)
    assert len(trail.records()) == 1


def test_audit_trail_append_only_no_remove() -> None:
    trail = AuditTrail()
    trail.add(_record())
    assert not hasattr(trail, "remove")
    assert not hasattr(trail, "pop")
    assert not hasattr(trail, "clear")
