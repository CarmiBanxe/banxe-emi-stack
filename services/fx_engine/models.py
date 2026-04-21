"""
services/fx_engine/models.py
FX Engine — Domain Models
IL-FXE-01 | Sprint 34 | Phase 48

FCA: PS22/9, EMIR, MLR 2017 Reg.28, FCA COBS 14.3
Trust Zone: AMBER

Pydantic v2 models (I-01). TTL ≤30s validator.
All amounts Decimal (I-22). UTC timestamps (I-23).
Append-only stores (I-24).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, field_validator


class QuoteStatus(StrEnum):
    """FX quote lifecycle status (I-02 UPPER_SNAKE)."""

    ACTIVE = "ACTIVE"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class ExecutionStatus(StrEnum):
    """FX execution status (I-02 UPPER_SNAKE)."""

    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class FXRateType(StrEnum):
    """FX rate type (I-02 UPPER_SNAKE)."""

    SPOT = "SPOT"
    FORWARD = "FORWARD"
    SWAP = "SWAP"


class RiskTier(StrEnum):
    """Risk tier classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FXRate(BaseModel):
    """FX rate model (pydantic v2, I-01).

    Bid/ask/mid all Decimal (I-22). UTC timestamps (I-23).
    Staleness tracked via is_stale flag.
    """

    rate_id: str
    currency_pair: str  # e.g. "GBP/EUR"
    base_currency: str
    quote_currency: str
    bid: Decimal  # I-22
    ask: Decimal  # I-22
    mid: Decimal  # I-22
    rate_type: FXRateType = FXRateType.SPOT
    timestamp: str  # I-23 UTC
    provider: str = "internal"
    is_stale: bool = False


class FXQuote(BaseModel):
    """FX quote model (pydantic v2, I-01).

    TTL hard-capped at 30 seconds via validator.
    All amounts Decimal (I-22). UTC timestamps (I-23).
    """

    quote_id: str
    currency_pair: str
    sell_amount: Decimal  # I-22
    sell_currency: str
    buy_amount: Decimal  # I-22
    buy_currency: str
    rate: Decimal  # I-22
    spread: Decimal  # I-22
    ttl_seconds: int = 30
    status: QuoteStatus = QuoteStatus.ACTIVE
    created_at: str  # I-23 UTC
    expires_at: str  # I-23 UTC
    tenant_id: str = "default"

    @field_validator("ttl_seconds")
    @classmethod
    def max_ttl(cls, v: int) -> int:
        """Enforce FX quote TTL ≤30 seconds (FCA COBS 14.3)."""
        if v > 30:
            raise ValueError("FX quote TTL must be ≤30 seconds")
        return v


class FXExecution(BaseModel):
    """FX execution record (pydantic v2, I-01).

    Append-only (I-24). UTC timestamps (I-23).
    """

    execution_id: str
    quote_id: str
    status: ExecutionStatus
    executed_at: str | None = None
    settlement_date: str | None = None
    confirmation_ref: str | None = None
    rejection_reason: str | None = None


class HedgePosition(BaseModel):
    """Hedge position snapshot (pydantic v2, I-01).

    Append-only (I-24). All amounts Decimal (I-22).
    UTC timestamps (I-23).
    """

    position_id: str
    currency_pair: str
    net_long: Decimal  # I-22
    net_short: Decimal  # I-22
    net_exposure: Decimal  # I-22
    snapshot_date: str  # I-23


@dataclass
class HITLProposal:
    """HITL L4 escalation proposal for FX operations.

    Executions >= £10k require TREASURY_OPS approval (I-04, I-27).
    """

    action: str
    quote_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


# ── Protocols (Protocol DI) ─────────────────────────────────────────────────


class RateStore(Protocol):
    """Protocol for FX rate persistence."""

    def save(self, rate: FXRate) -> None: ...

    def get_latest(self, currency_pair: str) -> FXRate | None: ...

    def get_all(self) -> list[FXRate]: ...


class QuoteStore(Protocol):
    """Protocol for FX quote persistence."""

    def save(self, quote: FXQuote) -> None: ...

    def get(self, quote_id: str) -> FXQuote | None: ...

    def list_active(self) -> list[FXQuote]: ...


