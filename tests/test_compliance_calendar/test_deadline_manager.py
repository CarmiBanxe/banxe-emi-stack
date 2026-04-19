"""
tests/test_compliance_calendar/test_deadline_manager.py
IL-CCD-01 | Phase 42 | 18 tests
"""

from __future__ import annotations

from datetime import date, timedelta
import hashlib

import pytest

from services.compliance_calendar.deadline_manager import DeadlineManager, HITLProposal
from services.compliance_calendar.models import (
    DeadlineStatus,
    DeadlineType,
    InMemoryDeadlineStore,
    Priority,
)


def _manager() -> tuple[DeadlineManager, InMemoryDeadlineStore]:
    store = InMemoryDeadlineStore()
    return DeadlineManager(deadline_store=store), store


def _create_test_deadline(manager: DeadlineManager, days_ahead: int = 30) -> object:
    return manager.create_deadline(
        title="Test Deadline",
        deadline_type=DeadlineType.CUSTOM,
        priority=Priority.MEDIUM,
        due_date=date.today() + timedelta(days=days_ahead),
        owner="tester",
        description="Test",
    )


class TestCreateDeadline:
    def test_create_returns_deadline(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        assert dl.id is not None

    def test_create_status_upcoming(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        assert dl.status == DeadlineStatus.UPCOMING

    def test_create_title_stored(self) -> None:
        manager, _ = _manager()
        dl = manager.create_deadline(
            "FIN060 Q1", DeadlineType.FCA_RETURN, Priority.CRITICAL, date.today(), "CFO", "desc"
        )
        assert dl.title == "FIN060 Q1"

    def test_create_stores_in_store(self) -> None:
        manager, store = _manager()
        dl = _create_test_deadline(manager)
        fetched = store.get_deadline(dl.id)
        assert fetched is not None


class TestUpdateDeadline:
    def test_update_returns_hitl_proposal(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        proposal = manager.update_deadline(dl.id, {"due_date": "2026-05-01"})
        assert isinstance(proposal, HITLProposal)

    def test_update_autonomy_l4(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        proposal = manager.update_deadline(dl.id, {})
        assert proposal.autonomy_level == "L4"

    def test_update_approver_compliance(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        proposal = manager.update_deadline(dl.id, {})
        assert "COMPLIANCE" in proposal.requires_approval_from.upper()


class TestCompleteDeadline:
    def test_complete_status_completed(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        updated = manager.complete_deadline(dl.id, "evidence text")
        assert updated.status == DeadlineStatus.COMPLETED

    def test_complete_sha256_evidence_hash(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        evidence = "signed audit report"
        updated = manager.complete_deadline(dl.id, evidence)
        expected_hash = hashlib.sha256(evidence.encode()).hexdigest()
        assert updated.evidence_hash == expected_hash

    def test_complete_sets_completed_at(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        updated = manager.complete_deadline(dl.id, "evidence")
        assert updated.completed_at is not None

    def test_complete_unknown_raises(self) -> None:
        manager, _ = _manager()
        with pytest.raises(ValueError):
            manager.complete_deadline("nonexistent-id", "evidence")


class TestMissDeadline:
    def test_miss_medium_becomes_overdue(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        updated = manager.miss_deadline(dl.id)
        assert updated.status == DeadlineStatus.OVERDUE

    def test_miss_critical_becomes_escalated(self) -> None:
        manager, _ = _manager()
        dl = manager.create_deadline(
            "Critical",
            DeadlineType.FCA_RETURN,
            Priority.CRITICAL,
            date.today() - timedelta(days=1),
            "CFO",
            "desc",
        )
        updated = manager.miss_deadline(dl.id)
        assert updated.status == DeadlineStatus.ESCALATED

    def test_miss_unknown_raises(self) -> None:
        manager, _ = _manager()
        with pytest.raises(ValueError):
            manager.miss_deadline("nonexistent")


class TestListUpcoming:
    def test_upcoming_within_30_days(self) -> None:
        manager, _ = _manager()
        manager.create_deadline(
            "Soon",
            DeadlineType.CUSTOM,
            Priority.LOW,
            date.today() + timedelta(days=10),
            "owner",
            "desc",
        )
        upcoming = manager.list_upcoming(30)
        assert any(d.title == "Soon" for d in upcoming)

    def test_far_future_not_in_upcoming(self) -> None:
        manager, store = _manager()
        for dl in store.list_all():
            if dl.id not in ("dl-fca-fin060-q1", "dl-board-q1-risk"):
                store.save_deadline(dl)
        manager.create_deadline(
            "Far",
            DeadlineType.CUSTOM,
            Priority.LOW,
            date.today() + timedelta(days=365),
            "owner",
            "desc",
        )
        upcoming = manager.list_upcoming(30)
        assert all(d.title != "Far" for d in upcoming)

    def test_overdue_not_in_upcoming(self) -> None:
        manager, _ = _manager()
        dl = manager.create_deadline(
            "Past",
            DeadlineType.CUSTOM,
            Priority.LOW,
            date.today() - timedelta(days=5),
            "owner",
            "desc",
        )
        manager.miss_deadline(dl.id)
        upcoming = manager.list_upcoming(30)
        assert all(d.id != dl.id for d in upcoming)


class TestGetOverdue:
    def test_overdue_included(self) -> None:
        manager, _ = _manager()
        dl = _create_test_deadline(manager)
        manager.miss_deadline(dl.id)
        overdue = manager.get_overdue()
        assert any(d.id == dl.id for d in overdue)

    def test_escalated_included_in_overdue(self) -> None:
        manager, _ = _manager()
        dl = manager.create_deadline(
            "Crit", DeadlineType.FCA_RETURN, Priority.CRITICAL, date.today(), "CFO", "x"
        )
        manager.miss_deadline(dl.id)
        overdue = manager.get_overdue()
        assert any(d.id == dl.id for d in overdue)
