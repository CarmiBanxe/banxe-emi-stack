"""
tests/test_compliance_calendar/test_task_tracker.py
IL-CCD-01 | Phase 42 | 14 tests
"""

from __future__ import annotations

import pytest

from services.compliance_calendar.models import InMemoryTaskStore
from services.compliance_calendar.task_tracker import TaskTracker


def _tracker() -> tuple[TaskTracker, InMemoryTaskStore]:
    store = InMemoryTaskStore()
    return TaskTracker(task_store=store), store


class TestCreateTask:
    def test_create_returns_task(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Draft report", "user-1")
        assert task.id is not None

    def test_create_status_pending(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Review docs", "user-1")
        assert task.status == "PENDING"

    def test_create_progress_zero(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Review docs", "user-1")
        assert task.progress == 0


class TestAssignTask:
    def test_assign_updates_assignee(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Task", "user-1")
        updated = tracker.assign_task(task.id, "user-2")
        assert updated.assigned_to == "user-2"

    def test_assign_unknown_raises(self) -> None:
        tracker, _ = _tracker()
        with pytest.raises(ValueError):
            tracker.assign_task("nonexistent", "user-1")


class TestUpdateProgress:
    def test_update_progress_50(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Task", "user-1")
        updated = tracker.update_progress(task.id, 50)
        assert updated.progress == 50

    def test_progress_100_auto_completes(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Task", "user-1")
        updated = tracker.update_progress(task.id, 100)
        assert updated.status == "COMPLETED"
        assert updated.completed_at is not None

    def test_invalid_progress_raises(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Task", "user-1")
        with pytest.raises(ValueError):
            tracker.update_progress(task.id, 101)

    def test_negative_progress_raises(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Task", "user-1")
        with pytest.raises(ValueError):
            tracker.update_progress(task.id, -1)


class TestCompleteTask:
    def test_complete_sets_status(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Task", "user-1")
        updated = tracker.complete_task(task.id)
        assert updated.status == "COMPLETED"

    def test_complete_sets_100_progress(self) -> None:
        tracker, _ = _tracker()
        task = tracker.create_task("dl-1", "Task", "user-1")
        updated = tracker.complete_task(task.id)
        assert updated.progress == 100

    def test_complete_unknown_raises(self) -> None:
        tracker, _ = _tracker()
        with pytest.raises(ValueError):
            tracker.complete_task("nonexistent")


class TestWorkloadSummary:
    def test_summary_counts_correctly(self) -> None:
        tracker, _ = _tracker()
        tracker.create_task("dl-1", "Task 1", "user-3")
        tracker.create_task("dl-2", "Task 2", "user-3")
        t3 = tracker.create_task("dl-3", "Task 3", "user-3")
        tracker.complete_task(t3.id)
        summary = tracker.get_workload_summary("user-3")
        assert summary["total"] == 3
        assert summary["completed"] == 1

    def test_empty_assignee_zeros(self) -> None:
        tracker, _ = _tracker()
        summary = tracker.get_workload_summary("nonexistent-user")
        assert summary["total"] == 0
