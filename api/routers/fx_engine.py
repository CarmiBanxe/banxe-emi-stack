"""
api/routers/fx_engine.py
FX Engine REST API
IL-FXE-01 | Sprint 34 | Phase 48

FCA: PS22/9, EMIR, MLR 2017 Reg.28, FCA COBS 14.3
Trust Zone: AMBER

9 endpoints at /v1/fx/*
HITL L4 for executions >= £10k (I-04, I-27).
"""

from __future__ import annotations

from decimal import Decimal
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.fx_engine.fx_agent import FXAgent
from services.fx_engine.fx_compliance_reporter import FXComplianceReporter
from services.fx_engine.fx_executor import FXExecutor
from services.fx_engine.fx_quoter import FXQuoter
from services.fx_engine.hedging_engine import HedgingEngine
from services.fx_engine.models import (
    InMemoryExecutionStore,
    InMemoryHedgeStore,
    InMemoryQuoteStore,
    InMemoryRateStore,
)
from services.fx_engine.rate_provider import RateProvider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FX Engine"])

# ── Module-level singletons ───────────────────────────────────────────────

_rate_store = InMemoryRateStore()
_quote_store = InMemoryQuoteStore()
_execution_store = InMemoryExecutionStore()
_hedge_store = InMemoryHedgeStore()

_rate_provider = RateProvider(store=_rate_store)
_quoter = FXQuoter(rate_store=_rate_store, quote_store=_quote_store)
_executor = FXExecutor(quote_store=_quote_store, execution_store=_execution_store)
_hedging = HedgingEngine(store=_hedge_store)
_compliance = FXComplianceReporter()
_agent = FXAgent(quoter=_quoter)


# ── Request / Response models ─────────────────────────────────────────────


class CreateQuoteRequest(BaseModel):
    """Request model for FX quote creation."""

    currency_pair: str  # e.g. "GBP/EUR"
    sell_amount: str  # Decimal string (I-22)
    sell_currency: str
    tenant_id: str = "default"


class ExecuteQuoteRequest(BaseModel):
    """Request model for FX quote execution."""

    actor: str = "API"


class RejectQuoteRequest(BaseModel):
    """Request model for FX quote rejection."""

    reason: str
    actor: str = "API"


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/rates")
async def list_rates() -> dict[str, object]:
    """List all available FX rates.

    Staleness checked (max 60s). Decimal bid/ask/mid (I-22).
    """
    rates = _rate_provider.get_all_rates()
    return {
        "rates": [r.model_dump() for r in rates],
        "count": len(rates),
    }


@router.get("/rates/{currency_pair}")
async def get_rate(currency_pair: str) -> dict[str, object]:
    """Get FX rate for a currency pair (e.g. GBP-EUR → GBP/EUR).

    Staleness checked. is_stale=True if >60s old (I-23).
    """
    pair = currency_pair.replace("-", "/").upper()
    rate = _rate_provider.get_rate(pair)
    if rate is None:
        raise HTTPException(status_code=404, detail=f"No rate found for {pair}")
    return rate.model_dump()


@router.post("/quotes")
async def create_quote(req: CreateQuoteRequest) -> dict[str, object]:
    """Create FX quote with 30-second TTL.

    Spread tiered by volume (I-04 £10k). I-23: UTC expires_at.
    Returns None if rate not found.
    """
    try:
        sell_amount = Decimal(req.sell_amount)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid sell_amount: {req.sell_amount}")

    quote = _quoter.create_quote(
        currency_pair=req.currency_pair,
        sell_amount=sell_amount,
        sell_currency=req.sell_currency,
        tenant_id=req.tenant_id,
    )
    if quote is None:
        raise HTTPException(status_code=404, detail=f"No rate available for {req.currency_pair}")
    return quote.model_dump()


@router.get("/quotes/{quote_id}")
async def get_quote(quote_id: str) -> dict[str, object]:
    """Get FX quote by ID with validity status."""
    quote = _quoter.get_quote(quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")
    is_valid = _quoter.is_quote_valid(quote_id)
    result = quote.model_dump()
    result["is_valid"] = is_valid
    return result


@router.post("/quotes/{quote_id}/execute")
async def execute_quote(quote_id: str, req: ExecuteQuoteRequest) -> dict[str, object]:
    """Execute FX quote.

    Auto-approved < £10k (L1). HITLProposal >= £10k (I-04, I-27).
    """
    from dataclasses import asdict

    quote = _quoter.get_quote(quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")

    result = _executor.execute(quote_id, req.actor)

    if hasattr(result, "action"):  # HITLProposal
        return asdict(result)  # type: ignore[arg-type]
    return result.model_dump()  # type: ignore[union-attr]


@router.post("/quotes/{quote_id}/reject")
async def reject_quote(quote_id: str, req: RejectQuoteRequest) -> dict[str, object]:
    """Reject FX quote — always returns HITLProposal (L4, I-27)."""
    from dataclasses import asdict

    proposal = _executor.reject(quote_id, req.reason, req.actor)
    return asdict(proposal)


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str) -> dict[str, object]:
    """Get FX execution by ID."""
    execution = _executor.get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return execution.model_dump()


@router.get("/hedge/positions/{currency_pair}")
async def get_hedge_position(currency_pair: str) -> dict[str, object]:
    """Get current hedge position for a currency pair.

    HITL alert if |net_exposure| >= £500k (I-27).
    """
    pair = currency_pair.replace("-", "/").upper()
    exposure = _hedging.get_net_exposure(pair)
    alert = _hedging.check_threshold(pair)

    result: dict[str, object] = {
        "currency_pair": pair,
        "net_exposure": str(exposure),
        "hitl_alert": alert is not None,
    }
    if alert is not None:
        from dataclasses import asdict

        result["hitl_proposal"] = asdict(alert)

    return result


@router.get("/compliance/summary")
async def get_compliance_summary() -> dict[str, object]:
    """Get FX compliance summary.

    Large FX count, pending reports, daily volume. I-22 Decimal as strings.
    """
    summary = _compliance.get_compliance_summary()
    return {
        "large_fx_count": summary["large_fx_count"],
        "total_volume": str(summary["total_volume"]),
        "pending_reports": summary["pending_reports"],
    }
