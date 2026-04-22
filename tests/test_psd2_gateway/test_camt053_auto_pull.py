"""Tests for camt053_auto_pull.py — schedule, execute_pull, list_active, I-24.

IL-PSD2GW-01 | Phase 52B | Sprint 37
"""

from __future__ import annotations

import pytest

from services.psd2_gateway.camt053_auto_pull import (
    AutoPuller,
    InMemoryPullScheduleStore,
    PullSchedule,
)

# ── PullSchedule ───────────────────────────────────────────────────────────


def test_pull_schedule_frozen() -> None:
    from dataclasses import FrozenInstanceError

    schedule = PullSchedule(
        schedule_id="pull_001",
        iban="GB29NWBK60161331926819",
        frequency="daily",
        last_pull_at=None,
        enabled=True,
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        schedule.enabled = False  # type: ignore[misc]


def test_pull_schedule_default_enabled() -> None:
    schedule = PullSchedule(
        schedule_id="pull_001",
        iban="GB29NWBK60161331926819",
        frequency="daily",
        last_pull_at=None,
        enabled=True,
    )
    assert schedule.enabled is True


# ── InMemoryPullScheduleStore ──────────────────────────────────────────────


def test_store_append_and_get() -> None:
    store = InMemoryPullScheduleStore()
    schedule = PullSchedule(
        schedule_id="pull_test",
        iban="GB29NWBK60161331926819",
        frequency="daily",
        last_pull_at=None,
        enabled=True,
    )
    store.append(schedule)
    found = store.get("pull_test")
    assert found is not None
    assert found.schedule_id == "pull_test"


def test_store_get_missing() -> None:
    store = InMemoryPullScheduleStore()
    assert store.get("nonexistent") is None


def test_store_list_active_filters_disabled() -> None:
    store = InMemoryPullScheduleStore()
    active = PullSchedule(
        schedule_id="pull_a",
        iban="GB29NWBK60161331926819",
        frequency="daily",
        last_pull_at=None,
        enabled=True,
    )
    disabled = PullSchedule(
        schedule_id="pull_d",
        iban="DE89370400440532013000",
        frequency="weekly",
        last_pull_at=None,
        enabled=False,
    )
    store.append(active)
    store.append(disabled)
    result = store.list_active()
    assert len(result) == 1
    assert result[0].schedule_id == "pull_a"


# ── AutoPuller.schedule ────────────────────────────────────────────────────


def test_schedule_returns_pull_schedule() -> None:
    puller = AutoPuller()
    schedule = puller.schedule("GB29NWBK60161331926819")
    assert isinstance(schedule, PullSchedule)
    assert schedule.enabled is True


def test_schedule_appends_to_store() -> None:
    """I-24: schedule must append to store."""
    store = InMemoryPullScheduleStore()
    puller = AutoPuller(store=store)
    puller.schedule("GB29NWBK60161331926819")
    assert len(store.list_active()) == 1


def test_schedule_deterministic_id() -> None:
    """Same IBAN + frequency = same schedule_id."""
    store1 = InMemoryPullScheduleStore()
    store2 = InMemoryPullScheduleStore()
    s1 = AutoPuller(store=store1).schedule("GB29NWBK60161331926819", "daily")
    s2 = AutoPuller(store=store2).schedule("GB29NWBK60161331926819", "daily")
    assert s1.schedule_id == s2.schedule_id


def test_schedule_different_frequency_different_id() -> None:
    s1 = AutoPuller().schedule("GB29NWBK60161331926819", "daily")
    s2 = AutoPuller().schedule("GB29NWBK60161331926819", "weekly")
    assert s1.schedule_id != s2.schedule_id


def test_schedule_id_starts_with_pull() -> None:
    puller = AutoPuller()
    schedule = puller.schedule("GB29NWBK60161331926819")
    assert schedule.schedule_id.startswith("pull_")


def test_schedule_default_daily() -> None:
    puller = AutoPuller()
    schedule = puller.schedule("GB29NWBK60161331926819")
    assert schedule.frequency == "daily"


def test_schedule_weekly() -> None:
    puller = AutoPuller()
    schedule = puller.schedule("GB29NWBK60161331926819", "weekly")
    assert schedule.frequency == "weekly"


def test_schedule_iban_stored() -> None:
    store = InMemoryPullScheduleStore()
    puller = AutoPuller(store=store)
    puller.schedule("GB29NWBK60161331926819")
    active = store.list_active()
    assert active[0].iban == "GB29NWBK60161331926819"


def test_schedule_last_pull_at_none() -> None:
    puller = AutoPuller()
    schedule = puller.schedule("GB29NWBK60161331926819")
    assert schedule.last_pull_at is None


# ── AutoPuller.execute_pull ────────────────────────────────────────────────


def test_execute_pull_returns_summary() -> None:
    store = InMemoryPullScheduleStore()
    puller = AutoPuller(store=store)
    schedule = puller.schedule("GB29NWBK60161331926819")
    result = puller.execute_pull(schedule.schedule_id)
    assert result["status"] == "pulled"
    assert result["schedule_id"] == schedule.schedule_id


def test_execute_pull_masks_iban() -> None:
    """No PII: IBAN must be masked in result."""
    store = InMemoryPullScheduleStore()
    puller = AutoPuller(store=store)
    schedule = puller.schedule("GB29NWBK60161331926819")
    result = puller.execute_pull(schedule.schedule_id)
    # Full IBAN must not appear in result
    assert "GB29NW" in result["iban"]  # first 6 OK
    assert result["iban"].endswith("***")


def test_execute_pull_has_pulled_at() -> None:
    store = InMemoryPullScheduleStore()
    puller = AutoPuller(store=store)
    schedule = puller.schedule("GB29NWBK60161331926819")
    result = puller.execute_pull(schedule.schedule_id)
    assert "T" in result["pulled_at"]  # ISO timestamp


def test_execute_pull_missing_schedule_raises() -> None:
    puller = AutoPuller()
    with pytest.raises(KeyError):
        puller.execute_pull("nonexistent_schedule")


def test_execute_pull_transactions_fetched_stub() -> None:
    store = InMemoryPullScheduleStore()
    puller = AutoPuller(store=store)
    schedule = puller.schedule("GB29NWBK60161331926819")
    result = puller.execute_pull(schedule.schedule_id)
    assert result["transactions_fetched"] == 0  # stub


# ── AutoPuller.list_active_schedules ──────────────────────────────────────


def test_list_active_schedules_returns_list() -> None:
    store = InMemoryPullScheduleStore()
    puller = AutoPuller(store=store)
    puller.schedule("GB29NWBK60161331926819")
    puller.schedule("DE89370400440532013000")
    active = puller.list_active_schedules()
    assert len(active) == 2


def test_list_active_schedules_empty() -> None:
    puller = AutoPuller()
    active = puller.list_active_schedules()
    assert active == []
