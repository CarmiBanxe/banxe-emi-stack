"""
services/referral/models.py — Referral Program domain models
IL-REF-01 | Phase 30 | banxe-emi-stack

Domain models, enums, protocols, and InMemory stubs for the referral program.
Protocol DI pattern throughout. Frozen dataclasses with dataclasses.replace() for mutations.
Invariants: I-01 (Decimal reward amounts), I-05 (amounts as strings), I-24 (append-only audit),
I-27 (HITL for fraud-blocked referrals).
FCA: COBS 4 (financial promotions), PS22/9 (fair value), BCOBS 2.2 (communications).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


class ReferralStatus(str, Enum):
    INVITED = "INVITED"
    REGISTERED = "REGISTERED"
    KYC_COMPLETE = "KYC_COMPLETE"
    QUALIFIED = "QUALIFIED"
    REWARDED = "REWARDED"
    FRAUDULENT = "FRAUDULENT"


class RewardStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"
    REJECTED = "REJECTED"


class CampaignStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class FraudReason(str, Enum):
    SELF_REFERRAL = "SELF_REFERRAL"
    VELOCITY_ABUSE = "VELOCITY_ABUSE"
    SAME_IP = "SAME_IP"
    SAME_DEVICE = "SAME_DEVICE"
    DUPLICATE_ACCOUNT = "DUPLICATE_ACCOUNT"


# ── Frozen dataclasses ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReferralCode:
    code_id: str
    customer_id: str
    code: str
    campaign_id: str
    created_at: datetime
    used_count: int = 0
    max_uses: int = 100
    is_vanity: bool = False


@dataclass(frozen=True)
class Referral:
    referral_id: str
    referrer_id: str
    referee_id: str
    code: str
    campaign_id: str
    status: ReferralStatus
    created_at: datetime
    qualified_at: datetime | None = None
    rewarded_at: datetime | None = None


@dataclass(frozen=True)
class ReferralReward:
    reward_id: str
    referral_id: str
    recipient_id: str
    amount: Decimal  # I-01: Decimal, never float
    reward_type: str
    status: RewardStatus
    created_at: datetime
    paid_at: datetime | None = None


@dataclass(frozen=True)
class ReferralCampaign:
    campaign_id: str
    name: str
    referrer_reward: Decimal
    referee_reward: Decimal
    total_budget: Decimal
    spent_budget: Decimal
    status: CampaignStatus
    start_date: datetime
    created_at: datetime
    end_date: datetime | None = None


@dataclass(frozen=True)
class FraudCheck:
    check_id: str
    referral_id: str
    fraud_reason: FraudReason | None
    is_fraudulent: bool
    confidence_score: Decimal
    checked_at: datetime


# ── Protocols (DI ports) ──────────────────────────────────────────────────


class ReferralCodeStorePort(Protocol):
    def save(self, code: ReferralCode) -> None: ...
    def get_by_code(self, code_str: str) -> ReferralCode | None: ...
    def get_by_customer(self, customer_id: str) -> list[ReferralCode]: ...
    def update(self, code: ReferralCode) -> None: ...


class ReferralStorePort(Protocol):
    def save(self, ref: Referral) -> None: ...
    def get(self, referral_id: str) -> Referral | None: ...
    def list_by_referrer(self, referrer_id: str) -> list[Referral]: ...
    def list_by_referee(self, referee_id: str) -> list[Referral]: ...
    def update(self, ref: Referral) -> None: ...


class ReferralRewardStorePort(Protocol):
    def save(self, reward: ReferralReward) -> None: ...
    def list_by_referral(self, referral_id: str) -> list[ReferralReward]: ...
    def list_by_recipient(self, recipient_id: str) -> list[ReferralReward]: ...
    def get(self, reward_id: str) -> ReferralReward | None: ...
    def update(self, reward: ReferralReward) -> None: ...


class ReferralCampaignStorePort(Protocol):
    def save(self, campaign: ReferralCampaign) -> None: ...
    def get(self, campaign_id: str) -> ReferralCampaign | None: ...
    def list_active(self) -> list[ReferralCampaign]: ...
    def update(self, campaign: ReferralCampaign) -> None: ...


class FraudCheckStorePort(Protocol):
    def save(self, check: FraudCheck) -> None: ...
    def get_by_referral(self, referral_id: str) -> FraudCheck | None: ...
    def list_recent_by_ip(self, ip: str, hours: int) -> list[FraudCheck]: ...


# ── InMemory stubs ────────────────────────────────────────────────────────

_DEFAULT_CAMPAIGN_ID = "camp-default"


class InMemoryReferralCodeStore:
    def __init__(self) -> None:
        self._by_code: dict[str, ReferralCode] = {}
        self._by_customer: dict[str, list[ReferralCode]] = {}

    def save(self, code: ReferralCode) -> None:
        self._by_code[code.code] = code
        self._by_customer.setdefault(code.customer_id, []).append(code)

    def get_by_code(self, code_str: str) -> ReferralCode | None:
        return self._by_code.get(code_str)

    def get_by_customer(self, customer_id: str) -> list[ReferralCode]:
        return self._by_customer.get(customer_id, [])

    def update(self, code: ReferralCode) -> None:
        self._by_code[code.code] = code
        cust_list = self._by_customer.get(code.customer_id, [])
        self._by_customer[code.customer_id] = [
            c if c.code_id != code.code_id else code for c in cust_list
        ]


class InMemoryReferralStore:
    def __init__(self) -> None:
        self._store: dict[str, Referral] = {}

    def save(self, ref: Referral) -> None:
        self._store[ref.referral_id] = ref

    def get(self, referral_id: str) -> Referral | None:
        return self._store.get(referral_id)

    def list_by_referrer(self, referrer_id: str) -> list[Referral]:
        return [r for r in self._store.values() if r.referrer_id == referrer_id]

    def list_by_referee(self, referee_id: str) -> list[Referral]:
        return [r for r in self._store.values() if r.referee_id == referee_id]

    def update(self, ref: Referral) -> None:
        self._store[ref.referral_id] = ref


class InMemoryReferralRewardStore:
    def __init__(self) -> None:
        self._store: dict[str, ReferralReward] = {}

    def save(self, reward: ReferralReward) -> None:
        self._store[reward.reward_id] = reward

    def list_by_referral(self, referral_id: str) -> list[ReferralReward]:
        return [r for r in self._store.values() if r.referral_id == referral_id]

    def list_by_recipient(self, recipient_id: str) -> list[ReferralReward]:
        return [r for r in self._store.values() if r.recipient_id == recipient_id]

    def get(self, reward_id: str) -> ReferralReward | None:
        return self._store.get(reward_id)

    def update(self, reward: ReferralReward) -> None:
        self._store[reward.reward_id] = reward


class InMemoryReferralCampaignStore:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        default = ReferralCampaign(
            campaign_id=_DEFAULT_CAMPAIGN_ID,
            name="Standard Referral",
            referrer_reward=Decimal("25.00"),
            referee_reward=Decimal("10.00"),
            total_budget=Decimal("100000.00"),
            spent_budget=Decimal("0"),
            status=CampaignStatus.ACTIVE,
            start_date=now,
            created_at=now,
        )
        self._store: dict[str, ReferralCampaign] = {default.campaign_id: default}

    def save(self, campaign: ReferralCampaign) -> None:
        self._store[campaign.campaign_id] = campaign

    def get(self, campaign_id: str) -> ReferralCampaign | None:
        return self._store.get(campaign_id)

    def list_active(self) -> list[ReferralCampaign]:
        return [c for c in self._store.values() if c.status == CampaignStatus.ACTIVE]

    def update(self, campaign: ReferralCampaign) -> None:
        self._store[campaign.campaign_id] = campaign


class InMemoryFraudCheckStore:
    def __init__(self) -> None:
        self._checks: list[FraudCheck] = []

    def save(self, check: FraudCheck) -> None:
        self._checks.append(check)  # append-only (I-24)

    def get_by_referral(self, referral_id: str) -> FraudCheck | None:
        matches = [c for c in self._checks if c.referral_id == referral_id]
        return matches[-1] if matches else None

    def list_recent_by_ip(self, ip: str, hours: int) -> list[FraudCheck]:
        # In stub: return all checks (no IP stored in FraudCheck — IP check via context)
        # This is intentionally simplified for InMemory stub
        return []
