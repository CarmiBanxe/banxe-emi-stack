"""
api/routers/quant_advisory.py — Quant advisory endpoints (read/advisory only)
GAP-070 | IMPL-4 | banxe-emi-stack

GET  /v1/quant/price        — Heston/Bates/BS option price
GET  /v1/quant/vol-surface  — SABR implied-vol surface
GET  /v1/quant/greeks       — Black-Scholes Greeks
GET  /v1/quant/var          — parametric VaR99
POST /v1/quant/mm-spread    — Avellaneda-Stoikov optimal spread (advisory)

ADVISORY-SEAM ONLY (ADR-113) — there are NO execution endpoints.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from api.models.quant_advisory import (
    GreeksResponse,
    MMSpreadRequest,
    MMSpreadResponse,
    PriceResponse,
    VarResponse,
    VolSurfacePointModel,
    VolSurfaceResponse,
)
from services.quant_advisory.pricing import PricingModel
from services.quant_advisory.service import QuantAdvisoryService

router = APIRouter(tags=["Quant Advisory"], prefix="/quant")


@lru_cache(maxsize=1)
def _svc() -> QuantAdvisoryService:
    return QuantAdvisoryService()


def _model(name: str) -> PricingModel:
    try:
        return PricingModel(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"unknown model: {name}") from exc


@router.get("/price", response_model=PriceResponse)
def price(
    s: float, k: float, t: float, r: float = 0.0, sigma: float = 0.2, model: str = "heston"
) -> PriceResponse:
    pm = _model(model)
    return PriceResponse(model=pm.value, price=round(_svc().price(pm, s, k, t, r, sigma=sigma), 6))


@router.get("/vol-surface", response_model=VolSurfaceResponse)
def vol_surface(forward: float, t: float, strikes: str) -> VolSurfaceResponse:
    try:
        strike_list = [round(x, 6) for x in (float(v) for v in strikes.split(","))]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="strikes must be comma-separated") from exc
    points = _svc().vol_surface(forward, t, strike_list)
    return VolSurfaceResponse(
        forward=forward,
        expiry=t,
        points=[
            VolSurfacePointModel(strike=p.strike, implied_vol=round(p.implied_vol, 6))
            for p in points
        ],
    )


@router.get("/greeks", response_model=GreeksResponse)
def greeks(s: float, k: float, t: float, r: float = 0.0, sigma: float = 0.2) -> GreeksResponse:
    g = _svc().compute_greeks(s, k, t, r, sigma)
    return GreeksResponse(
        delta=round(g.delta, 6),
        gamma=round(g.gamma, 6),
        vega=round(g.vega, 6),
        theta=round(g.theta, 6),
        rho=round(g.rho, 6),
    )


@router.get("/var", response_model=VarResponse)
def var(
    position_value: float, sigma: float, horizon_days: int = 1, confidence: float = 0.99
) -> VarResponse:
    value = _svc().value_at_risk(
        position_value, sigma, horizon_days=horizon_days, confidence=confidence
    )
    return VarResponse(var99=round(value, 6), horizon_days=horizon_days, confidence=confidence)


@router.post("/mm-spread", response_model=MMSpreadResponse)
def mm_spread(req: MMSpreadRequest) -> MMSpreadResponse:
    quote = _svc().mm_spread(
        req.mid,
        req.inventory,
        gamma=req.gamma,
        sigma=req.sigma,
        time_left=req.time_left,
        k=req.k,
    )
    return MMSpreadResponse(
        reservation_price=round(quote.reservation_price, 6),
        optimal_spread=round(quote.optimal_spread, 6),
        bid=round(quote.bid, 6),
        ask=round(quote.ask, 6),
    )
