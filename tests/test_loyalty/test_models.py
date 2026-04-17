"""
tests/test_loyalty/test_models.py — Unit tests for loyalty domain models
IL-LRE-01 | Phase 29 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

import pytest

from services.loyalty.models import (
    CampaignStatus,
    EarnRule,
    EarnRuleType,
    ExpiryStatus,
    InMemoryEarnRuleStore,
    InMemoryPointsBalanceStore,
    InMemoryPointsTransactionStore,
    InMemoryRedeemOptionStore,
    PointsBalance,
    PointsTransaction,
    PointsTransactionType,
    RedeemOption,
    RedeemOptionType,
    RewardTier,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ── Enum value tests ──────────────────────────────────────────────────────


def test_reward_tier_bronze_value() -> None:
    assert RewardTier.BRONZE.value == "BRONZE"


def test_reward_tier_silver_value() -> None:
    assert RewardTier.SILVER.value == "SILVER"


def test_reward_tier_gold_value() -> None:
    assert RewardTier.GOLD.value == "GOLD"


def test_reward_tier_platinum_value() -> None:
    assert RewardTier.PLATINUM.value == "PLATINUM"


def test_points_transaction_type_values() -> None:
    assert PointsTransactionType.EARN.value == "EARN"
    assert PointsTransactionType.REDEEM.value == "REDEEM"
    assert PointsTransactionType.EXPIRE.value == "EXPIRE"
    assert PointsTransactionType.ADJUST.value == "ADJUST"
    assert PointsTransactionType.BONUS.value == "BONUS"


def test_redeem_option_type_values() -> None:
    assert RedeemOptionType.CASHBACK.value == "CASHBACK"
    assert RedeemOptionType.FX_DISCOUNT.value == "FX_DISCOUNT"
    assert RedeemOptionType.CARD_FEE_WAIVER.value == "CARD_FEE_WAIVER"
    assert RedeemOptionType.VOUCHER.value == "VOUCHER"


def test_earn_rule_type_values() -> None:
    assert EarnRuleType.CARD_SPEND.value == "CARD_SPEND"
    assert EarnRuleType.FX.value == "FX"
    assert EarnRuleType.DIRECT_DEBIT.value == "DIRECT_DEBIT"
    assert EarnRuleType.SIGNUP_BONUS.value == "SIGNUP_BONUS"
    assert EarnRuleType.REFERRAL_BONUS.value == "REFERRAL_BONUS"


def test_campaign_status_values() -> None:
    assert CampaignStatus.ACTIVE.value == "ACTIVE"
    assert CampaignStatus.PAUSED.value == "PAUSED"
    assert CampaignStatus.ENDED.value == "ENDED"


def test_expiry_status_values() -> None:
    assert ExpiryStatus.ACTIVE.value == "ACTIVE"
    assert ExpiryStatus.EXPIRING_SOON.value == "EXPIRING_SOON"
    assert ExpiryStatus.EXPIRED.value == "EXPIRED"


# ── Dataclass creation and frozen tests ───────────────────────────────────


def test_points_balance_creation() -> None:
    now = _now()
    b = PointsBalance(
        balance_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tier=RewardTier.BRONZE,
        total_points=Decimal("500"),
        pending_points=Decimal("0"),
        lifetime_points=Decimal("500"),
        updated_at=now,
    )
    assert b.customer_id == "cust-1"
    assert b.tier == RewardTier.BRONZE
    assert b.total_points == Decimal("500")


def test_points_balance_frozen() -> None:
    now = _now()
    b = PointsBalance(
        balance_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tier=RewardTier.BRONZE,
        total_points=Decimal("0"),
        pending_points=Decimal("0"),
        lifetime_points=Decimal("0"),
        updated_at=now,
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        b.total_points = Decimal("999")  # type: ignore[misc]


def test_earn_rule_creation() -> None:
    now = _now()
    rule = EarnRule(
        rule_id=str(uuid.uuid4()),
        rule_type=EarnRuleType.CARD_SPEND,
        tier=RewardTier.GOLD,
        points_per_unit=Decimal("2"),
        multiplier=Decimal("2.0"),
        max_monthly_earn=Decimal("20000"),
        active=True,
        created_at=now,
    )
    assert rule.tier == RewardTier.GOLD
    assert rule.points_per_unit == Decimal("2")
    assert rule.active is True


def test_redeem_option_creation() -> None:
    now = _now()
    opt = RedeemOption(
        option_id="opt-test",
        option_type=RedeemOptionType.CASHBACK,
        points_required=Decimal("1000"),
        reward_value=Decimal("1.00"),
        description="1000 points = £1",
        active=True,
        created_at=now,
    )
    assert opt.option_id == "opt-test"
    assert opt.points_required == Decimal("1000")


def test_points_transaction_creation() -> None:
    now = _now()
    tx = PointsTransaction(
        tx_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tx_type=PointsTransactionType.EARN,
        points=Decimal("100"),
        balance_after=Decimal("100"),
        reference_id="ref-1",
        description="test earn",
        created_at=now,
    )
    assert tx.points == Decimal("100")
    assert tx.expires_at is None


def test_points_transaction_with_expiry() -> None:
    now = _now()
    tx = PointsTransaction(
        tx_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tx_type=PointsTransactionType.EARN,
        points=Decimal("50"),
        balance_after=Decimal("50"),
        reference_id="",
        description="earn with expiry",
        created_at=now,
        expires_at=now,
    )
    assert tx.expires_at is not None


# ── InMemoryPointsBalanceStore ─────────────────────────────────────────────


def test_balance_store_save_and_get() -> None:
    store = InMemoryPointsBalanceStore()
    b = PointsBalance(
        balance_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tier=RewardTier.SILVER,
        total_points=Decimal("1500"),
        pending_points=Decimal("0"),
        lifetime_points=Decimal("2000"),
        updated_at=_now(),
    )
    store.save(b)
    result = store.get("cust-1")
    assert result is not None
    assert result.total_points == Decimal("1500")


def test_balance_store_get_missing_returns_none() -> None:
    store = InMemoryPointsBalanceStore()
    assert store.get("nonexistent") is None


def test_balance_store_update() -> None:
    store = InMemoryPointsBalanceStore()
    b = PointsBalance(
        balance_id=str(uuid.uuid4()),
        customer_id="cust-2",
        tier=RewardTier.BRONZE,
        total_points=Decimal("100"),
        pending_points=Decimal("0"),
        lifetime_points=Decimal("100"),
        updated_at=_now(),
    )
    store.save(b)
    updated = dataclasses.replace(b, total_points=Decimal("200"))
    store.update(updated)
    assert store.get("cust-2").total_points == Decimal("200")


# ── InMemoryEarnRuleStore seeded rules ─────────────────────────────────────


def test_earn_rule_store_bronze_card_spend_seeded() -> None:
    store = InMemoryEarnRuleStore()
    rules = store.get_rules_for_tier(RewardTier.BRONZE)
    card_rules = [r for r in rules if r.rule_type == EarnRuleType.CARD_SPEND]
    assert len(card_rules) == 1
    assert card_rules[0].multiplier == Decimal("1.0")


def test_earn_rule_store_silver_card_spend_multiplier() -> None:
    store = InMemoryEarnRuleStore()
    rules = store.get_rules_for_tier(RewardTier.SILVER)
    card_rules = [r for r in rules if r.rule_type == EarnRuleType.CARD_SPEND]
    assert card_rules[0].multiplier == Decimal("1.5")


def test_earn_rule_store_gold_card_spend_multiplier() -> None:
    store = InMemoryEarnRuleStore()
    rules = store.get_rules_for_tier(RewardTier.GOLD)
    card_rules = [r for r in rules if r.rule_type == EarnRuleType.CARD_SPEND]
    assert card_rules[0].multiplier == Decimal("2.0")


def test_earn_rule_store_platinum_card_spend_multiplier() -> None:
    store = InMemoryEarnRuleStore()
    rules = store.get_rules_for_tier(RewardTier.PLATINUM)
    card_rules = [r for r in rules if r.rule_type == EarnRuleType.CARD_SPEND]
    assert card_rules[0].multiplier == Decimal("3.0")


def test_earn_rule_store_list_all_returns_multiple() -> None:
    store = InMemoryEarnRuleStore()
    all_rules = store.list_all()
    assert len(all_rules) >= 7  # 4 CARD_SPEND + FX + DD + SIGNUP


# ── InMemoryRedeemOptionStore seeded options ───────────────────────────────


def test_redeem_option_store_cashback_seeded() -> None:
    store = InMemoryRedeemOptionStore()
    opt = store.get("opt-cashback")
    assert opt is not None
    assert opt.points_required == Decimal("1000")
    assert opt.reward_value == Decimal("1.00")


def test_redeem_option_store_card_fee_seeded() -> None:
    store = InMemoryRedeemOptionStore()
    opt = store.get("opt-card-fee")
    assert opt is not None
    assert opt.points_required == Decimal("2000")


def test_redeem_option_store_voucher_seeded() -> None:
    store = InMemoryRedeemOptionStore()
    opt = store.get("opt-voucher")
    assert opt is not None
    assert opt.points_required == Decimal("5000")


def test_redeem_option_store_list_active_returns_4() -> None:
    store = InMemoryRedeemOptionStore()
    active = store.list_active()
    assert len(active) == 4


# ── InMemoryPointsTransactionStore append-only ─────────────────────────────


def test_tx_store_append_and_list() -> None:
    store = InMemoryPointsTransactionStore()
    tx = PointsTransaction(
        tx_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tx_type=PointsTransactionType.EARN,
        points=Decimal("100"),
        balance_after=Decimal("100"),
        reference_id="",
        description="earn",
        created_at=_now(),
    )
    store.append(tx)
    result = store.list_by_customer("cust-1")
    assert len(result) == 1
    assert result[0].tx_id == tx.tx_id


def test_tx_store_list_expiring_before() -> None:
    from datetime import timedelta

    store = InMemoryPointsTransactionStore()
    now = _now()
    past = now - timedelta(days=1)

    expiring_tx = PointsTransaction(
        tx_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tx_type=PointsTransactionType.EARN,
        points=Decimal("50"),
        balance_after=Decimal("50"),
        reference_id="",
        description="expiring",
        created_at=past,
        expires_at=past,
    )
    future_tx = PointsTransaction(
        tx_id=str(uuid.uuid4()),
        customer_id="cust-1",
        tx_type=PointsTransactionType.EARN,
        points=Decimal("50"),
        balance_after=Decimal("100"),
        reference_id="",
        description="not expiring",
        created_at=now,
        expires_at=now + timedelta(days=30),
    )
    store.append(expiring_tx)
    store.append(future_tx)
    result = store.list_expiring_before(now)
    assert len(result) == 1
    assert result[0].tx_id == expiring_tx.tx_id
