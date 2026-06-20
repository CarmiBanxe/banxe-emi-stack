"""
api/models/quant_advisory.py — Quant advisory API DTOs
GAP-070 | IMPL-4 | banxe-emi-stack

All read/advisory — no execution payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PriceResponse(BaseModel):
    model: str
    price: float
    advisory: bool = True


class VolSurfacePointModel(BaseModel):
    strike: float
    implied_vol: float


class VolSurfaceResponse(BaseModel):
    forward: float
    expiry: float
    points: list[VolSurfacePointModel]


class GreeksResponse(BaseModel):
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


class VarResponse(BaseModel):
    var99: float
    horizon_days: int
    confidence: float


class MMSpreadRequest(BaseModel):
    mid: float = Field(..., description="Mid price")
    inventory: float = Field(0.0, description="Current inventory q")
    gamma: float = Field(0.1, description="Risk aversion γ")
    sigma: float = Field(0.2, description="Volatility σ")
    time_left: float = Field(1.0, description="Time to horizon (T−t)")
    k: float = Field(1.5, description="Order-book liquidity k")


class MMSpreadResponse(BaseModel):
    reservation_price: float
    optimal_spread: float
    bid: float
    ask: float
    advisory: bool = True
    execution_allowed: bool = False
