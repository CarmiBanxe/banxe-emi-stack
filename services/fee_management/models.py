"""
services/fee_management/models.py
IL-FME-01 | Phase 41 | banxe-emi-stack

Domain models, protocols, and in-memory stubs for Fee Management Engine.
Protocol DI: Port (Protocol) → InMemory stub (tests) → Real adapter (production)
I-01: All monetary values as Decimal — NEVER float.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

# ── Enums ────────────────────────────────────────────────────────────────────


class FeeType(str, Enum):
    TRANSACTION = "TRANSACTION"
    MAINTENANCE = "MAINTENANCE"
    FX_MARKUP = "FX_MARKUP"
    WITHDRAWAL = "WITHDRAWAL"
    PENALTY = "PENALTY"
    CUSTOM = "CUSTOM"


class FeeStatus(str, Enum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    WAIVED = "WAIVED"
    REFUNDED = "REFUNDED"


class BillingCycle(str, Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"
    ON_DEMAND = "ON_DEMAND"


class WaiverReason(str, Enum):
    GOODWILL = "GOODWILL"
    PROMOTION = "PROMOTION"
    ERROR_CORRECTION = "ERROR_CORRECTION"
    VIP_TIER = "VIP_TIER"
    REGULATORY = "REGULATORY"


class FeeCategory(str, Enum):
    ACCOUNT = "ACCOUNT"
    PAYMENTS = "PAYMENTS"
    FX = "FX"
    CARDS = "CARDS"
    OTHER = "OTHER"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeeRule:
    id: str
    name: str
    fee_type: FeeType
    category: FeeCategory
    amount: Decimal
    percentage: Decimal | None
    min_amount: Decimal
    max_amount: Decimal | None
    billing_cycle: BillingCycle
    active: bool
    created_at: datetime


@dataclass(frozen=True)
class FeeCharge:
    id: str
    rule_id: str
    account_id: str
    amount: Decimal
    status: FeeStatus
    description: str
    reference: str
    applied_at: datetime
    paid_at: datetime | None = None


@dataclass(frozen=True)
class FeeWaiver:
    id: str
    charge_id: str
    account_id: str
    reason: WaiverReason
    amount_waived: Decimal
    requested_by: str
    status: str
    created_at: datetime
    approved_by: str | None = None
    resolved_at: datetime | None = None


@dataclass(frozen=True)
class FeeSummary:
    account_id: str
    period_start: datetime
    period_end: datetime
    total_charged: Decimal
    total_waived: Decimal
    total_paid: Decimal
    outstanding: Decimal
    breakdown: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class FeeSchedule:
    id: str
    name: str
    rules: list[str]
    effective_from: datetime
    tier: str
    description: str
    effective_to: datetime | None = None


# ── Protocols ────────────────────────────────────────────────────────────────


class FeeRuleStore(Protocol):
    def get_rule(self, id: str) -> FeeRule | None: ...
    def list_rules(self, active_only: bool = True) -> list[FeeRule]: ...
    def save_rule(self, r: FeeRule) -> None: ...


class FeeChargeStore(Protocol):
    def save_charge(self, c: FeeCharge) -> None: ...
    def get_charge(self, id: str) -> FeeCharge | None: ...
    def list_charges(self, account_id: str) -> list[FeeCharge]: ...


class FeeWaiverStore(Protocol):
    def save_waiver(self, w: FeeWaiver) -> None: ...
    def get_waiver(self, id: str) -> FeeWaiver | None: ...
    def list_waivers(self, account_id: str) -> list[FeeWaiver]: ...


class FeeScheduleStore(Protocol):
    def save_schedule(self, s: FeeSchedule) -> None: ...
    def get_schedule(self, id: str) -> FeeSchedule | None: ...
    def list_schedules(self) -> list[FeeSchedule]: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryFeeRuleStore:
    def __init__(self) -> None:
        self._rules: dict[str, FeeRule] = {}
        self._seed()

    def _seed(self) -> None:
        now = datetime.now(UTC)
        seed_rules = [
            FeeRule(
                id="rule-maintenance-001",
                name="Monthly Account Maintenance",
                fee_type=FeeType.MAINTENANCE,
                category=FeeCategory.ACCOUNT,
                amount=Decimal("4.99"),
                percentage=None,
                min_amount=Decimal("4.99"),
                max_amount=None,
                billing_cycle=BillingCycle.MONTHLY,
                active=True,
                created_at=now,
            ),
            FeeRule(
                id="rule-atm-withdrawal-001",
                name="ATM Withdrawal Fee",
                fee_type=FeeType.WITHDRAWAL,
                category=FeeCategory.CARDS,
                amount=Decimal("1.50"),
                percentage=None,
                min_amount=Decimal("1.50"),
                max_amount=None,
                billing_cycle=BillingCycle.ON_DEMAND,
                active=True,
                created_at=now,
            ),
            FeeRule(
                id="rule-fx-markup-001",
                name="FX Markup Fee",
                fee_type=FeeType.FX_MARKUP,
                category=FeeCategory.FX,
                amount=Decimal("0"),
                percentage=Decimal("0.005"),
                min_amount=Decimal("0.01"),
                max_amount=None,
                billing_cycle=BillingCycle.ON_DEMAND,
                active=True,
                created_at=now,
            ),
            FeeRule(
                id="rule-swift-001",
                name="SWIFT Transaction Fee",
                fee_type=FeeType.TRANSACTION,
                category=FeeCategory.PAYMENTS,
                amount=Decimal("25.00"),
                percentage=None,
                min_amount=Decimal("25.00"),
                max_amount=None,
                billing_cycle=BillingCycle.ON_DEMAND,
                active=True,
                created_at=now,
            ),
            FeeRule(
                id="rule-card-replacement-001",
                name="Card Replacement Penalty",
                fee_type=FeeType.PENALTY,
                category=FeeCategory.CARDS,
                amount=Decimal("10.00"),
                percentage=None,
                min_amount=Decimal("10.00"),
                max_amount=None,
                billing_cycle=BillingCycle.ON_DEMAND,
                active=True,
                created_at=now,
            ),
        ]
        for rule in seed_rules:
            self._rules[rule.id] = rule

    def get_rule(self, id: str) -> FeeRule | None:
        return self._rules.get(id)

    def list_rules(self, active_only: bool = True) -> list[FeeRule]:
        if active_only:
            return [r for r in self._rules.values() if r.active]
        return list(self._rules.values())

    def save_rule(self, r: FeeRule) -> None:
        self._rules[r.id] = r


class InMemoryFeeChargeStore:
    def __init__(self) -> None:
        self._charges: dict[str, FeeCharge] = {}

    def save_charge(self, c: FeeCharge) -> None:
        self._charges[c.id] = c

    def get_charge(self, id: str) -> FeeCharge | None:
        return self._charges.get(id)

    def list_charges(self, account_id: str) -> list[FeeCharge]:
        return [c for c in self._charges.values() if c.account_id == account_id]


class InMemoryFeeWaiverStore:
    def __init__(self) -> None:
        self._waivers: dict[str, FeeWaiver] = {}

    def save_waiver(self, w: FeeWaiver) -> None:
        self._waivers[w.id] = w

    def get_waiver(self, id: str) -> FeeWaiver | None:
        return self._waivers.get(id)

    def list_waivers(self, account_id: str) -> list[FeeWaiver]:
        return [w for w in self._waivers.values() if w.account_id == account_id]


class InMemoryFeeScheduleStore:
    def __init__(self) -> None:
        self._schedules: dict[str, FeeSchedule] = {}

    def save_schedule(self, s: FeeSchedule) -> None:
        self._schedules[s.id] = s

    def get_schedule(self, id: str) -> FeeSchedule | None:
        return self._schedules.get(id)

    def list_schedules(self) -> list[FeeSchedule]:
        return list(self._schedules.values())
