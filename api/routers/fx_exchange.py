"""
api/routers/fx_exchange.py
IL-FX-01 | Phase 21
from api.deps import require_auth

FX & Currency Exchange REST API.
from api.deps import require_auth

POST /v1/fx/quote                       — request FX quote
POST /v1/fx/execute                     — execute FX order
GET  /v1/fx/rates                       — all live rates (optional ?pairs=)
GET  /v1/fx/rates/{from}/{to}           — single pair rate
GET  /v1/fx/history/{entity_id}         — FX execution history
GET  /v1/fx/spreads                     — all spread configs
GET  /v1/fx/spreads/{from}/{to}         — single pair spread
POST /v1/fx/rates/refresh               — trigger rate refresh (operator)
from api.deps import require_auth

FCA compliance:
  - Amounts as strings in all responses (I-05)
  - HITL gate returns HTTP 202 for amounts >= £50k (I-27)
  - BLOCKED compliance flag returns HTTP 400
  - Sanctioned currencies hard-blocked (I-02)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.fx_exchange.fx_agent import FXAgent
from services.fx_exchange.fx_compliance import FXCompliance
from services.fx_exchange.fx_executor import FXExecutor
from services.fx_exchange.models import (
    InMemoryExecutionStore,
    InMemoryFXAudit,
    InMemoryOrderStore,
    InMemoryQuoteStore,
    InMemoryRateStore,
)
from services.fx_exchange.quote_engine import QuoteEngine
from services.fx_exchange.rate_provider import RateProvider
from services.fx_exchange.spread_manager import SpreadManager

router = APIRouter(tags=["fx-exchange"])


# ── Pydantic request models ────────────────────────────────────────────────────


class QuoteRequest(BaseModel):
    entity_id: str
    from_currency: str
    to_currency: str
    amount: str  # DecimalString (I-05)


class ExecuteRequest(BaseModel):
    entity_id: str
    quote_id: str


# ── Agent factory ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> FXAgent:
    """Build FXAgent wired to InMemory stubs — test isolation via Depends."""
    rate_store = InMemoryRateStore()
    quote_store = InMemoryQuoteStore()
    order_store = InMemoryOrderStore()
    execution_store = InMemoryExecutionStore()
    audit = InMemoryFXAudit()

    rate_provider = RateProvider(rate_store)
    quote_engine = QuoteEngine(rate_store, quote_store)
    fx_executor = FXExecutor(order_store, execution_store, audit)
    spread_manager = SpreadManager()
    fx_compliance = FXCompliance()

    return FXAgent(rate_provider, quote_engine, fx_executor, spread_manager, fx_compliance)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/v1/fx/quote")
async def request_quote(
    req: QuoteRequest,
    agent: FXAgent = Depends(_get_agent),
) -> dict[str, Any]:
    """Request a live FX quote. Returns 400 if currency is sanctioned."""
    try:
        result = await agent.request_quote(
            entity_id=req.entity_id,
            from_currency=req.from_currency,
            to_currency=req.to_currency,
            amount=req.amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if result.get("status") == "BLOCKED":
        raise HTTPException(status_code=400, detail=result.get("reason", "Blocked"))
    return result


@router.post("/v1/fx/execute")
async def execute_fx(
    req: ExecuteRequest,
    agent: FXAgent = Depends(_get_agent),
) -> dict[str, Any]:
    """Execute an FX order from a valid quote.

    Returns:
      200 — execution dict
      202 — HITL_REQUIRED (amount >= £50k, requires Compliance Officer approval)
      400 — blocked or validation error
      404 — quote not found
    """
    try:
        result = await agent.execute_fx(
            entity_id=req.entity_id,
            quote_id=req.quote_id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    if result.get("status") == "HITL_REQUIRED":
        # HTTP 202 Accepted — pending human review (I-27)
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=202, content=result)

    return result


@router.get("/v1/fx/rates")
async def get_live_rates(
    pairs: str | None = None,
    agent: FXAgent = Depends(_get_agent),
) -> dict[str, Any]:
    """Return live FX rates. Optional ?pairs=GBP/EUR,GBP/USD query parameter."""
    pair_list: list[str] | None = None
    if pairs:
        pair_list = [p.strip() for p in pairs.split(",") if p.strip()]
    return await agent.get_live_rates(pair_list)


@router.get("/v1/fx/rates/refresh")
async def get_refresh_placeholder() -> dict[str, str]:
    """Placeholder — use POST /v1/fx/rates/refresh to trigger refresh."""
    return {"detail": "Use POST /v1/fx/rates/refresh to trigger rate refresh."}


@router.post("/v1/fx/rates/refresh")
async def refresh_rates(
    agent: FXAgent = Depends(_get_agent),
) -> dict[str, Any]:
    """Trigger a rate refresh for all supported pairs (operator endpoint)."""

    rates = await agent.get_live_rates(None)
    return {"refreshed": len(rates), "rates": rates}


@router.get("/v1/fx/rates/{from_currency}/{to_currency}")
async def get_single_rate(
    from_currency: str,
    to_currency: str,
    agent: FXAgent = Depends(_get_agent),
) -> dict[str, Any]:
    """Return the live rate for a single currency pair."""
    pair_str = f"{from_currency}/{to_currency}"
    rates = await agent.get_live_rates([pair_str])
    if pair_str not in rates:
        raise HTTPException(status_code=404, detail=f"No rate found for pair {pair_str}")
    return {"pair": pair_str, "rate": rates[pair_str]}


@router.get("/v1/fx/history/{entity_id}")
async def get_fx_history(
    entity_id: str,
    agent: FXAgent = Depends(_get_agent),
) -> list[dict[str, Any]]:
    """Return FX execution history for an entity."""
    return await agent.get_fx_history(entity_id)


@router.get("/v1/fx/spreads")
async def list_spreads(
    agent: FXAgent = Depends(_get_agent),
) -> list[dict[str, Any]]:
    """Return all configured spread configs."""
    configs = await agent._spreads.list_spreads()
    return [
        {
            "pair": str(c.pair),
            "base_spread_bps": c.base_spread_bps,
            "min_spread_bps": c.min_spread_bps,
            "vip_spread_bps": c.vip_spread_bps,
            "tier_volume_threshold": str(c.tier_volume_threshold),
        }
        for c in configs
    ]


@router.get("/v1/fx/spreads/{from_currency}/{to_currency}")
async def get_single_spread(
    from_currency: str,
    to_currency: str,
    agent: FXAgent = Depends(_get_agent),
) -> dict[str, Any]:
    """Return spread configuration for a single currency pair."""
    return await agent.get_spread_info(from_currency, to_currency)
