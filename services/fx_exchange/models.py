"""
services/fx_exchange/models.py
IL-FX-01 | Phase 21

Domain models, enums, protocols, and InMemory stubs for FX & Currency Exchange.
Amounts always Decimal (I-01). API layer uses strings (I-05).
Append-only audit trail (I-24). HITL for large FX >£50k (I-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

# ── Enums ─────────────────────────────────────────────────────────────────────


class RateSource(str, Enum):
    ECB = "ECB"
    FRANKFURTER = "FRANKFURTER"
    FALLBACK = "FALLBACK"


class FXOrderStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class FXOrderType(str, Enum):
    SPOT = "SPOT"
    FORWARD = "FORWARD"


class ComplianceFlag(str, Enum):
    CLEAR = "CLEAR"
    EDD_REQUIRED = "EDD_REQUIRED"
    BLOCKED = "BLOCKED"


# ── Frozen dataclasses ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CurrencyPair:
    base: str
    quote: str

    def __str__(self) -> str:
        return f"{self.base}/{self.quote}"


@dataclass(frozen=True)
class FXQuote:
    quote_id: str
    pair: CurrencyPair
    rate: Decimal
    bid: Decimal
    ask: Decimal
    spread_bps: int
    source: RateSource
    valid_until: datetime
    created_at: datetime


@dataclass(frozen=True)
class FXOrder:
    order_id: str
    entity_id: str
    pair: CurrencyPair
    amount_base: Decimal
    amount_quote: Decimal
    rate: Decimal
    order_type: FXOrderType
    status: FXOrderStatus
    compliance_flag: ComplianceFlag
    created_at: datetime
    executed_at: datetime | None = None


@dataclass(frozen=True)
class FXExecution:
    execution_id: str
    order_id: str
    debit_account: str
    credit_account: str
    debit_amount: Decimal
    credit_amount: Decimal
    rate: Decimal
    fee: Decimal
    created_at: datetime


@dataclass(frozen=True)
class SpreadConfig:
    pair: CurrencyPair
    base_spread_bps: int
    min_spread_bps: int
    vip_spread_bps: int
    tier_volume_threshold: Decimal


@dataclass(frozen=True)
class RateSnapshot:
    pair: CurrencyPair
    rate: Decimal
    source: RateSource
    timestamp: datetime


# ── Protocols (runtime_checkable) ─────────────────────────────────────────────


@runtime_checkable
class RateStorePort(Protocol):
    async def save_rate(self, snapshot: RateSnapshot) -> None: ...

    async def get_latest_rate(self, pair: CurrencyPair) -> RateSnapshot | None: ...

    async def get_rate_history(self, pair: CurrencyPair, limit: int = 50) -> list[RateSnapshot]: ...


@runtime_checkable
class QuoteStorePort(Protocol):
    async def save_quote(self, quote: FXQuote) -> None: ...

    async def get_quote(self, quote_id: str) -> FXQuote | None: ...


@runtime_checkable
class OrderStorePort(Protocol):
    async def save_order(self, order: FXOrder) -> None: ...

    async def get_order(self, order_id: str) -> FXOrder | None: ...

    async def list_orders(self, entity_id: str) -> list[FXOrder]: ...


@runtime_checkable
class ExecutionStorePort(Protocol):
    async def save_execution(self, execution: FXExecution) -> None: ...

    async def list_executions(self, entity_id: str) -> list[FXExecution]: ...


@runtime_checkable
class FXAuditPort(Protocol):
    async def log_event(self, event_type: str, payload: dict) -> None: ...

    async def list_events(self, entity_id: str | None = None) -> list[dict]: ...


# ── InMemory stubs ─────────────────────────────────────────────────────────────


class InMemoryRateStore:
    """In-memory stub for RateStorePort — test isolation only."""

    def __init__(self) -> None:
        self._latest: dict[str, RateSnapshot] = {}
        self._history: dict[str, list[RateSnapshot]] = {}

    async def save_rate(self, snapshot: RateSnapshot) -> None:
        key = str(snapshot.pair)
        self._latest[key] = snapshot
        self._history.setdefault(key, []).append(snapshot)

    async def get_latest_rate(self, pair: CurrencyPair) -> RateSnapshot | None:
        return self._latest.get(str(pair))

    async def get_rate_history(self, pair: CurrencyPair, limit: int = 50) -> list[RateSnapshot]:
        history = self._history.get(str(pair), [])
        return history[-limit:]


class InMemoryQuoteStore:
    """In-memory stub for QuoteStorePort — test isolation only."""

    def __init__(self) -> None:
        self._quotes: dict[str, FXQuote] = {}

    async def save_quote(self, quote: FXQuote) -> None:
        self._quotes[quote.quote_id] = quote

    async def get_quote(self, quote_id: str) -> FXQuote | None:
        return self._quotes.get(quote_id)


class InMemoryOrderStore:
    """In-memory stub for OrderStorePort — test isolation only."""

    def __init__(self) -> None:
        self._orders: dict[str, FXOrder] = {}

    async def save_order(self, order: FXOrder) -> None:
        self._orders[order.order_id] = order

    async def get_order(self, order_id: str) -> FXOrder | None:
        return self._orders.get(order_id)

    async def list_orders(self, entity_id: str) -> list[FXOrder]:
        return [o for o in self._orders.values() if o.entity_id == entity_id]


class InMemoryExecutionStore:
    """In-memory stub for ExecutionStorePort — test isolation only."""

    def __init__(self) -> None:
        self._executions: list[FXExecution] = []
        self._by_order: dict[str, FXExecution] = {}

    async def save_execution(self, execution: FXExecution) -> None:
        self._executions.append(execution)
        self._by_order[execution.order_id] = execution

    async def list_executions(self, entity_id: str) -> list[FXExecution]:
        # Return all executions (entity lookup via order_id cross-ref handled by agent)
        return list(self._executions)


class InMemoryFXAudit:
    """In-memory stub for FXAuditPort — append-only (I-24)."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    async def log_event(self, event_type: str, payload: dict) -> None:
        self._events.append(
            {
                "event_type": event_type,
                "payload": payload,
                "logged_at": datetime.now(UTC).isoformat(),
            }
        )

    async def list_events(self, entity_id: str | None = None) -> list[dict]:
        if entity_id is None:
            return list(self._events)
        return [e for e in self._events if e.get("payload", {}).get("entity_id") == entity_id]


