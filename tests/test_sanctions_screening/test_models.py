"""Tests for sanctions screening models — Phase 46 (IL-SRS-01)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from services.sanctions_screening.models import (
    AlertCase,
    AlertStatus,
    EntityType,
    HITLProposal,
    InMemoryAlertStore,
    InMemoryHitStore,
    InMemoryListStore,
    InMemoryScreeningStore,
    ListSource,
    MatchConfidence,
    SanctionsList,
    ScreeningHit,
    ScreeningRequest,
    ScreeningResult,
)

# --- Enum values ---


def test_screening_result_enum():
    assert ScreeningResult.CLEAR == "clear"
    assert ScreeningResult.POSSIBLE_MATCH == "possible_match"
    assert ScreeningResult.CONFIRMED_MATCH == "confirmed_match"
    assert ScreeningResult.ERROR == "error"


def test_list_source_enum():
    assert ListSource.OFSI == "ofsi"
    assert ListSource.EU_CONSOLIDATED == "eu_consolidated"


def test_match_confidence_enum():
    assert MatchConfidence.LOW == "low"
    assert MatchConfidence.MEDIUM == "medium"
    assert MatchConfidence.HIGH == "high"


def test_entity_type_enum():
    assert EntityType.INDIVIDUAL == "individual"
    assert EntityType.ORGANISATION == "organisation"
    assert EntityType.VESSEL == "vessel"


def test_alert_status_enum():
    assert AlertStatus.OPEN == "open"
    assert AlertStatus.RESOLVED_TRUE == "resolved_true_positive"
    assert AlertStatus.RESOLVED_FALSE == "resolved_false_positive"


# --- Frozen dataclasses ---


def test_screening_request_is_frozen():
    req = ScreeningRequest(
        "req_001", "John", EntityType.INDIVIDUAL, "GB", None, "system", "2026-01-01T00:00:00Z"
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        req.entity_name = "Changed"  # type: ignore[misc]


def test_screening_hit_is_frozen():
    hit = ScreeningHit(
        "hit_001",
        "req_001",
        ListSource.OFSI,
        MatchConfidence.HIGH,
        Decimal("90"),
        "Ivan Petrov",
        "ofsi_001",
        "details",
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        hit.match_score = Decimal("50")  # type: ignore[misc]


def test_screening_hit_score_is_decimal():
    hit = ScreeningHit(
        "hit_001",
        "req_001",
        ListSource.OFSI,
        MatchConfidence.HIGH,
        Decimal("90.5"),
        "Ivan Petrov",
        "ofsi_001",
        "details",
    )
    assert isinstance(hit.match_score, Decimal)


def test_alert_case_is_frozen():
    alert = AlertCase(
        "alert_001", "req_001", "hit_001", AlertStatus.OPEN, "officer", "2026-01-01T00:00:00Z"
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        alert.status = AlertStatus.ESCALATED  # type: ignore[misc]


def test_sanctions_list_has_sha256():
    lst = SanctionsList("lst_001", ListSource.OFSI, "v1", 10, "2026-01-01", "a" * 64)
    assert len(lst.checksum) == 64


# --- HITLProposal mutable ---


def test_hitl_proposal_mutable():
    p = HITLProposal("freeze", "Ivan", "MLRO", "test")
    p.reason = "updated"
    assert p.reason == "updated"


def test_hitl_proposal_default_autonomy():
    p = HITLProposal("freeze", "Ivan", "MLRO", "test")
    assert p.autonomy_level == "L4"


# --- InMemory stores ---


def test_inmemory_screening_store_save_get_request():
    store = InMemoryScreeningStore()
    req = ScreeningRequest(
        "req_001", "John", EntityType.INDIVIDUAL, "GB", None, "system", "2026-01-01T00:00:00Z"
    )
    store.save_request(req)
    assert store.get_request("req_001") is not None


def test_inmemory_screening_store_get_missing():
    store = InMemoryScreeningStore()
    assert store.get_request("missing") is None


def test_inmemory_list_store_seeded_ofsi():
    store = InMemoryListStore()
    lst = store.get_list(ListSource.OFSI)
    assert lst is not None
    assert lst.entry_count == 5


def test_inmemory_list_store_seeded_eu():
    store = InMemoryListStore()
    lst = store.get_list(ListSource.EU_CONSOLIDATED)
    assert lst is not None


def test_inmemory_list_store_entries():
    store = InMemoryListStore()
    entries = store.get_entries(ListSource.OFSI)
    assert len(entries) >= 1


def test_inmemory_alert_store_append_only():
    store = InMemoryAlertStore()
    alert = AlertCase(
        "alert_001", "req_001", "hit_001", AlertStatus.OPEN, "officer", "2026-01-01T00:00:00Z"
    )
    store.append(alert)
    assert len(store.list_open()) >= 1


def test_inmemory_alert_store_no_delete():
    store = InMemoryAlertStore()
    assert not hasattr(store, "delete")
    assert not hasattr(store, "update")


def test_inmemory_hit_store_append_only():
    store = InMemoryHitStore()
    hit = ScreeningHit(
        "hit_001",
        "req_001",
        ListSource.OFSI,
        MatchConfidence.HIGH,
        Decimal("90"),
        "Ivan",
        "ofsi_001",
        "details",
    )
    store.append(hit)
    hits = store.list_by_request("req_001")
    assert len(hits) == 1


def test_inmemory_hit_store_no_delete():
    store = InMemoryHitStore()
    assert not hasattr(store, "delete")
    assert not hasattr(store, "update")
