"""FX Rates Router — Frankfurter ECB self-hosted rates.

IL-FXR-01 | Phase 52A | Sprint 37

GET  /v1/fx-rates/latest                — ?base=GBP&symbols=EUR,USD
GET  /v1/fx-rates/historical/{date}     — ?base=GBP&symbols=EUR,USD
GET  /v1/fx-rates/time-series           — ?start=2026-01-01&end=2026-01-31&base=GBP
POST /v1/fx-rates/convert               — {amount: "100.00", from: "GBP", to: "EUR"}
POST /v1/fx-rates/override              — {base, symbol, rate, reason} → HITLProposal (I-27 L4)

FCA compliance:
  - Amounts always strings (DecimalString, I-01)
  - Rates always strings (DecimalString, I-01)
  - Blocked currencies rejected (I-02)
  - Override always HITL L4 (I-27, TREASURY_OFFICER)
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from services.fx_rates.frankfurter_client import BLOCKED_CURRENCIES, FXRateService

router = APIRouter(tags=["fx-rates"])


# ── Dependency ─────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_service() -> FXRateService:
    return FXRateService()


# ── Pydantic models ────────────────────────────────────────────────────────


class ConvertRequest(BaseModel):
    amount: str  # DecimalString (I-01)
    from_currency: str
    to_currency: str

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            d = Decimal(v)
        except InvalidOperation as exc:
            raise ValueError("amount must be a valid decimal string") from exc
        if d <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("from_currency", "to_currency")
    @classmethod
    def validate_currency_not_blocked(cls, v: str) -> str:
        if v.upper() in BLOCKED_CURRENCIES:
            raise ValueError(f"I-02: currency {v!r} is from a blocked jurisdiction")
        return v.upper()


class OverrideRequest(BaseModel):
    base: str
    symbol: str
    rate: str  # DecimalString (I-01)
    operator: str
    reason: str

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, v: str) -> str:
        try:
            d = Decimal(v)
        except InvalidOperation as exc:
            raise ValueError("rate must be a valid decimal string") from exc
        if d <= 0:
            raise ValueError("rate must be positive")
        return v

    @field_validator("base", "symbol")
    @classmethod
    def validate_not_blocked(cls, v: str) -> str:
        if v.upper() in BLOCKED_CURRENCIES:
            raise ValueError(f"I-02: currency {v!r} is from a blocked jurisdiction")
        return v.upper()


class ConvertResponse(BaseModel):
    from_currency: str
    to_currency: str
    amount: str  # DecimalString (I-01)
    converted_amount: str  # DecimalString (I-01)
    rate: str  # DecimalString (I-01)
    date: str


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/fx-rates/latest")
async def get_latest_rates(
    base: str = Query(default="GBP", description="Base currency"),
    symbols: str = Query(default="", description="Comma-separated symbols, e.g. EUR,USD"),
) -> dict[str, Any]:
    """Get latest ECB FX rates from self-hosted Frankfurter. (IL-FXR-01)"""
    svc = _get_service()
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    try:
        rates = svc.get_latest(base=base.upper(), symbols=syms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "base": base.upper(),
        "rates": {sym: str(rate) for sym, rate in rates.items()},
        "source": "frankfurter-ecb",
    }


@router.get("/fx-rates/historical/{date}")
async def get_historical_rates(
    date: str,
    base: str = Query(default="GBP", description="Base currency"),
    symbols: str = Query(default="", description="Comma-separated symbols"),
) -> dict[str, Any]:
    """Get historical ECB rates for a specific date (YYYY-MM-DD). (IL-FXR-01)"""
    svc = _get_service()
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    try:
        rates = svc.get_historical(date=date, base=base.upper(), symbols=syms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "base": base.upper(),
        "date": date,
        "rates": {sym: str(rate) for sym, rate in rates.items()},
        "source": "frankfurter-ecb",
    }


@router.get("/fx-rates/time-series")
async def get_time_series(
    start: str = Query(description="Start date YYYY-MM-DD"),
    end: str = Query(description="End date YYYY-MM-DD"),
    base: str = Query(default="GBP", description="Base currency"),
) -> dict[str, Any]:
    """Get FX rate time series for a date range. (IL-FXR-01)"""
    svc = _get_service()
    try:
        entries = svc.get_time_series(start=start, end=end, base=base.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "base": base.upper(),
        "start": start,
        "end": end,
        "entries": [
            {
                "date": e.date,
                "rates": e.rates,
                "source": e.source,
            }
            for e in entries
        ],
    }


@router.post("/fx-rates/convert", response_model=ConvertResponse)
async def convert_currency(body: ConvertRequest) -> ConvertResponse:
    """Convert amount between currencies using ECB rates (I-01 Decimal). (IL-FXR-01)"""
    svc = _get_service()
    try:
        result = svc.convert(
            amount=Decimal(body.amount),
            from_currency=body.from_currency,
            to_currency=body.to_currency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ConvertResponse(
        from_currency=result.from_currency,
        to_currency=result.to_currency,
        amount=str(result.amount),
        converted_amount=str(result.converted_amount),
        rate=str(result.rate),
        date=result.date,
    )


@router.post("/fx-rates/override", status_code=202)
async def override_rate(body: OverrideRequest) -> dict[str, Any]:
    """Propose manual FX rate override — always HITLProposal (I-27 L4, TREASURY_OFFICER)."""
    svc = _get_service()
    proposal = svc.override_rate(
        base=body.base,
        symbol=body.symbol,
        rate=Decimal(body.rate),
        operator=body.operator,
        reason=body.reason,
    )
    return proposal
