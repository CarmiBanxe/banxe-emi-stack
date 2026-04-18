"""
tests/test_risk_management/test_mitigation_tracker.py
IL-RMS-01 | Phase 37 | banxe-emi-stack — 18 tests
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.risk_management.mitigation_tracker import MitigationTracker, _sha256
from services.risk_management.models import (
    InMemoryMitigationPort,
    MitigationAction,
)


def _tracker() -> MitigationTracker:
    return MitigationTracker(InMemoryMitigationPort())


def _due_future() -> datetime:
    return datetime.now(UTC) + timedelta(days=30)


def _due_past() -> datetime:
    return datetime.now(UTC) - timedelta(days=5)


class TestCreatePlan:
    def test_returns_plan(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix AML gap", "Alice", _due_future())
        assert plan.id != ""

    def test_initial_action_is_identified(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix gap", "Alice", _due_future())
        assert plan.action == MitigationAction.IDENTIFIED

    def test_evidence_hash_is_sha256(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix gap", "Alice", _due_future())
        expected = _sha256("assess-1" + "Fix gap")
        assert plan.evidence_hash == expected

    def test_completed_at_is_none(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix gap", "Alice", _due_future())
        assert plan.completed_at is None

    def test_owner_stored(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-2", "Desc", "Bob", _due_future())
        assert plan.owner == "Bob"


class TestUpdateAction:
    def test_update_to_in_progress(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix", "Alice", _due_future())
        updated = tracker.update_action(plan.id, MitigationAction.IN_PROGRESS)
        assert updated.action == MitigationAction.IN_PROGRESS

    def test_mitigated_sets_completed_at(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix", "Alice", _due_future())
        updated = tracker.update_action(plan.id, MitigationAction.MITIGATED)
        assert updated.completed_at is not None

    def test_evidence_hash_updated_with_evidence(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix", "Alice", _due_future())
        evidence = "screenshot.png content"
        updated = tracker.update_action(plan.id, MitigationAction.IN_PROGRESS, evidence)
        expected = _sha256(evidence)
        assert updated.evidence_hash == expected

    def test_no_evidence_keeps_old_hash(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix", "Alice", _due_future())
        old_hash = plan.evidence_hash
        updated = tracker.update_action(plan.id, MitigationAction.IN_PROGRESS)
        assert updated.evidence_hash == old_hash

    def test_unknown_plan_raises(self) -> None:
        tracker = _tracker()
        with pytest.raises(ValueError, match="not found"):
            tracker.update_action("nonexistent-plan", MitigationAction.MITIGATED)


class TestListOverdue:
    def test_overdue_plan_returned(self) -> None:
        tracker = _tracker()
        tracker.create_plan("assess-1", "Fix", "Alice", _due_past())
        overdue = tracker.list_overdue()
        assert len(overdue) >= 1

    def test_future_plan_not_returned(self) -> None:
        tracker = _tracker()
        tracker.create_plan("assess-2", "Fix", "Alice", _due_future())
        overdue = tracker.list_overdue()
        assert all(p.due_date.date() < __import__("datetime").date.today() for p in overdue)

    def test_mitigated_not_returned(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-3", "Fix", "Alice", _due_past())
        tracker.update_action(plan.id, MitigationAction.MITIGATED)
        overdue = tracker.list_overdue()
        assert all(p.id != plan.id for p in overdue)

    def test_accepted_not_returned(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-4", "Fix", "Alice", _due_past())
        tracker.update_action(plan.id, MitigationAction.ACCEPTED)
        overdue = tracker.list_overdue()
        assert all(p.id != plan.id for p in overdue)


class TestAttachEvidence:
    def test_recomputes_hash(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix", "Alice", _due_future())
        evidence = "new evidence"
        updated = tracker.attach_evidence(plan.id, evidence)
        assert updated.evidence_hash == _sha256(evidence)

    def test_old_hash_different(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix", "Alice", _due_future())
        old_hash = plan.evidence_hash
        updated = tracker.attach_evidence(plan.id, "new evidence")
        assert updated.evidence_hash != old_hash

    def test_get_plan_returns_none_for_unknown(self) -> None:
        tracker = _tracker()
        assert tracker.get_plan("no-such-plan") is None

    def test_get_plan_returns_plan(self) -> None:
        tracker = _tracker()
        plan = tracker.create_plan("assess-1", "Fix", "Alice", _due_future())
        fetched = tracker.get_plan(plan.id)
        assert fetched is not None
        assert fetched.id == plan.id
