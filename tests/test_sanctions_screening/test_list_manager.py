"""Tests for ListManager — Phase 46 (IL-SRS-01)."""

from __future__ import annotations

import pytest

from services.sanctions_screening.list_manager import ListManager
from services.sanctions_screening.models import InMemoryListStore, ListSource


def make_manager():
    return ListManager(InMemoryListStore())


# --- load_list ---


def test_load_list_returns_sanctions_list():
    mgr = make_manager()
    entries = [{"id": "x_001", "name": "Test Person", "nationality": "XX"}]
    lst = mgr.load_list(ListSource.UN_CONSOLIDATED, entries, "v1.0")
    assert lst.source == ListSource.UN_CONSOLIDATED
    assert lst.entry_count == 1


def test_load_list_computes_sha256_checksum():
    mgr = make_manager()
    entries = [{"id": "x_001", "name": "Test"}]
    lst = mgr.load_list(ListSource.UN_CONSOLIDATED, entries, "v1.0")
    assert len(lst.checksum) == 64  # I-12: SHA-256


def test_load_list_different_entries_different_checksum():
    mgr = make_manager()
    lst1 = mgr.load_list(ListSource.US_OFAC, [{"id": "a"}], "v1.0")
    lst2 = mgr.load_list(ListSource.US_OFAC, [{"id": "b"}], "v1.1")
    assert lst1.checksum != lst2.checksum


def test_load_list_saves_to_store():
    store = InMemoryListStore()
    mgr = ListManager(store)
    mgr.load_list(ListSource.UN_CONSOLIDATED, [{"id": "a"}], "v1.0")
    assert store.get_list(ListSource.UN_CONSOLIDATED) is not None


# --- update_list ---


def test_update_list_different_checksum_ok():
    mgr = make_manager()
    mgr.load_list(ListSource.UN_CONSOLIDATED, [{"id": "old"}], "v1.0")
    lst = mgr.update_list(ListSource.UN_CONSOLIDATED, [{"id": "new"}], "v1.1")
    assert lst.version == "v1.1"


def test_update_list_same_checksum_raises():
    mgr = make_manager()
    entries = [{"id": "same"}]
    mgr.load_list(ListSource.UN_CONSOLIDATED, entries, "v1.0")
    with pytest.raises(ValueError, match="checksum"):
        mgr.update_list(ListSource.UN_CONSOLIDATED, entries, "v1.1")


# --- get_active_lists ---


def test_get_active_lists_returns_seeded():
    mgr = make_manager()
    lists = mgr.get_active_lists()
    sources = [lst.source for lst in lists]
    assert ListSource.OFSI in sources
    assert ListSource.EU_CONSOLIDATED in sources


def test_get_active_lists_count():
    mgr = make_manager()
    lists = mgr.get_active_lists()
    assert len(lists) >= 2


# --- get_list_version ---


def test_get_list_version_existing():
    mgr = make_manager()
    version = mgr.get_list_version(ListSource.OFSI)
    assert version is not None


def test_get_list_version_missing():
    mgr = make_manager()
    version = mgr.get_list_version(ListSource.UN_CONSOLIDATED)
    assert version is None


# --- schedule_refresh ---


def test_schedule_refresh_returns_dict():
    mgr = make_manager()
    result = mgr.schedule_refresh(ListSource.OFSI)
    assert result["scheduled"] is True
    assert result["source"] == "ofsi"


# --- compare_versions ---


def test_compare_versions_different():
    mgr = make_manager()
    result = mgr.compare_versions(ListSource.OFSI, "v1.0", "v2.0")
    assert result["changed"] is True
    assert result["old_version"] == "v1.0"


def test_compare_versions_same():
    mgr = make_manager()
    result = mgr.compare_versions(ListSource.OFSI, "v1.0", "v1.0")
    assert result["changed"] is False
