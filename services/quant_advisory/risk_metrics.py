"""
services/quant_advisory/risk_metrics.py — Greeks + VaR + stress
GAP-070 | IMPL-4 | banxe-emi-stack

Closed-form option Greeks, parametric VaR99 and deterministic stress scenarios
for the advisory seam (ties GAP-020 ICARA). Read-only analytics — no execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import NormalDist

_N = NormalDist()


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


@dataclass(frozen=True)
class StressResult:
    scenario: str
    pnl: float


def greeks(s: float, k: float, t: float, r: float, sigma: float, *, call: bool = True) -> Greeks:
    """Black-Scholes Greeks (per 1.0 spot; vega/theta/rho per unit move)."""
    if t <= 0 or sigma <= 0:
        intrinsic_delta = (1.0 if s > k else 0.0) if call else (-1.0 if s < k else 0.0)
        return Greeks(delta=intrinsic_delta, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    pdf_d1 = _N.pdf(d1)
    delta = _N.cdf(d1) if call else _N.cdf(d1) - 1.0
    gamma = pdf_d1 / (s * sigma * sqrt_t)
    vega = s * pdf_d1 * sqrt_t
    discount = k * t * math.exp(-r * t)
    if call:
        theta = -(s * pdf_d1 * sigma) / (2 * sqrt_t) - r * discount / t * _N.cdf(d2)
        rho = discount * _N.cdf(d2)
    else:
        theta = -(s * pdf_d1 * sigma) / (2 * sqrt_t) + r * discount / t * _N.cdf(-d2)
        rho = -discount * _N.cdf(-d2)
    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def parametric_var(
    position_value: float, sigma: float, *, horizon_days: int = 1, confidence: float = 0.99
) -> float:
    """Parametric (variance-covariance) VaR — positive number = potential loss."""
    z = _N.inv_cdf(confidence)
    horizon_sigma = sigma * math.sqrt(horizon_days / 252.0)
    return abs(position_value) * z * horizon_sigma


def stress_scenarios(
    position_value: float, sigma: float, *, spot_shocks=(-0.2, -0.1, 0.1, 0.2)
) -> list[StressResult]:
    """Deterministic spot-shock stress P&L (advisory, ICARA-aligned)."""
    results: list[StressResult] = []
    for shock in spot_shocks:
        results.append(StressResult(scenario=f"spot{shock:+.0%}", pnl=position_value * shock))
    results.append(StressResult(scenario="vol+50%", pnl=-abs(position_value) * sigma * 0.5))
    return results
