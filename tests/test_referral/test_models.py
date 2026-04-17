"""
tests/test_referral/test_models.py — Unit tests for referral domain models
IL-REF-01 | Phase 30 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

import pytest

from services.referral.models import (
    CampaignStatus,
    FraudCheck,
    FraudReason,
    InMemoryFraudCheckStore,
    InMemoryReferralCampaignStore,
    InMemoryReferralCodeStore,
    InMemoryReferralStore,
    Referral,
    ReferralCampaign,
    ReferralCode,
    ReferralReward,
    ReferralStatus,
    RewardStatus,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ── Enum tests ─────────────────────────────────────────────────────────────


def test_referral_status_values() -> None:
    assert ReferralStatus.INVITED.value == "INVITED"
    assert ReferralStatus.REGISTERED.value == "REGISTERED"
    assert ReferralStatus.KYC_COMPLETE.value == "KYC_COMPLETE"
    assert ReferralStatus.QUALIFIED.value == "QUALIFIED"
    assert ReferralStatus.REWARDED.value == "REWARDED"
    assert ReferralStatus.FRAUDULENT.value == "FRAUDULENT"


def test_reward_status_values() -> None:
    assert RewardStatus.PENDING.value == "PENDING"
    assert RewardStatus.APPROVED.value == "APPROVED"
    assert RewardStatus.PAID.value == "PAID"
    assert RewardStatus.REJECTED.value == "REJECTED"


def test_campaign_status_values() -> None:
    assert CampaignStatus.DRAFT.value == "DRAFT"
    assert CampaignStatus.ACTIVE.value == "ACTIVE"
    assert CampaignStatus.PAUSED.value == "PAUSED"
    assert CampaignStatus.ENDED.value == "ENDED"


def test_fraud_reason_values() -> None:
    assert FraudReason.SELF_REFERRAL.value == "SELF_REFERRAL"
    assert FraudReason.VELOCITY_ABUSE.value == "VELOCITY_ABUSE"
    assert FraudReason.SAME_IP.value == "SAME_IP"
    assert FraudReason.SAME_DEVICE.value == "SAME_DEVICE"
    assert FraudReason.DUPLICATE_ACCOUNT.value == "DUPLICATE_ACCOUNT"


# ── Dataclass creation tests ───────────────────────────────────────────────


def test_referral_code_creation() -> None:
    code = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id="cust-1",
        code="BANXETEST",
        campaign_id="camp-default",
        created_at=_now(),
        is_vanity=True,
    )
    assert code.code == "BANXETEST"
    assert code.is_vanity is True
    assert code.used_count == 0
    assert code.max_uses == 100


def test_referral_code_frozen() -> None:
    code = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id="cust-2",
        code="TESTCODE",
        campaign_id="camp-1",
        created_at=_now(),
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        code.code = "MODIFIED"  # type: ignore[misc]


def test_referral_creation() -> None:
    ref = Referral(
        referral_id=str(uuid.uuid4()),
        referrer_id="ref-1",
        referee_id="ref-2",
        code="ABCD1234",
        campaign_id="camp-default",
        status=ReferralStatus.INVITED,
        created_at=_now(),
    )
    assert ref.status == ReferralStatus.INVITED
    assert ref.qualified_at is None
    assert ref.rewarded_at is None


def test_referral_reward_creation() -> None:
    reward = ReferralReward(
        reward_id=str(uuid.uuid4()),
        referral_id="ref-id-1",
        recipient_id="cust-1",
        amount=Decimal("25.00"),
        reward_type="referrer",
        status=RewardStatus.PENDING,
        created_at=_now(),
    )
    assert reward.amount == Decimal("25.00")
    assert reward.status == RewardStatus.PENDING
    assert reward.paid_at is None


def test_referral_campaign_creation() -> None:
    now = _now()
    campaign = ReferralCampaign(
        campaign_id="camp-1",
        name="Test Campaign",
        referrer_reward=Decimal("25.00"),
        referee_reward=Decimal("10.00"),
        total_budget=Decimal("10000.00"),
        spent_budget=Decimal("0"),
        status=CampaignStatus.ACTIVE,
        start_date=now,
        created_at=now,
    )
    assert campaign.referrer_reward == Decimal("25.00")
    assert campaign.referee_reward == Decimal("10.00")
    assert campaign.end_date is None


def test_fraud_check_creation() -> None:
    check = FraudCheck(
        check_id=str(uuid.uuid4()),
        referral_id="ref-1",
        fraud_reason=FraudReason.SELF_REFERRAL,
        is_fraudulent=True,
        confidence_score=Decimal("1.0"),
        checked_at=_now(),
    )
    assert check.is_fraudulent is True
    assert check.confidence_score == Decimal("1.0")


def test_fraud_check_clean_has_no_reason() -> None:
    check = FraudCheck(
        check_id=str(uuid.uuid4()),
        referral_id="ref-2",
        fraud_reason=None,
        is_fraudulent=False,
        confidence_score=Decimal("0.0"),
        checked_at=_now(),
    )
    assert check.fraud_reason is None
    assert check.is_fraudulent is False


# ── InMemoryReferralCodeStore ──────────────────────────────────────────────


def test_code_store_save_and_get_by_code() -> None:
    store = InMemoryReferralCodeStore()
    code = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id="cust-1",
        code="ABCD1234",
        campaign_id="camp-1",
        created_at=_now(),
    )
    store.save(code)
    result = store.get_by_code("ABCD1234")
    assert result is not None
    assert result.customer_id == "cust-1"


def test_code_store_get_by_customer() -> None:
    store = InMemoryReferralCodeStore()
    code = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id="cust-2",
        code="EFGH5678",
        campaign_id="camp-1",
        created_at=_now(),
    )
    store.save(code)
    result = store.get_by_customer("cust-2")
    assert len(result) == 1


def test_code_store_get_missing_returns_none() -> None:
    store = InMemoryReferralCodeStore()
    assert store.get_by_code("NONEXIST") is None


def test_code_store_update() -> None:
    store = InMemoryReferralCodeStore()
    code = ReferralCode(
        code_id=str(uuid.uuid4()),
        customer_id="cust-3",
        code="IJKL9012",
        campaign_id="camp-1",
        created_at=_now(),
    )
    store.save(code)
    updated = dataclasses.replace(code, used_count=1)
    store.update(updated)
    result = store.get_by_code("IJKL9012")
    assert result.used_count == 1


# ── InMemoryReferralStore ──────────────────────────────────────────────────


def test_referral_store_save_and_get() -> None:
    store = InMemoryReferralStore()
    ref = Referral(
        referral_id="ref-id-1",
        referrer_id="r1",
        referee_id="r2",
        code="CODE1",
        campaign_id="camp-1",
        status=ReferralStatus.INVITED,
        created_at=_now(),
    )
    store.save(ref)
    assert store.get("ref-id-1") is not None


def test_referral_store_list_by_referrer() -> None:
    store = InMemoryReferralStore()
    ref = Referral(
        referral_id="ref-id-2",
        referrer_id="r1",
        referee_id="r3",
        code="CODE2",
        campaign_id="camp-1",
        status=ReferralStatus.INVITED,
        created_at=_now(),
    )
    store.save(ref)
    result = store.list_by_referrer("r1")
    assert len(result) == 1


# ── InMemoryReferralCampaignStore seeded default campaign ─────────────────


def test_campaign_store_seeded_default_campaign() -> None:
    store = InMemoryReferralCampaignStore()
    campaign = store.get("camp-default")
    assert campaign is not None
    assert campaign.status == CampaignStatus.ACTIVE


def test_campaign_store_default_referrer_reward() -> None:
    store = InMemoryReferralCampaignStore()
    campaign = store.get("camp-default")
    assert campaign.referrer_reward == Decimal("25.00")


def test_campaign_store_default_referee_reward() -> None:
    store = InMemoryReferralCampaignStore()
    campaign = store.get("camp-default")
    assert campaign.referee_reward == Decimal("10.00")


def test_campaign_store_default_budget() -> None:
    store = InMemoryReferralCampaignStore()
    campaign = store.get("camp-default")
    assert campaign.total_budget == Decimal("100000.00")


def test_campaign_store_list_active_returns_default() -> None:
    store = InMemoryReferralCampaignStore()
    active = store.list_active()
    assert len(active) >= 1
    ids = [c.campaign_id for c in active]
    assert "camp-default" in ids


# ── InMemoryFraudCheckStore append-only ────────────────────────────────────


def test_fraud_store_save_and_get_by_referral() -> None:
    store = InMemoryFraudCheckStore()
    check = FraudCheck(
        check_id=str(uuid.uuid4()),
        referral_id="ref-fraud-1",
        fraud_reason=FraudReason.SELF_REFERRAL,
        is_fraudulent=True,
        confidence_score=Decimal("1.0"),
        checked_at=_now(),
    )
    store.save(check)
    result = store.get_by_referral("ref-fraud-1")
    assert result is not None
    assert result.is_fraudulent is True


def test_fraud_store_get_missing_returns_none() -> None:
    store = InMemoryFraudCheckStore()
    assert store.get_by_referral("nonexistent") is None


def test_fraud_store_returns_latest_check() -> None:
    store = InMemoryFraudCheckStore()
    check1 = FraudCheck(
        check_id=str(uuid.uuid4()),
        referral_id="ref-1",
        fraud_reason=FraudReason.SELF_REFERRAL,
        is_fraudulent=True,
        confidence_score=Decimal("1.0"),
        checked_at=_now(),
    )
    check2 = FraudCheck(
        check_id=str(uuid.uuid4()),
        referral_id="ref-1",
        fraud_reason=None,
        is_fraudulent=False,
        confidence_score=Decimal("0.0"),
        checked_at=_now(),
    )
    store.save(check1)
    store.save(check2)
    result = store.get_by_referral("ref-1")
    assert result.check_id == check2.check_id
