"""
services/merchant_acquiring/models.py
IL-MAG-01 | Phase 20

Domain models, protocols, and in-memory stubs for Merchant Acquiring Gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable
import uuid

# ── Enums ─────────────────────────────────────────────────────────────────────


class MerchantStatus(str, Enum):
    PENDING_KYB = "PENDING_KYB"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class MerchantRiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    PROHIBITED = "PROHIBITED"


class PaymentResult(str, Enum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    PENDING_3DS = "PENDING_3DS"


class DisputeStatus(str, Enum):
    RECEIVED = "RECEIVED"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    REPRESENTED = "REPRESENTED"
    RESOLVED_WIN = "RESOLVED_WIN"
    RESOLVED_LOSS = "RESOLVED_LOSS"


class SettlementStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChargebackReason(str, Enum):
    FRAUD = "FRAUD"
    ITEM_NOT_RECEIVED = "ITEM_NOT_RECEIVED"
    ITEM_NOT_AS_DESCRIBED = "ITEM_NOT_AS_DESCRIBED"
    DUPLICATE = "DUPLICATE"
    SUBSCRIPTION_CANCELLED = "SUBSCRIPTION_CANCELLED"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Merchant:
    id: str
    name: str
    legal_name: str
    mcc: str
    country: str
    website: str | None
    status: MerchantStatus
    risk_tier: MerchantRiskTier
    onboarded_at: datetime | None
    daily_limit: Decimal
    monthly_limit: Decimal


@dataclass(frozen=True)
class PaymentAcceptance:
    id: str
    merchant_id: str
    amount: Decimal
    currency: str
    result: PaymentResult
    card_last_four: str
    reference: str
    requires_3ds: bool
    created_at: datetime
    completed_at: datetime | None
    acquirer_ref: str | None


@dataclass(frozen=True)
class SettlementBatch:
    id: str
    merchant_id: str
    settlement_date: datetime
    gross_amount: Decimal
    fees: Decimal
    net_amount: Decimal
    payment_count: int
    status: SettlementStatus
    bank_reference: str | None


@dataclass(frozen=True)
class DisputeCase:
    id: str
    merchant_id: str
    payment_id: str
    amount: Decimal
    currency: str
    reason: ChargebackReason
    status: DisputeStatus
    received_at: datetime
    resolved_at: datetime | None
    evidence_submitted: bool


@dataclass(frozen=True)
class MerchantRiskScore:
    merchant_id: str
    computed_at: datetime
    chargeback_ratio: float
    volume_anomaly: float
    mcc_risk: float
    overall_score: float
    risk_tier: MerchantRiskTier


@dataclass(frozen=True)
class MAEventEntry:
    id: str
    merchant_id: str
    event_type: str
    details: dict
    actor: str
    created_at: datetime


# ── Protocols ─────────────────────────────────────────────────────────────────


@runtime_checkable
class MerchantStorePort(Protocol):
    async def save(self, merchant: Merchant) -> None: ...
    async def get(self, merchant_id: str) -> Merchant | None: ...
    async def list_all(self) -> list[Merchant]: ...


@runtime_checkable
class PaymentStorePort(Protocol):
    async def save(self, payment: PaymentAcceptance) -> None: ...
    async def get(self, payment_id: str) -> PaymentAcceptance | None: ...
    async def list_by_merchant(self, merchant_id: str) -> list[PaymentAcceptance]: ...


@runtime_checkable
class SettlementStorePort(Protocol):
    async def save(self, batch: SettlementBatch) -> None: ...
    async def get(self, batch_id: str) -> SettlementBatch | None: ...
    async def list_by_merchant(self, merchant_id: str) -> list[SettlementBatch]: ...
    async def get_latest(self, merchant_id: str) -> SettlementBatch | None: ...


@runtime_checkable
class DisputeStorePort(Protocol):
    async def save(self, dispute: DisputeCase) -> None: ...
    async def get(self, dispute_id: str) -> DisputeCase | None: ...
    async def list_by_merchant(self, merchant_id: str) -> list[DisputeCase]: ...


@runtime_checkable
class MAAuditPort(Protocol):
    async def log(
        self,
        event_type: str,
        merchant_id: str,
        actor: str,
        details: dict,
    ) -> None: ...

    async def list_events(self, merchant_id: str | None = None) -> list[dict]: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────────


class InMemoryMerchantStore:
    """In-memory stub for MerchantStorePort."""

    def __init__(self) -> None:
        self._data: dict[str, Merchant] = {}

    async def save(self, merchant: Merchant) -> None:
        self._data[merchant.id] = merchant

    async def get(self, merchant_id: str) -> Merchant | None:
        return self._data.get(merchant_id)

    async def list_all(self) -> list[Merchant]:
        return list(self._data.values())


class InMemoryPaymentStore:
    """In-memory stub for PaymentStorePort."""

    def __init__(self) -> None:
        self._data: dict[str, PaymentAcceptance] = {}

    async def save(self, payment: PaymentAcceptance) -> None:
        self._data[payment.id] = payment

    async def get(self, payment_id: str) -> PaymentAcceptance | None:
        return self._data.get(payment_id)

    async def list_by_merchant(self, merchant_id: str) -> list[PaymentAcceptance]:
        return [p for p in self._data.values() if p.merchant_id == merchant_id]


class InMemorySettlementStore:
    """In-memory stub for SettlementStorePort."""

    def __init__(self) -> None:
        self._data: dict[str, SettlementBatch] = {}

    async def save(self, batch: SettlementBatch) -> None:
        self._data[batch.id] = batch

    async def get(self, batch_id: str) -> SettlementBatch | None:
        return self._data.get(batch_id)

    async def list_by_merchant(self, merchant_id: str) -> list[SettlementBatch]:
        return [b for b in self._data.values() if b.merchant_id == merchant_id]

    async def get_latest(self, merchant_id: str) -> SettlementBatch | None:
        batches = [b for b in self._data.values() if b.merchant_id == merchant_id]
        if not batches:
            return None
        return max(batches, key=lambda b: b.settlement_date)


class InMemoryDisputeStore:
    """In-memory stub for DisputeStorePort."""

    def __init__(self) -> None:
        self._data: dict[str, DisputeCase] = {}

    async def save(self, dispute: DisputeCase) -> None:
        self._data[dispute.id] = dispute

    async def get(self, dispute_id: str) -> DisputeCase | None:
        return self._data.get(dispute_id)

    async def list_by_merchant(self, merchant_id: str) -> list[DisputeCase]:
        return [d for d in self._data.values() if d.merchant_id == merchant_id]


class InMemoryMAAudit:
    """In-memory stub for MAAuditPort."""

    def __init__(self) -> None:
        self._events: list[MAEventEntry] = []

    async def log(
        self,
        event_type: str,
        merchant_id: str,
        actor: str,
        details: dict,
    ) -> None:
        entry = MAEventEntry(
            id=str(uuid.uuid4()),
            merchant_id=merchant_id,
            event_type=event_type,
            details=details,
            actor=actor,
            created_at=datetime.now(UTC),
        )
        self._events.append(entry)

    async def list_events(self, merchant_id: str | None = None) -> list[dict]:
        events = (
            self._events
            if merchant_id is None
            else [e for e in self._events if e.merchant_id == merchant_id]
        )
        return [
            {
                "id": e.id,
                "merchant_id": e.merchant_id,
                "event_type": e.event_type,
                "details": e.details,
                "actor": e.actor,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