class ExecutionStore(Protocol):
    """Protocol for FX execution persistence (append-only, I-24)."""

    def append(self, execution: FXExecution) -> None: ...  # I-24

    def get(self, execution_id: str) -> FXExecution | None: ...

    def list_by_quote(self, quote_id: str) -> list[FXExecution]: ...


class HedgeStore(Protocol):
    """Protocol for hedge position persistence (append-only, I-24)."""

    def append(self, position: HedgePosition) -> None: ...  # I-24

    def get_latest(self, currency_pair: str) -> HedgePosition | None: ...


# ── InMemory stubs with seeded rates ────────────────────────────────────────


class InMemoryRateStore:
    """In-memory FX rate store with 3 seeded rates."""

    def __init__(self) -> None:
        """Initialise with seeded rates: GBP/EUR, GBP/USD, EUR/USD."""
        ts = datetime.now(UTC).isoformat()
        self._data: dict[str, FXRate] = {
            "GBP/EUR": FXRate(
                rate_id="r_001",
                currency_pair="GBP/EUR",
                base_currency="GBP",
                quote_currency="EUR",
                bid=Decimal("1.1650"),
                ask=Decimal("1.1680"),
                mid=Decimal("1.1665"),
                timestamp=ts,
            ),
            "GBP/USD": FXRate(
                rate_id="r_002",
                currency_pair="GBP/USD",
                base_currency="GBP",
                quote_currency="USD",
                bid=Decimal("1.2680"),
                ask=Decimal("1.2710"),
                mid=Decimal("1.2695"),
                timestamp=ts,
            ),
            "EUR/USD": FXRate(
                rate_id="r_003",
                currency_pair="EUR/USD",
                base_currency="EUR",
                quote_currency="USD",
                bid=Decimal("1.0870"),
                ask=Decimal("1.0890"),
                mid=Decimal("1.0880"),
                timestamp=ts,
            ),
        }

    def save(self, rate: FXRate) -> None:
        """Save or update an FX rate."""
        self._data[rate.currency_pair] = rate

    def get_latest(self, currency_pair: str) -> FXRate | None:
        """Get latest rate for a currency pair."""
        return self._data.get(currency_pair)

    def get_all(self) -> list[FXRate]:
        """Get all stored FX rates."""
        return list(self._data.values())


class InMemoryQuoteStore:
    """In-memory FX quote store."""

    def __init__(self) -> None:
        """Initialise empty quote store."""
        self._data: dict[str, FXQuote] = {}

    def save(self, quote: FXQuote) -> None:
        """Save or update an FX quote."""
        self._data[quote.quote_id] = quote

    def get(self, quote_id: str) -> FXQuote | None:
        """Retrieve an FX quote by ID."""
        return self._data.get(quote_id)

    def list_active(self) -> list[FXQuote]:
        """List all active FX quotes."""
        return [q for q in self._data.values() if q.status == QuoteStatus.ACTIVE]


class InMemoryExecutionStore:
    """In-memory FX execution store (append-only, I-24)."""

    def __init__(self) -> None:
        """Initialise empty append-only execution log."""
        self._log: list[FXExecution] = []

    def append(self, execution: FXExecution) -> None:  # I-24
        """Append execution record (never update/delete)."""
        self._log.append(execution)

    def get(self, execution_id: str) -> FXExecution | None:
        """Retrieve execution by ID."""
        return next((e for e in self._log if e.execution_id == execution_id), None)

    def list_by_quote(self, quote_id: str) -> list[FXExecution]:
        """List executions for a quote."""
        return [e for e in self._log if e.quote_id == quote_id]


class InMemoryHedgeStore:
    """In-memory hedge position store (append-only, I-24)."""

    def __init__(self) -> None:
        """Initialise empty append-only hedge log."""
        self._log: list[HedgePosition] = []

    def append(self, position: HedgePosition) -> None:  # I-24
        """Append hedge position snapshot (never update/delete)."""
        self._log.append(position)

    def get_latest(self, currency_pair: str) -> HedgePosition | None:
        """Get most recent hedge position for a currency pair."""
        matches = [p for p in self._log if p.currency_pair == currency_pair]
        return matches[-1] if matches else None
