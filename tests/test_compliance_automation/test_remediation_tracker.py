"""tests/test_compliance_automation/test_remediation_tracker.py — RemediationTracker."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.compliance_automation.models import (
    InMemoryRemediationStore,
    RemediationStatus,
)
from services.compliance_automation.remediation_tracker import RemediationTracker

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
_DUE = datetime(2026, 2, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def tracker():
    return RemediationTracker(InMemoryRemediationStore())


@pytest.mark.asyncio
async def test_create_remediation_open_status(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    assert r.status == RemediationStatus.OPEN
    assert r.check_id == "c-1"
    assert r.entity_id == "ent-1"
    assert r.assigned_to == "alice"


@pytest.mark.asyncio
async def test_create_remediation_has_uuid_id(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    assert len(r.remediation_id) == 36


@pytest.mark.asyncio
async def test_create_remediation_resolved_at_none(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    assert r.resolved_at is None


@pytest.mark.asyncio
async def test_update_status_open_to_assigned(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    updated = await tracker.update_status(r.remediation_id, RemediationStatus.ASSIGNED)
    assert updated.status == RemediationStatus.ASSIGNED


@pytest.mark.asyncio
async def test_update_status_assigned_to_in_progress(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    r2 = await tracker.update_status(r.remediation_id, RemediationStatus.ASSIGNED)
    r3 = await tracker.update_status(r2.remediation_id, RemediationStatus.IN_PROGRESS)
    assert r3.status == RemediationStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_update_status_in_progress_to_resolved(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    r2 = await tracker.update_status(r.remediation_id, RemediationStatus.ASSIGNED)
    r3 = await tracker.update_status(r2.remediation_id, RemediationStatus.IN_PROGRESS)
    r4 = await tracker.update_status(r3.remediation_id, RemediationStatus.RESOLVED)
    assert r4.status == RemediationStatus.RESOLVED
    assert r4.resolved_at is not None


@pytest.mark.asyncio
async def test_update_status_resolved_to_verified(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    r2 = await tracker.update_status(r.remediation_id, RemediationStatus.ASSIGNED)
    r3 = await tracker.update_status(r2.remediation_id, RemediationStatus.IN_PROGRESS)
    r4 = await tracker.update_status(r3.remediation_id, RemediationStatus.RESOLVED)
    r5 = await tracker.update_status(r4.remediation_id, RemediationStatus.VERIFIED)
    assert r5.status == RemediationStatus.VERIFIED


@pytest.mark.asyncio
async def test_update_status_verified_to_closed(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    for status in [
        RemediationStatus.ASSIGNED,
        RemediationStatus.IN_PROGRESS,
        RemediationStatus.RESOLVED,
        RemediationStatus.VERIFIED,
    ]:
        r = await tracker.update_status(r.remediation_id, status)
    r_closed = await tracker.update_status(r.remediation_id, RemediationStatus.CLOSED)
    assert r_closed.status == RemediationStatus.CLOSED


@pytest.mark.asyncio
async def test_update_status_invalid_transition_raises(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    with pytest.raises(ValueError, match="Invalid transition"):
        await tracker.update_status(r.remediation_id, RemediationStatus.RESOLVED)


@pytest.mark.asyncio
async def test_update_status_open_to_closed_invalid(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    with pytest.raises(ValueError):
        await tracker.update_status(r.remediation_id, RemediationStatus.CLOSED)


@pytest.mark.asyncio
async def test_update_status_not_found_raises(tracker):
    with pytest.raises(ValueError, match="not found"):
        await tracker.update_status("nonexistent", RemediationStatus.ASSIGNED)


@pytest.mark.asyncio
async def test_get_remediation_by_id(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    fetched = await tracker.get_remediation(r.remediation_id)
    assert fetched is not None
    assert fetched.remediation_id == r.remediation_id


@pytest.mark.asyncio
async def test_get_remediation_not_found(tracker):
    result = await tracker.get_remediation("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_open_remediations_includes_open(tracker):
    await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    open_items = await tracker.list_open_remediations()
    assert len(open_items) == 1


@pytest.mark.asyncio
async def test_list_open_remediations_excludes_closed(tracker):
    r = await tracker.create_remediation("c-1", "ent-1", "finding", "alice", _DUE)
    for status in [
        RemediationStatus.ASSIGNED,
        RemediationStatus.IN_PROGRESS,
        RemediationStatus.RESOLVED,
        RemediationStatus.VERIFIED,
        RemediationStatus.CLOSED,
    ]:
        r = await tracker.update_status(r.remediation_id, status)
    open_items = await tracker.list_open_remediations()
    assert len(open_items) == 0


@pytest.mark.asyncio
async def test_list_open_remediations_filtered_by_entity(tracker):
    await tracker.create_remediation("c-1", "ent-1", "f1", "alice", _DUE)
    await tracker.create_remediation("c-2", "ent-2", "f2", "bob", _DUE)
    items = await tracker.list_open_remediations(entity_id="ent-1")
    assert len(items) == 1
    assert items[0].entity_id == "ent-1"
