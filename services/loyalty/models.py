"""
services/loyalty/models.py — Loyalty & Rewards domain models
IL-LRE-01 | Phase 29 | banxe-emi-stack

Domain models, enums, protocols, and InMemory stubs for the loyalty engine.
Protocol DI pattern throughout. Frozen dataclasses with dataclasses.replace() for mutations.
Invariants: I-01 (Decimal points/cashback), I-05 (amounts as strings), I-24 (append-only tx log).
FCA: PS22/9 (Consumer Duty — fair value), BCOBS 5 (post-sale).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol
import uuid


class RewardTier(str, Enum):
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


class PointsTransactionType(str, Enum):
    EARN = "EARN"
    REDEEM = "REDEEM"
    EXPIRE = "EXPIRE"
    ADJUST = "ADJUST"
    BONUS = "BONUS"


class RedeemOptionType(str, Enum):
    CASHBACK = "CASHBACK"
    FX_DISCOUNT = "FX_DISCOUNT"
    CARD_FEE_WAIVER = "CARD_FEE_WAIVER"
    VOUCHER = "VOUCHER"


class EarnRuleType(str, Enum):
    CARD_SPEND = "CARD_SPEND"
    FX = "FX"
    DIRECT_DEBIT = "DIRECT_DEBIT"
    SIGNUP_BONUS = "SIGNUP_BONUS"
    REFERRAL_BONUS = "REFERRAL_BONUS"


class CampaignStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class ExpiryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"


# ── Frozen dataclasses ────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoyaltyProgram:
    program_id: str
    name: str
    description: str
    created_at: datetime


@dataclass(frozen=True)
class PointsBalance:
    balance_id: str
    customer_id: str
    tier: RewardTier
    total_points: Decimal  # I-01: Decimal, never float
    pending_points: Decimal
    lifetime_points: Decimal
    updated_at: datetime


@dataclass(frozen=True)
class EarnRule:
    rule_id: str
    rule_type: EarnRuleType
    tier: RewardTier
    points_per_unit: Decimal
    multiplier: Decimal
    max_monthly_earn: Decimal
    active: bool
    created_at: datetime


@dataclass(frozen=True)
class RedeemOption:
    option_id: str
    option_type: RedeemOptionType
    points_required: Decimal
    reward_value: Decimal
    description: str
    active: bool
    created_at: datetime


@dataclass(frozen=True)
class PointsTransaction:
    tx_id: str
    customer_id: str
    tx_type: PointsTransactionType
    points: Decimal
    balance_after: Decimal
    reference_id: str
    description: str
    created_at: datetime
    expires_at: datetime | None = None


# ── Protocols (DI ports) ──────────────────────────────────────────────────


class PointsBalanceStorePort(Protocol):
    def get(self, customer_id: str) -> PointsBalance | None: ...
    def save(self, balance: PointsBalance) -> None: ...
    def update(self, balance: PointsBalance) -> None: ...


class EarnRuleStorePort(Protocol):
    def get_rules_for_tier(self, tier: RewardTier) -> list[EarnRule]: ...
    def save(self, rule: EarnRule) -> None: ...
    def list_all(self) -> list[EarnRule]: ...


class RedeemOptionStorePort(Protocol):
    def list_active(self) -> list[RedeemOption]: ...
    def get(self, option_id: str) -> RedeemOption | None: ...
    def save(self, option: RedeemOption) -> None: ...


class PointsTransactionStorePort(Protocol):
    def append(self, tx: PointsTransaction) -> None: ...
    def list_by_customer(self, customer_id: str, limit: int = 100) -> list[PointsTransaction]: ...
    def list_expiring_before(self, dt: datetime) -> list[PointsTransaction]: ...


# ── InMemory stubs ────────────────────────────────────────────────────────


class InMemoryPointsBalanceStore:
    def __init__(self) -> None:
        self._store: dict[str, PointsBalance] = {}

    def get(self, customer_id: str) -> PointsBalance | None:
        return self._store.get(customer_id)

    def save(self, balance: PointsBalance) -> None:
        self._store[balance.customer_id] = balance

    def update(self, balance: PointsBalance) -> None:
        self._store[balance.customer_id] = balance


class InMemoryEarnRuleStore:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self._rules: list[EarnRule] = [
            EarnRule(
                rule_id=str(uuid.uuid4()),
                rule_type=EarnRuleType.CARD_SPEND,
                tier=RewardTier.BRONZE,
                points_per_unit=Decimal("1"),
                multiplier=Decimal("1.0"),
                max_monthly_earn=Decimal("5000"),
                active=True,
                created_at=now,
            ),
            EarnRule(
                rule_id=str(uuid.uuid4()),
                rule_type=EarnRuleType.CARD_SPEND,
                tier=RewardTier.SILVER,
                points_per_unit=Decimal("1"),
                multiplier=Decimal("1.5"),
                max_monthly_earn=Decimal("10000"),
                active=True,
                created_at=now,
            ),
            EarnRule(
                rule_id=str(uuid.uuid4()),
                rule_type=EarnRuleType.CARD_SPEND,
                tier=RewardTier.GOLD,
                points_per_unit=Decimal("2"),
                multiplier=Decimal("2.0"),
                max_monthly_earn=Decimal("20000"),
                active=True,
                created_at=now,
            ),
            EarnRule(
                rule_id=str(uuid.uuid4()),
                rule_type=EarnRuleType.CARD_SPEND,
                tier=RewardTier.PLATINUM,
                points_per_unit=Decimal("3"),
                multiplier=Decimal("3.0"),
                max_monthly_earn=Decimal("50000"),
                active=True,
                created_at=now,
            ),
            EarnRule(
                rule_id=str(uuid.uuid4()),
                rule_type=EarnRuleType.FX,
                tier=RewardTier.GOLD,
                points_per_unit=Decimal("3"),
                multiplier=Decimal("3.0"),
                max_monthly_earn=Decimal("30000"),
                active=True,
                created_at=now,
            ),
            EarnRule(
                rule_id=str(uuid.uuid4()),
                rule_type=EarnRuleType.DIRECT_DEBIT,
                tier=RewardTier.BRONZE,
                points_per_unit=Decimal("1"),
                multiplier=Decimal("1.0"),
                max_monthly_earn=Decimal("2000"),
                active=True,
                created_at=now,
            ),
            EarnRule(
                rule_id=str(uuid.uuid4()),
                rule_type=EarnRuleType.SIGNUP_BONUS,
                tier=RewardTier.BRONZE,
                points_per_unit=Decimal("500"),
                multiplier=Decimal("1.0"),
                max_monthly_earn=Decimal("500"),
                active=True,
                created_at=now,
            ),
        ]

    def get_rules_for_tier(self, tier: RewardTier) -> list[EarnRule]:
        return [r for r in self._rules if r.tier == tier and r.active]

    def save(self, rule: EarnRule) -> None:
        self._rules.append(rule)

    def list_all(self) -> list[EarnRule]:
        return list(self._rules)


class InMemoryRedeemOptionStore:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        options = [
            RedeemOption(
                option_id="opt-cashback",
                option_type=RedeemOptionType.CASHBACK,
                points_required=Decimal("1000"),
                reward_value=Decimal("1.00"),
                description="1000 points = £1 cashback",
                active=True,
                created_at=now,
            ),
            RedeemOption(
                option_id="opt-fx-discount",
                option_type=RedeemOptionType.FX_DISCOUNT,
                points_required=Decimal("500"),
                reward_value=Decimal("0.001"),
                description="500 points = 0.1% FX fee discount",
                active=True,
                created_at=now,
            ),
            RedeemOption(
                option_id="opt-card-fee",
                option_type=RedeemOptionType.CARD_FEE_WAIVER,
                points_required=Decimal("2000"),
                reward_value=Decimal("5.00"),
                description="2000 points = 1-month card fee waiver",
                active=True,
                created_at=now,
            ),
            RedeemOption(
                option_id="opt-voucher",
                option_type=RedeemOptionType.VOUCHER,
                points_required=Decimal("5000"),
                reward_value=Decimal("5.00"),
                description="5000 points = £5 partner voucher",
                active=True,
                created_at=now,
            ),
        ]
        self._options: dict[str, RedeemOption] = {o.option_id: o for o in options}

    def list_active(self) -> list[RedeemOption]:
        return [o for o in self._options.values() if o.active]

    def get(self, option_id: str) -> RedeemOption | None:
        return self._options.get(option_id)

    def save(self, option: RedeemOption) -> None:
        self._options[option.option_id] = option


class InMemoryPointsTransactionStore:
    def __init__(self) -> None:
        self._txs: list[PointsTransaction] = []

    def append(self, tx: PointsTransaction) -> None:
        self._txs.append(tx)  # append-only (I-24)

    def list_by_customer(self, customer_id: str, limit: int = 100) -> list[PointsTransaction]:
        return [t for t in self._txs if t.customer_id == customer_id][-limit:]

    def list_expiring_before(self, dt: datetime) -> list[PointsTransaction]:
        return [
            t
            for t in self._txs
            if t.expires_at is not None
            and t.expires_at <= dt
            and t.tx_type == PointsTransactionType.EARN
        ]