# ── Seed data ─────────────────────────────────────────────────────────────────

_SUPPORTED_PAIRS: list[CurrencyPair] = [
    CurrencyPair("GBP", "EUR"),
    CurrencyPair("GBP", "USD"),
    CurrencyPair("GBP", "CHF"),
    CurrencyPair("GBP", "PLN"),
    CurrencyPair("GBP", "CZK"),
    CurrencyPair("EUR", "USD"),
]

# Major pairs: GBP/EUR, GBP/USD, GBP/CHF, EUR/USD — base_spread_bps=20
# Exotic pairs: GBP/PLN, GBP/CZK — base_spread_bps=50
_DEFAULT_SPREADS: dict[str, SpreadConfig] = {
    "GBP/EUR": SpreadConfig(
        pair=CurrencyPair("GBP", "EUR"),
        base_spread_bps=20,
        min_spread_bps=8,
        vip_spread_bps=10,
        tier_volume_threshold=Decimal("100000"),
    ),
    "GBP/USD": SpreadConfig(
        pair=CurrencyPair("GBP", "USD"),
        base_spread_bps=20,
        min_spread_bps=8,
        vip_spread_bps=10,
        tier_volume_threshold=Decimal("100000"),
    ),
    "GBP/CHF": SpreadConfig(
        pair=CurrencyPair("GBP", "CHF"),
        base_spread_bps=20,
        min_spread_bps=8,
        vip_spread_bps=10,
        tier_volume_threshold=Decimal("100000"),
    ),
    "EUR/USD": SpreadConfig(
        pair=CurrencyPair("EUR", "USD"),
        base_spread_bps=20,
        min_spread_bps=8,
        vip_spread_bps=10,
        tier_volume_threshold=Decimal("100000"),
    ),
    "GBP/PLN": SpreadConfig(
        pair=CurrencyPair("GBP", "PLN"),
        base_spread_bps=50,
        min_spread_bps=20,
        vip_spread_bps=25,
        tier_volume_threshold=Decimal("200000"),
    ),
    "GBP/CZK": SpreadConfig(
        pair=CurrencyPair("GBP", "CZK"),
        base_spread_bps=50,
        min_spread_bps=20,
        vip_spread_bps=25,
        tier_volume_threshold=Decimal("200000"),
    ),
}

# ── Helpers ────────────────────────────────────────────────────────────────────

_DEFAULT_SPREAD_BPS: int = 30


def get_default_spread_config(pair: CurrencyPair) -> SpreadConfig:
    """Return default SpreadConfig for unknown pairs."""
    return SpreadConfig(
        pair=pair,
        base_spread_bps=_DEFAULT_SPREAD_BPS,
        min_spread_bps=15,
        vip_spread_bps=15,
        tier_volume_threshold=Decimal("100000"),
    )
