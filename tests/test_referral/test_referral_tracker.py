"""
tests/test_referral/test_referral_tracker.py — Unit tests for ReferralTracker
IL-REF-01 | Phase 30 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

import pytest

from services.referral.models import (
    InMemoryReferralCodeStore,
    InMemoryReferralStore,
    ReferralCode,
)
from services.referral.referral_tracker import ReferralTracker


def _setup_tracker_with_code(
    referrer_id: str = "referrer-1",
    campaign_id: str = "camp-default",
    code_str: str = "TESTCODE",
) -> tuple[ReferralTracker, str]:
    """Create a tracker with a pre-saved code, return (tracker, code_str)."""
    code_store = InMemoryReferralCodeStore()
    ref_store = InMemoryReferralStore()
    code = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id=referrer_id,
        code=code_str,
        campaign_id=campaign_id,
        created_at=datetime.now(UTC),
    )
    code_store.save(code)
    tracker = ReferralTracker(referral_store=ref_store, code_store=code_store)
    return tracker, code_str


# ── track_referral ─────────────────────────────────────────────────────────


def test_track_referral_success() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-1", code_str="ABCD1234")
    result = tracker.track_referral("new-cust", code_str)
    assert result["status"] == "INVITED"


def test_track_referral_returns_referrer_id() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-2", code_str="EFGH5678")
    result = tracker.track_referral("new-cust-2", code_str)
    assert result["referrer_id"] == "ref-2"


def test_track_referral_returns_referee_id() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-3", code_str="IJKL9012")
    result = tracker.track_referral("target-cust", code_str)
    assert result["referee_id"] == "target-cust"


def test_track_referral_has_referral_id() -> None:
    tracker, code_str = _setup_tracker_with_code(code_str="MNOP3456")
    result = tracker.track_referral("new-cust-3", code_str)
    assert result["referral_id"] != ""


def test_track_referral_self_referral_raises() -> None:
    tracker, code_str = _setup_tracker_with_code("self-cust", code_str="QRST7890")
    with pytest.raises(ValueError, match="self_referral"):
        tracker.track_referral("self-cust", code_str)


def test_track_referral_invalid_code_raises() -> None:
    code_store = InMemoryReferralCodeStore()
    tracker = ReferralTracker(code_store=code_store)
    with pytest.raises(ValueError, match="Invalid referral code"):
        tracker.track_referral("some-cust", "NONEXIST")


def test_track_referral_already_referred_raises() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-4", code_str="UVWX1234")
    tracker.track_referral("already-cust", code_str)

    # Use different code for second referral attempt
    code_store2 = tracker._code_store
    code2 = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id="ref-4b",
        code="YZAB5678",
        campaign_id="camp-default",
        created_at=datetime.now(UTC),
    )
    code_store2.save(code2)
    with pytest.raises(ValueError, match="already referred"):
        tracker.track_referral("already-cust", "YZAB5678")


def test_track_referral_increments_code_usage() -> None:
    code_store = InMemoryReferralCodeStore()
    code = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id="ref-5",
        code="CODE0001",
        campaign_id="camp-1",
        created_at=datetime.now(UTC),
        used_count=0,
    )
    code_store.save(code)
    tracker = ReferralTracker(code_store=code_store)
    tracker.track_referral("new-ref-5", "CODE0001")
    updated = code_store.get_by_code("CODE0001")
    assert updated.used_count == 1


# ── advance_status ─────────────────────────────────────────────────────────


def test_advance_status_invited_to_registered() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-6", code_str="ADVA0001")
    result = tracker.track_referral("adv-cust-1", code_str)
    referral_id = result["referral_id"]
    adv = tracker.advance_status(referral_id, "REGISTERED")
    assert adv["status"] == "REGISTERED"


def test_advance_status_registered_to_kyc_complete() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-7", code_str="ADVA0002")
    result = tracker.track_referral("adv-cust-2", code_str)
    rid = result["referral_id"]
    tracker.advance_status(rid, "REGISTERED")
    adv = tracker.advance_status(rid, "KYC_COMPLETE")
    assert adv["status"] == "KYC_COMPLETE"


def test_advance_status_kyc_to_qualified() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-8", code_str="ADVA0003")
    result = tracker.track_referral("adv-cust-3", code_str)
    rid = result["referral_id"]
    tracker.advance_status(rid, "REGISTERED")
    tracker.advance_status(rid, "KYC_COMPLETE")
    adv = tracker.advance_status(rid, "QUALIFIED")
    assert adv["status"] == "QUALIFIED"
    assert adv["qualified_at"] is not None


def test_advance_status_invalid_transition_raises() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-9", code_str="ADVA0004")
    result = tracker.track_referral("adv-cust-4", code_str)
    rid = result["referral_id"]
    with pytest.raises(ValueError, match="Invalid transition"):
        tracker.advance_status(rid, "QUALIFIED")  # skip REGISTERED and KYC


def test_advance_status_not_found_raises() -> None:
    code_store = InMemoryReferralCodeStore()
    tracker = ReferralTracker(code_store=code_store)
    with pytest.raises(ValueError, match="Referral not found"):
        tracker.advance_status("nonexistent-id", "REGISTERED")


def test_advance_status_fraudulent_valid_from_invited() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-10", code_str="ADVA0005")
    result = tracker.track_referral("adv-cust-5", code_str)
    rid = result["referral_id"]
    adv = tracker.advance_status(rid, "FRAUDULENT")
    assert adv["status"] == "FRAUDULENT"


# ── get_referral_status ────────────────────────────────────────────────────


def test_get_referral_status_returns_correct_fields() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-11", code_str="STAT0001")
    result = tracker.track_referral("stat-cust-1", code_str)
    rid = result["referral_id"]
    status = tracker.get_referral_status(rid)
    assert status["referral_id"] == rid
    assert status["status"] == "INVITED"


def test_get_referral_status_not_found_raises() -> None:
    code_store = InMemoryReferralCodeStore()
    tracker = ReferralTracker(code_store=code_store)
    with pytest.raises(ValueError, match="Referral not found"):
        tracker.get_referral_status("nonexistent")


# ── list_referrals_by_referrer ─────────────────────────────────────────────


def test_list_referrals_by_referrer_empty() -> None:
    code_store = InMemoryReferralCodeStore()
    tracker = ReferralTracker(code_store=code_store)
    result = tracker.list_referrals_by_referrer("no-referrals-referrer")
    assert result["referrals"] == []


def test_list_referrals_by_referrer_returns_referral() -> None:
    tracker, code_str = _setup_tracker_with_code("ref-12", code_str="LIST0001")
    tracker.track_referral("list-cust-1", code_str)
    result = tracker.list_referrals_by_referrer("ref-12")
    assert len(result["referrals"]) == 1
