"""
services/treasury/models.py
IL-TLM-01 | Phase 17

Domain models, protocols, and in-memory stubs for Treasury & Liquidity Management.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

# ── Enums ────────────────────────────────────────────────────────────────────


class PoolStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class FundingSourceType(str, Enum):
    CREDIT_LINE = "CREDIT_LINE"
    INTERBANK = "INTERBANK"
    SHAREHOLDER_LOAN = "SHAREHOLDER_LOAN"
    REPO = "REPO"


class SweepDirection(str, Enum):
    SURPLUS_OUT = "SURPLUS_OUT"
    DEFICIT_IN = "DEFICIT_IN"


class ForecastHorizon(str, Enum):
    DAYS_7 = "DAYS_7"
    DAYS_14 = "DAYS_14"
    DAYS_30 = "DAYS_30"


class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    DISCREPANCY = "DISCREPANCY"
    PENDING = "PENDING"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LiquidityPool:
    id: str
    name: str
    currency: str
    current_balance: Decimal
    required_minimum: Decimal
    status: PoolStatus
    aspsp_account_id: str
    updated_at: datetime


@dataclass(frozen=True)
class CashPosition:
    id: str
    pool_id: str
    amount: Decimal
    currency: str
    value_date: datetime
    description: str
    is_client_money: bool


@dataclass(frozen=True)
class FundingSource:
    id: str
    name: str
    source_type: FundingSourceType
    available_amount: Decimal
    drawn_amount: Decimal
    interest_rate: Decimal
    currency: str
    maturity_date: datetime | None


@dataclass(frozen=True)
class SafeguardingAccount:
    id: str
    institution: str
    iban: str
    balance: Decimal
    client_money_held: Decimal
    currency: str
    last_reconciled_at: datetime


@dataclass(frozen=True)
class ForecastResult:
    id: str
    pool_id: str
    horizon: ForecastHorizon
    forecast_amount: Decimal
    confidence: Decimal
    generated_at: datetime
    model_version: str
    shortfall_risk: bool


@dataclass(frozen=True)
class SweepEvent:
    id: str
    pool_id: str
    direction: SweepDirection
    amount: Decimal
    currency: str
    executed_at: datetime | None
    proposed_at: datetime
    approved_by: str | None
    description: str


@dataclass(frozen=True)
class ReconciliationRecord:
    id: str
    account_id: str
    period_date: datetime
    book_balance: Decimal
    bank_balance: Decimal
    variance: Decimal
    status: ReconciliationStatus
    reconciled_at: datetime | None
    notes: str


# ── Protocols ─────────────────────────────────────────────────────────────────


@runtime_checkable
class LiquidityStorePort(Protocol):
    async def get_pool(self, pool_id: str) -> LiquidityPool | None: ...
    async def list_pools(self) -> list[LiquidityPool]: ...
    async def save_pool(self, pool: LiquidityPool) -> None: ...
    async def list_positions(self, pool_id: str) -> list[CashPosition]: ...
    async def add_position(self, pos: CashPosition) -> None: ...


@runtime_checkable
class ForecastStorePort(Protocol):
    async def save_forecast(self, f: ForecastResult) -> None: ...
    async def get_latest(self, pool_id: str, horizon: ForecastHorizon) -> ForecastResult | None: ...
    async def list_forecasts(self, pool_id: str) -> list[ForecastResult]: ...


@runtime_checkable
class SweepStorePort(Protocol):
    async def save_sweep(self, s: SweepEvent) -> None: ...
    async def list_sweeps(self, pool_id: str | None = None) -> list[SweepEvent]: ...
    async def approve_sweep(self, sweep_id: str, approved_by: str) -> SweepEvent: ...


@runtime_checkable
class ReconciliationStorePort(Protocol):
    async def save_record(self, r: ReconciliationRecord) -> None: ...
    async def list_records(self, account_id: str | None = None) -> list[ReconciliationRecord]: ...
    async def get_latest(self, account_id: str) -> ReconciliationRecord | None: ...


@runtime_checkable
class TreasuryAuditPort(Protocol):
    async def log(self, event_type: str, entity_id: str, details: dict, actor: str) -> None: ...
    async def list_events(self, entity_id: str | None = None) -> list[dict]: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryLiquidityStore:
    def __init__(self) -> None:
        self._pools: dict[str, LiquidityPool] = {}
        self._positions: list[CashPosition] = []

    async def get_pool(self, pool_id: str) -> LiquidityPool | None:
        return self._pools.get(pool_id)

    async def list_pools(self) -> list[LiquidityPool]:
        return list(self._pools.values())

    async def save_pool(self, pool: LiquidityPool) -> None:
        self._pools[pool.id] = pool

    async def list_positions(self, pool_id: str) -> list[CashPosition]:
        return [p for p in self._positions if p.pool_id == pool_id]

    async def add_position(self, pos: CashPosition) -> None:
        self._positions.append(pos)


class InMemoryForecastStore:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], list[ForecastResult]] = {}

    async def save_forecast(self, f: ForecastResult) -> None:
        key = (f.pool_id, f.horizon.value)
        self._store.setdefault(key, []).append(f)

    async def get_latest(self, pool_id: str, horizon: ForecastHorizon) -> ForecastResult | None:
        key = (pool_id, horizon.value)
        results = self._store.get(key, [])
        return results[-1] if results else None

    async def list_forecasts(self, pool_id: str) -> list[ForecastResult]:
        results: list[ForecastResult] = []
        for (pid, _), items in self._store.items():
            if pid == pool_id:
                results.extend(items)
        return results


class InMemorySweepStore:
    def __init__(self) -> None:
        self._sweeps: list[SweepEvent] = []

    async def save_sweep(self, s: SweepEvent) -> None:
        self._sweeps.append(s)

    async def list_sweeps(self, pool_id: str | None = None) -> list[SweepEvent]:
        if pool_id is None:
            return list(self._sweeps)
        return [s for s in self._sweeps if s.pool_id == pool_id]

    async def approve_sweep(self, sweep_id: str, approved_by: str) -> SweepEvent:
        for i, s in enumerate(self._sweeps):
            if s.id == sweep_id:
                updated = SweepEvent(
                    id=s.id,
                    pool_id=s.pool_id,
                    direction=s.direction,
                    amount=s.amount,
                    currency=s.currency,
                    executed_at=datetime.now(UTC),
                    proposed_at=s.proposed_at,
                    approved_by=approved_by,
                    description=s.description,
                )
                self._sweeps[i] = updated
                return updated
        raise KeyError(f"Sweep {sweep_id} not found")


class InMemoryReconciliationStore:
    def __init__(self) -> None:
        self._records: list[ReconciliationRecord] = []

    async def save_record(self, r: ReconciliationRecord) -> None:
        self._records.append(r)

    async def list_records(self, account_id: str | None = None) -> list[ReconciliationRecord]:
        if account_id is None:
            return list(self._records)
        return [r for r in self._records if r.account_id == account_id]

    async def get_latest(self, account_id: str) -> ReconciliationRecord | None:
        recs = [r for r in self._records if r.account_id == account_id]
        return recs[-1] if recs else None


class InMemoryTreasuryAudit:
    def __init__(self) -> None:
        self._events: list[dict] = []

    async def log(self, event_type: str, entity_id: str, details: dict, actor: str) -> None:
        self._events.append(
            {
                "event_type": event_type,
                "entity_id": entity_id,
                "details": details,
                "actor": actor,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def list_events(self, entity_id: str | None = None) -> list[dict]:
        if entity_id is None:
            return list(self._events)
        return [e for e in self._events if e["entity_id"] == entity_id]


# ── Seed Helper ────────────────────────────────────────────────────────────────


def make_sample_pool(pool_id: str = "pool-001") -> LiquidityPool:
    """Create a sample GBP liquidity pool for testing and seeding."""
    return LiquidityPool(
        id=pool_id,
        name="Primary GBP Pool",
        currency="GBP",
        current_balance=Decimal("2500000"),
        required_minimum=Decimal("500000"),
        status=PoolStatus.ACTIVE,
        aspsp_account_id="aspsp-acc-001",
        updated_at=datetime.now(UTC),
    )
