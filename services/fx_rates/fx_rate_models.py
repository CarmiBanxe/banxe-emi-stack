from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class RateEntry:
    base: str
    date: str  # ISO date YYYY-MM-DD
    rates: dict[str, str]  # symbol → Decimal as string (JSON-safe, I-01)
    source: str = "frankfurter-ecb"
    fetched_at: str = ""  # UTC ISO


@dataclass(frozen=True)
class ConversionResult:
    from_currency: str
    to_currency: str
    amount: Decimal  # I-01
    converted_amount: Decimal  # I-01
    rate: Decimal  # I-01
    date: str


@dataclass(frozen=True)
class RateOverride:
    override_id: str
    base: str
    symbol: str
    rate: Decimal  # I-01
    operator: str
    reason: str
    created_at: str


class RateStorePort(Protocol):
    def append(self, entry: RateEntry) -> None: ...

    def get_latest(self, base: str) -> RateEntry | None: ...

    def get_historical(self, base: str, date: str) -> RateEntry | None: ...

    def list_recent(self, limit: int = 30) -> list[RateEntry]: ...


class InMemoryRateStore:
    def __init__(self) -> None:
        self._entries: list[RateEntry] = []
        # seed 2 entries
        from datetime import date

        today = date.today().isoformat()
        self._entries.append(
            RateEntry(
                base="GBP",
                date=today,
                rates={"EUR": "1.1650", "USD": "1.2340", "JPY": "185.50", "CHF": "1.1020"},
                fetched_at=today + "T07:00:00Z",
            )
        )
        self._entries.append(
            RateEntry(
                base="EUR",
                date=today,
                rates={"GBP": "0.8584", "USD": "1.0594", "JPY": "159.22"},
                fetched_at=today + "T07:00:00Z",
            )
        )

    def append(self, entry: RateEntry) -> None:
        self._entries.append(entry)

    def get_latest(self, base: str) -> RateEntry | None:
        matches = [e for e in self._entries if e.base == base]
        return matches[-1] if matches else None

    def get_historical(self, base: str, date: str) -> RateEntry | None:
        matches = [e for e in self._entries if e.base == base and e.date == date]
        return matches[0] if matches else None

    def list_recent(self, limit: int = 30) -> list[RateEntry]:
        return self._entries[-limit:]
