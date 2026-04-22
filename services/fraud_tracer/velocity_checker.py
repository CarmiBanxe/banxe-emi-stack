"""
services/fraud_tracer/velocity_checker.py
Redis-backed velocity checks for fraud detection (IL-TRC-01).
I-01: all amounts Decimal.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from services.fraud_tracer.tracer_models import TracerConfig, VelocityResult

DEFAULT_CONFIG = TracerConfig()


class VelocityPort(Protocol):
    """Protocol for velocity data store."""

    def get_tx_count(self, customer_id: str, window_minutes: int) -> int: ...

    def get_tx_total(self, customer_id: str, window_minutes: int) -> Decimal: ...

    def record_tx(self, customer_id: str, amount: Decimal) -> None: ...


class InMemoryVelocityPort:
    """In-memory stub for velocity checks (Protocol DI)."""

    def __init__(self) -> None:
        self._data: dict[str, list[Decimal]] = {}

    def get_tx_count(self, customer_id: str, window_minutes: int) -> int:
        return len(self._data.get(customer_id, []))

    def get_tx_total(self, customer_id: str, window_minutes: int) -> Decimal:
        amounts = self._data.get(customer_id, [])
        return sum(amounts, Decimal("0"))

    def record_tx(self, customer_id: str, amount: Decimal) -> None:
        if customer_id not in self._data:
            self._data[customer_id] = []
        self._data[customer_id].append(amount)


class VelocityChecker:
    """Checks transaction velocity against configured thresholds.

    I-01: all amounts are Decimal.
    """

    def __init__(
        self,
        port: VelocityPort | None = None,
        config: TracerConfig | None = None,
    ) -> None:
        self._port: VelocityPort = port or InMemoryVelocityPort()
        self._config = config or DEFAULT_CONFIG

    def check_velocity(self, customer_id: str, window_minutes: int = 60) -> VelocityResult:
        count = self._port.get_tx_count(customer_id, window_minutes)
        total = self._port.get_tx_total(customer_id, window_minutes)
        max_amount = Decimal(self._config.max_tx_amount)
        breached = count >= self._config.max_tx_count or total >= max_amount
        return VelocityResult(
            customer_id=customer_id,
            window_minutes=window_minutes,
            tx_count=count,
            total_amount=str(total),
            breached=breached,
        )

    def record_transaction(self, customer_id: str, amount: Decimal) -> None:
        """Record a transaction for velocity tracking."""
        self._port.record_tx(customer_id, amount)
