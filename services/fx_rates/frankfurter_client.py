"""Frankfurter FX rate client — self-hosted ECB rates.

Frankfurter is an open-source API for current and historical foreign exchange rates
published by the European Central Bank (no API key required).
Self-hosted: docker run -p 8087:8080 hakanensari/frankfurter
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import logging
import os
import time
from typing import Any

import httpx

from services.fx_rates.fx_rate_models import (
    ConversionResult,
    InMemoryRateStore,
    RateEntry,
    RateOverride,
    RateStorePort,
)

logger = logging.getLogger("banxe.fx_rates")

FRANKFURTER_BASE_URL = os.environ.get("FRANKFURTER_BASE_URL", "http://localhost:8087")
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.5  # seconds

# I-02: blocked jurisdictions — currencies associated with blocked jurisdictions
BLOCKED_CURRENCIES = {"RUB", "IRR", "KPW", "BYR", "BYN", "CUP", "CUC", "VES"}


def _safe_decimal(value: Any) -> Decimal:
    """Convert API float/string to Decimal safely (I-01)."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


class FrankfurterClient:
    """HTTP client for self-hosted Frankfurter ECB rate service."""

    def __init__(
        self, base_url: str = FRANKFURTER_BASE_URL, store: RateStorePort | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._store = store or InMemoryRateStore()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET with retry (3 attempts, exponential backoff)."""
        url = f"{self._base_url}{path}"
        for attempt in range(MAX_RETRIES):
            try:
                response = httpx.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(RETRY_BASE_DELAY * (2**attempt))
        return {}  # unreachable

    def _filter_blocked(self, rates: dict[str, Any]) -> dict[str, str]:
        """Remove blocked-jurisdiction currencies, convert to Decimal strings (I-01, I-02)."""
        return {
            sym: str(_safe_decimal(rate))
            for sym, rate in rates.items()
            if sym not in BLOCKED_CURRENCIES
        }

    def get_latest(self, base: str = "GBP", symbols: list[str] | None = None) -> dict[str, Decimal]:
        """Fetch latest ECB rates. Returns {symbol: Decimal} (I-01)."""
        params: dict[str, Any] = {"base": base}
        if symbols:
            params["symbols"] = ",".join(s for s in symbols if s not in BLOCKED_CURRENCIES)
        data = self._get("/latest", params)
        rates_str = self._filter_blocked(data.get("rates", {}))
        entry = RateEntry(
            base=base,
            date=data.get("date", datetime.now(UTC).date().isoformat()),
            rates=rates_str,
            fetched_at=datetime.now(UTC).isoformat(),
        )
        self._store.append(entry)  # I-24 append-only
        return {sym: Decimal(rate) for sym, rate in rates_str.items()}

    def get_historical(
        self, date: str, base: str = "GBP", symbols: list[str] | None = None
    ) -> dict[str, Decimal]:
        """Fetch historical rates for a specific date (YYYY-MM-DD). Returns Decimal (I-01)."""
        params: dict[str, Any] = {"base": base}
        if symbols:
            params["symbols"] = ",".join(s for s in symbols if s not in BLOCKED_CURRENCIES)
        data = self._get(f"/{date}", params)
        rates_str = self._filter_blocked(data.get("rates", {}))
        entry = RateEntry(
            base=base,
            date=date,
            rates=rates_str,
            fetched_at=datetime.now(UTC).isoformat(),
        )
        self._store.append(entry)  # I-24
        return {sym: Decimal(rate) for sym, rate in rates_str.items()}

    def get_time_series(
        self,
        start: str,
        end: str,
        base: str = "GBP",
        symbols: list[str] | None = None,
    ) -> list[RateEntry]:
        """Fetch time series (start..end, YYYY-MM-DD). Returns list of RateEntry (I-01)."""
        params: dict[str, Any] = {"base": base, "start_date": start, "end_date": end}
        if symbols:
            params["symbols"] = ",".join(s for s in symbols if s not in BLOCKED_CURRENCIES)
        data = self._get(f"/{start}..{end}", params)
        entries = []
        for date_str, rates_raw in data.get("rates", {}).items():
            rates_str = self._filter_blocked(rates_raw)
            entry = RateEntry(
                base=base,
                date=date_str,
                rates=rates_str,
                fetched_at=datetime.now(UTC).isoformat(),
            )
            self._store.append(entry)  # I-24
            entries.append(entry)
        return entries

    def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> ConversionResult:
        """Convert amount between currencies (I-01 Decimal in/out)."""
        if from_currency in BLOCKED_CURRENCIES or to_currency in BLOCKED_CURRENCIES:
            raise ValueError(
                f"I-02: blocked currency in conversion ({from_currency}/{to_currency})"
            )
        rates = self.get_latest(base=from_currency, symbols=[to_currency])
        if to_currency not in rates:
            raise ValueError(f"Rate not available: {from_currency}/{to_currency}")
        rate = rates[to_currency]
        return ConversionResult(
            from_currency=from_currency,
            to_currency=to_currency,
            amount=amount,
            converted_amount=(amount * rate).quantize(Decimal("0.0001")),
            rate=rate,
            date=datetime.now(UTC).date().isoformat(),
        )


class FXRateService:
    """Application service wrapping FrankfurterClient with I-27 HITL for overrides."""

    def __init__(
        self,
        client: FrankfurterClient | None = None,
        store: RateStorePort | None = None,
    ) -> None:
        self._store = store or InMemoryRateStore()
        self._client = client or FrankfurterClient(store=self._store)
        self._overrides: list[RateOverride] = []

    def get_latest(self, base: str = "GBP", symbols: list[str] | None = None) -> dict[str, Decimal]:
        return self._client.get_latest(base, symbols)

    def get_historical(
        self, date: str, base: str = "GBP", symbols: list[str] | None = None
    ) -> dict[str, Decimal]:
        return self._client.get_historical(date, base, symbols)

    def get_time_series(self, start: str, end: str, base: str = "GBP") -> list[RateEntry]:
        return self._client.get_time_series(start, end, base)

    def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> ConversionResult:
        return self._client.convert(amount, from_currency, to_currency)

    def override_rate(
        self, base: str, symbol: str, rate: Decimal, operator: str, reason: str
    ) -> dict[str, Any]:
        """Manual rate override — always HITL L4 (I-27, TREASURY_OFFICER)."""
        override_id = (
            f"ovr_{hashlib.sha256(f'{base}{symbol}{rate}{operator}'.encode()).hexdigest()[:8]}"
        )
        return {
            "proposal_type": "HITL_REQUIRED",
            "action": "rate_override",
            "data": {"base": base, "symbol": symbol, "rate": str(rate), "reason": reason},
            "override_id": override_id,
            "operator": operator,
            "autonomy_level": "L4",
            "requires_approval_from": "TREASURY_OFFICER",
            "created_at": datetime.now(UTC).isoformat(),
        }

    def get_cached_latest(self, base: str) -> RateEntry | None:
        return self._store.get_latest(base)


_fx_rate_service: FXRateService | None = None


def get_fx_rate_service() -> FXRateService:
    global _fx_rate_service
    if _fx_rate_service is None:
        _fx_rate_service = FXRateService()
    return _fx_rate_service
