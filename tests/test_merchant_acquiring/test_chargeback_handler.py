"""
tests/test_merchant_acquiring/test_chargeback_handler.py
IL-MAG-01 | Phase 20 — Chargeback handler service tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.merchant_acquiring.chargeback_handler import ChargebackHandler
from services.merchant_acquiring.models import (
    DisputeStatus,
    InMemoryDisputeStore,
    InMemoryMAAudit,
)


def _make_handler() -> tuple[ChargebackHandler, InMemoryMAAudit]:
    store = InMemoryDisputeStore()
    audit = InMemoryMAAudit()
    return ChargebackHandler(store, audit), audit


@pytest.mark.asyncio
async def test_receive_chargeback_returns_dispute_with_received_status() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    assert d.status == DisputeStatus.RECEIVED
    assert d.id != ""


@pytest.mark.asyncio
async def test_receive_chargeback_creates_audit_event() -> None:
    handler, audit = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    events = await audit.list_events("m-001")
    assert any(e["event_type"] == "chargeback.received" for e in events)


@pytest.mark.asyncio
async def test_receive_chargeback_amount_is_decimal() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "99.99", "GBP", "FRAUD", "admin")
    assert isinstance(d.amount, Decimal)
    assert d.amount == Decimal("99.99")


@pytest.mark.asyncio
async def test_receive_chargeback_invalid_reason_raises_value_error() -> None:
    handler, _ = _make_handler()
    with pytest.raises(ValueError):
        await handler.receive_chargeback(
            "m-001", "p-001", "25.00", "GBP", "INVALID_REASON", "admin"
        )


@pytest.mark.asyncio
async def test_investigate_changes_status_to_under_investigation() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    updated = await handler.investigate(d.id, "admin")
    assert updated.status == DisputeStatus.UNDER_INVESTIGATION


@pytest.mark.asyncio
async def test_investigate_creates_audit_event() -> None:
    handler, audit = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    await handler.investigate(d.id, "admin")
    events = await audit.list_events("m-001")
    assert any(e["event_type"] == "chargeback.investigating" for e in events)


@pytest.mark.asyncio
async def test_submit_evidence_sets_represented_and_evidence_flag() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    await handler.investigate(d.id, "admin")
    represented = await handler.submit_evidence(d.id, "admin")
    assert represented.status == DisputeStatus.REPRESENTED
    assert represented.evidence_submitted is True


@pytest.mark.asyncio
async def test_submit_evidence_creates_audit_event() -> None:
    handler, audit = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    await handler.submit_evidence(d.id, "admin")
    events = await audit.list_events("m-001")
    assert any(e["event_type"] == "chargeback.evidence_submitted" for e in events)


@pytest.mark.asyncio
async def test_resolve_won_true_gives_resolved_win() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    resolved = await handler.resolve(d.id, won=True, actor="admin")
    assert resolved.status == DisputeStatus.RESOLVED_WIN


@pytest.mark.asyncio
async def test_resolve_won_false_gives_resolved_loss() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    resolved = await handler.resolve(d.id, won=False, actor="admin")
    assert resolved.status == DisputeStatus.RESOLVED_LOSS


@pytest.mark.asyncio
async def test_resolve_sets_resolved_at() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    resolved = await handler.resolve(d.id, won=True, actor="admin")
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_creates_audit_event() -> None:
    handler, audit = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    await handler.resolve(d.id, won=True, actor="admin")
    events = await audit.list_events("m-001")
    assert any(e["event_type"] == "chargeback.resolved" for e in events)


@pytest.mark.asyncio
async def test_get_dispute_existing() -> None:
    handler, _ = _make_handler()
    d = await handler.receive_chargeback("m-001", "p-001", "25.00", "GBP", "FRAUD", "admin")
    found = await handler.get_dispute(d.id)
    assert found is not None
    assert found.id == d.id


@pytest.mark.asyncio
async def test_list_disputes_returns_all_for_merchant() -> None:
    handler, _ = _make_handler()
    await handler.receive_chargeback("m-001", "p-001", "10.00", "GBP", "FRAUD", "admin")
    await handler.receive_chargeback("m-001", "p-002", "20.00", "GBP", "DUPLICATE", "admin")
    disputes = await handler.list_disputes("m-001")
    assert len(disputes) == 2
