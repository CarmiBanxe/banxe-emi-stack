"""Tests for ScreeningEngine — Phase 46 (IL-SRS-01)."""

from __future__ import annotations

from decimal import Decimal

from services.sanctions_screening.models import (
    EntityType,
    InMemoryHitStore,
    InMemoryListStore,
    InMemoryScreeningStore,
    ScreeningResult,
)
from services.sanctions_screening.screening_engine import (
    AML_EDD_THRESHOLD,
    BLOCKED_JURISDICTIONS,
    MATCH_THRESHOLD_CONFIRMED,
    MATCH_THRESHOLD_POSSIBLE,
    ScreeningEngine,
)


def make_engine():
    return ScreeningEngine(InMemoryScreeningStore(), InMemoryListStore(), InMemoryHitStore())


# --- I-02: blocked jurisdictions → CONFIRMED_MATCH ---


def test_screen_entity_blocked_ru():
    engine = make_engine()
    report = engine.screen_entity("Ivan Petrov", EntityType.INDIVIDUAL, "RU")
    assert report.result == ScreeningResult.CONFIRMED_MATCH
    assert "blocked" in report.notes


def test_screen_entity_blocked_ir():
    engine = make_engine()
    report = engine.screen_entity("Corp", EntityType.ORGANISATION, "IR")
    assert report.result == ScreeningResult.CONFIRMED_MATCH


def test_screen_entity_blocked_kp():
    engine = make_engine()
    report = engine.screen_entity("Test", EntityType.INDIVIDUAL, "KP")
    assert report.result == ScreeningResult.CONFIRMED_MATCH


def test_screen_entity_all_blocked_jurisdictions():
    engine = make_engine()
    for jur in BLOCKED_JURISDICTIONS:
        report = engine.screen_entity("Entity", EntityType.INDIVIDUAL, jur)
        assert report.result == ScreeningResult.CONFIRMED_MATCH


def test_screen_entity_clear_gb():
    engine = make_engine()
    report = engine.screen_entity("John Unknown Person", EntityType.INDIVIDUAL, "GB")
    assert report.result == ScreeningResult.CLEAR


def test_screen_entity_report_has_id():
    engine = make_engine()
    report = engine.screen_entity("Test Person", EntityType.INDIVIDUAL, "GB")
    assert report.report_id.startswith("rep_")
    assert report.request_id.startswith("req_")


def test_screen_entity_saves_report():
    store = InMemoryScreeningStore()
    engine = ScreeningEngine(store, InMemoryListStore(), InMemoryHitStore())
    report = engine.screen_entity("Test", EntityType.INDIVIDUAL, "GB")
    assert store.get_report(report.request_id) is not None


# --- I-04: EDD threshold ---


def test_screen_transaction_edd_triggered():
    engine = make_engine()
    report = engine.screen_transaction("John Doe", AML_EDD_THRESHOLD, "GB")
    assert "I-04" in report.notes
    assert "EDD" in report.notes


def test_screen_transaction_below_edd_no_flag():
    engine = make_engine()
    report = engine.screen_transaction("John Doe", Decimal("9999.99"), "GB")
    assert "EDD" not in report.notes


def test_screen_transaction_exactly_10k_triggers_edd():
    engine = make_engine()
    report = engine.screen_transaction("John Doe", Decimal("10000"), "GB")
    assert "EDD" in report.notes


def test_screen_transaction_blocked_nationality():
    engine = make_engine()
    report = engine.screen_transaction("Corp", Decimal("5000"), "RU")
    assert report.result == ScreeningResult.CONFIRMED_MATCH


# --- calculate_match_score ---


def test_calculate_match_score_is_decimal():
    engine = make_engine()
    score = engine.calculate_match_score("Ivan Petrov", "Ivan Petrov")
    assert isinstance(score, Decimal)


def test_calculate_match_score_exact_100():
    engine = make_engine()
    score = engine.calculate_match_score("Ivan", "Ivan")
    assert score == Decimal("100.00")


def test_calculate_match_score_different_names():
    engine = make_engine()
    score = engine.calculate_match_score("Ivan Petrov", "John Smith")
    assert score < MATCH_THRESHOLD_POSSIBLE


# --- batch_screen ---


def test_batch_screen_multiple_entities():
    engine = make_engine()
    entities = [
        {"name": "John Doe", "nationality": "GB"},
        {"name": "Jane Smith", "nationality": "US"},
    ]
    reports = engine.batch_screen(entities)
    assert len(reports) == 2


def test_batch_screen_empty():
    engine = make_engine()
    assert engine.batch_screen([]) == []


# --- Thresholds ---


def test_match_threshold_possible_is_decimal():
    assert isinstance(MATCH_THRESHOLD_POSSIBLE, Decimal)


def test_match_threshold_confirmed_is_decimal():
    assert isinstance(MATCH_THRESHOLD_CONFIRMED, Decimal)


def test_edd_threshold_is_decimal():
    assert isinstance(AML_EDD_THRESHOLD, Decimal)
    assert Decimal("10000") == AML_EDD_THRESHOLD
