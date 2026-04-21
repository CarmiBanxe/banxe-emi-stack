"""
tests/test_consumer_duty/test_consumer_support_tracker.py
Tests for ConsumerSupportTracker: SLA breach rate, interaction recording.
IL-CDO-01 | Phase 50 | Sprint 35

≥20 tests covering:
- record_interaction (SHA-256 ID, I-24 append)
- record_resolution (append-only, I-24)
- get_sla_breach_rate (Decimal, I-01, within/over SLA)
- get_support_outcomes_summary
- SLA_TARGETS constants
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.consumer_duty.consumer_support_tracker import (
    SLA_TARGETS,
    ConsumerSupportTracker,
)


def make_tracker() -> ConsumerSupportTracker:
    return ConsumerSupportTracker()


# ── record_interaction tests ──────────────────────────────────────────────────


def test_record_interaction_returns_id() -> None:
    """Test record_interaction returns interaction_id."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "support", "phone")
    assert iid.startswith("int_")


def test_record_interaction_sha256_id_format() -> None:
    """Test interaction_id has int_ prefix and 8-char hash."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "support", "email")
    parts = iid.split("_")
    assert parts[0] == "int"
    assert len(parts[1]) == 8


def test_record_interaction_multiple_appends() -> None:
    """Test multiple interactions are all stored (I-24 append-only)."""
    tracker = make_tracker()
    tracker.record_interaction("c1", "complaint", "phone")
    tracker.record_interaction("c1", "support", "email")
    tracker.record_interaction("c2", "complaint", "chat")
    # 3 interactions stored
    assert len(tracker._interactions) == 3


def test_record_interaction_different_channels() -> None:
    """Test interactions with different channels are recorded."""
    tracker = make_tracker()
    for channel in ["phone", "email", "chat", "app"]:
        iid = tracker.record_interaction("c1", "support", channel)
        assert iid is not None


# ── record_resolution tests ───────────────────────────────────────────────────


def test_record_resolution_marks_resolved() -> None:
    """Test record_resolution stores resolution time."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "support", "phone")
    tracker.record_resolution(iid, 3600, "resolved")
    # Two records: original + resolved
    assert len(tracker._interactions) == 2


def test_record_resolution_unknown_raises() -> None:
    """Test record_resolution raises ValueError for unknown interaction."""
    tracker = make_tracker()
    with pytest.raises(ValueError, match="not found"):
        tracker.record_resolution("int_unknown", 3600, "resolved")


def test_record_resolution_append_only() -> None:
    """Test record_resolution appends new version (I-24 — not overwrite)."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "complaint", "email")
    tracker.record_resolution(iid, 7200, "complaint resolved")
    # Original + resolved = 2 records
    assert len(tracker._interactions) == 2


# ── get_sla_breach_rate tests ─────────────────────────────────────────────────


def test_get_sla_breach_rate_no_interactions_returns_zero() -> None:
    """Test breach rate is 0.0 when no interactions exist."""
    tracker = make_tracker()
    rate = tracker.get_sla_breach_rate("support")
    assert rate == Decimal("0.0")


def test_get_sla_breach_rate_within_sla_returns_zero() -> None:
    """Test breach rate is 0.0 when all resolved within SLA."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "support", "phone")
    tracker.record_resolution(iid, 1800, "resolved")  # 30 min < 2hr SLA
    rate = tracker.get_sla_breach_rate("support")
    assert rate == Decimal("0.0")


def test_get_sla_breach_rate_over_sla_returns_one() -> None:
    """Test breach rate is 1.0 when all resolved over SLA."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "support", "phone")
    tracker.record_resolution(iid, 10000, "resolved")  # > 2hr SLA
    rate = tracker.get_sla_breach_rate("support")
    assert rate == Decimal("1.0")


def test_get_sla_breach_rate_is_decimal() -> None:
    """Test breach rate is Decimal (I-01)."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "support", "phone")
    tracker.record_resolution(iid, 3600, "resolved")
    rate = tracker.get_sla_breach_rate("support")
    assert isinstance(rate, Decimal)


def test_get_sla_breach_rate_partial_breach() -> None:
    """Test breach rate is 0.5 when half breach SLA."""
    tracker = make_tracker()
    iid1 = tracker.record_interaction("c1", "support", "phone")
    iid2 = tracker.record_interaction("c2", "support", "email")
    tracker.record_resolution(iid1, 1800, "resolved")  # within SLA
    tracker.record_resolution(iid2, 10000, "resolved")  # over SLA
    rate = tracker.get_sla_breach_rate("support")
    assert rate == Decimal("0.5")


def test_get_sla_breach_rate_complaint_type() -> None:
    """Test breach rate for 'complaint' type uses complaint SLA."""
    tracker = make_tracker()
    sla = SLA_TARGETS["complaint"]  # 8 * 24 * 3600 = 691200s
    iid = tracker.record_interaction("c1", "complaint", "phone")
    tracker.record_resolution(iid, sla - 1, "resolved")  # just within SLA
    rate = tracker.get_sla_breach_rate("complaint")
    assert rate == Decimal("0.0")


# ── SLA_TARGETS tests ─────────────────────────────────────────────────────────


def test_sla_targets_complaint_is_8_business_days() -> None:
    """Test complaint SLA is 8 * 24 * 3600 seconds."""
    assert SLA_TARGETS["complaint"] == 8 * 24 * 3600


def test_sla_targets_support_is_2_hours() -> None:
    """Test support SLA is 2 * 3600 seconds."""
    assert SLA_TARGETS["support"] == 2 * 3600


# ── get_support_outcomes_summary tests ────────────────────────────────────────


def test_get_support_outcomes_summary_empty() -> None:
    """Test support outcomes summary is empty initially."""
    tracker = make_tracker()
    summary = tracker.get_support_outcomes_summary()
    assert summary["total_interactions"] == 0
    assert summary["resolved_count"] == 0


def test_get_support_outcomes_summary_counts_interactions() -> None:
    """Test support outcomes summary counts interactions."""
    tracker = make_tracker()
    iid = tracker.record_interaction("c1", "support", "phone")
    tracker.record_resolution(iid, 1800, "resolved")
    summary = tracker.get_support_outcomes_summary()
    assert summary["resolved_count"] >= 1


def test_get_support_outcomes_summary_has_breach_rates() -> None:
    """Test support outcomes summary includes breach rates."""
    tracker = make_tracker()
    summary = tracker.get_support_outcomes_summary()
    assert "complaint_sla_breach_rate" in summary
    assert "support_sla_breach_rate" in summary
