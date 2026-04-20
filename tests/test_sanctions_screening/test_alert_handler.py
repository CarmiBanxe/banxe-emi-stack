"""Tests for AlertHandler — Phase 46 (IL-SRS-01)."""

from __future__ import annotations

import pytest

from services.sanctions_screening.alert_handler import AlertHandler
from services.sanctions_screening.models import (
    AlertStatus,
    HITLProposal,
    InMemoryAlertStore,
    InMemoryHitStore,
)


def make_handler():
    return AlertHandler(InMemoryAlertStore(), InMemoryHitStore())


# --- create_alert ---


def test_create_alert_returns_open():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    assert alert.status == AlertStatus.OPEN


def test_create_alert_has_id():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    assert alert.alert_id.startswith("alert_")


def test_create_alert_appended_to_store():
    store = InMemoryAlertStore()
    h = AlertHandler(store, InMemoryHitStore())
    h.create_alert("req_001", "hit_001", "officer")
    assert len(store.list_open()) == 1


def test_create_alert_i24_append():
    store = InMemoryAlertStore()
    h = AlertHandler(store, InMemoryHitStore())
    h.create_alert("req_001", "hit_001", "officer_1")
    h.create_alert("req_002", "hit_002", "officer_2")
    assert len(store.list_open()) == 2


# --- escalate_alert (I-27) ---


def test_escalate_alert_returns_hitl():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    result = h.escalate_alert(alert.alert_id, "suspected", "supervisor")
    assert isinstance(result, HITLProposal)


def test_escalate_alert_requires_mlro():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    result = h.escalate_alert(alert.alert_id, "high risk", "supervisor")
    assert result.requires_approval_from == "MLRO"


def test_escalate_alert_autonomy_l4():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    result = h.escalate_alert(alert.alert_id, "reason", "supervisor")
    assert result.autonomy_level == "L4"


# --- resolve_alert (I-24 new record) ---


def test_resolve_alert_true_positive():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    resolved = h.resolve_alert(alert.alert_id, True, "officer", "confirmed")
    assert resolved.status == AlertStatus.RESOLVED_TRUE


def test_resolve_alert_false_positive():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    resolved = h.resolve_alert(alert.alert_id, False, "officer", "not a match")
    assert resolved.status == AlertStatus.RESOLVED_FALSE


def test_resolve_alert_creates_new_record_i24():
    store = InMemoryAlertStore()
    h = AlertHandler(store, InMemoryHitStore())
    alert = h.create_alert("req_001", "hit_001", "officer")
    h.resolve_alert(alert.alert_id, True, "officer", "confirmed")
    # Both the original OPEN and the new RESOLVED should be in the log
    assert len(store._log) == 2


def test_resolve_alert_nonexistent_raises():
    h = make_handler()
    with pytest.raises(ValueError):
        h.resolve_alert("nonexistent", True, "officer")


# --- auto_block_confirmed (I-27) ---


def test_auto_block_confirmed_returns_hitl():
    h = make_handler()
    alert = h.create_alert("req_001", "hit_001", "officer")
    result = h.auto_block_confirmed(alert.alert_id, "Ivan Petrov")
    assert isinstance(result, HITLProposal)
    assert result.requires_approval_from == "MLRO"
    assert result.action == "auto_block_entity"


# --- get_pending_alerts ---


def test_get_pending_alerts_empty():
    h = make_handler()
    assert h.get_pending_alerts() == []


def test_get_pending_alerts_returns_open():
    h = make_handler()
    h.create_alert("req_001", "hit_001", "officer")
    pending = h.get_pending_alerts()
    assert len(pending) == 1


# --- get_alert_stats ---


def test_get_alert_stats_fields():
    h = make_handler()
    stats = h.get_alert_stats()
    assert "total" in stats
    assert "open" in stats
    assert "resolved_true" in stats
    assert "resolved_false" in stats
    assert "escalated" in stats


def test_get_alert_stats_counts():
    h = make_handler()
    h.create_alert("req_001", "hit_001", "officer")
    stats = h.get_alert_stats()
    assert stats["open"] == 1
    assert stats["total"] >= 1
