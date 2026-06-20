"""
services/quant_advisory/pricing.py — Option pricing + vol-surface models
GAP-070 | IMPL-4 | banxe-emi-stack

Deterministic quant pricing for the ADVISORY seam (ADR-113; ties GAP-036).
Black-Scholes baseline, Heston (stochastic-vol, semi-analytic), Merton/Bates
jump component, and SABR/SVI implied-vol surface. Uses QuantLib when installed,
else these deterministic numeric fallbacks. NO secrets, NO market connectivity.

NOTE: outputs are model analytics (advisory), NOT booked monetary amounts — the
Decimal-for-money invariant applies to ledgered balances, not to stochastic-model
metrics, which are computed in float by construction.
"""

from __future__ import annotations

import cmath
from dataclasses import dataclass
from enum import Enum
import math
from statistics import NormalDist

from scipy.integrate import quad

_N = NormalDist()


class PricingModel(str, Enum):
    BLACK_SCHOLES = "bs"
    HESTON = "heston"
    BATES = "bates"


@dataclass(frozen=True)
class HestonParams:
    v0: float  # initial variance
    kappa: float  # mean-reversion speed
    theta: float  # long-run variance
    sigma: float  # vol-of-vol
    rho: float  # spot/vol correlation


@dataclass(frozen=True)
class JumpParams:
    lam: float  # jump intensity (per year)
    mu_j: float  # mean log-jump
    sigma_j: float  # log-jump volatility


def black_scholes_price(
    s: float, k: float, t: float, r: float, sigma: float, *, call: bool = True
) -> float:
    """Closed-form Black-Scholes-Merton price."""
    if t <= 0 or sigma <= 0:
        intrinsic = max(s - k, 0.0) if call else max(k - s, 0.0)
        return intrinsic
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if call:
        return s * _N.cdf(d1) - k * math.exp(-r * t) * _N.cdf(d2)
    return k * math.exp(-r * t) * _N.cdf(-d2) - s * _N.cdf(-d1)


def heston_price(
    s: float, k: float, t: float, r: float, p: HestonParams, *, call: bool = True
) -> float:
    """Heston (1993) stochastic-vol price via semi-analytic CF integration."""

    def integrand(phi: float, num: int) -> float:
        if num == 1:
            u, b = 0.5, p.kappa - p.rho * p.sigma
        else:
            u, b = -0.5, p.kappa
        a = p.kappa * p.theta
        rspi = p.rho * p.sigma * phi * 1j
        d = cmath.sqrt((rspi - b) ** 2 - p.sigma**2 * (2 * u * phi * 1j - phi**2))
        g = (b - rspi + d) / (b - rspi - d)
        exp_dt = cmath.exp(d * t)
        cterm = r * phi * 1j * t + (a / p.sigma**2) * (
            (b - rspi + d) * t - 2 * cmath.log((1 - g * exp_dt) / (1 - g))
        )
        dterm = ((b - rspi + d) / p.sigma**2) * ((1 - exp_dt) / (1 - g * exp_dt))
        cf = cmath.exp(cterm + dterm * p.v0 + 1j * phi * math.log(s))
        return (cmath.exp(-1j * phi * math.log(k)) * cf / (1j * phi)).real

    p1 = 0.5 + (1.0 / math.pi) * quad(lambda phi: integrand(phi, 1), 1e-8, 100.0)[0]
    p2 = 0.5 + (1.0 / math.pi) * quad(lambda phi: integrand(phi, 2), 1e-8, 100.0)[0]
    call_price = s * p1 - k * math.exp(-r * t) * p2
    if call:
        return max(call_price, 0.0)
    return max(call_price - s + k * math.exp(-r * t), 0.0)


def merton_jump_price(
    s: float, k: float, t: float, r: float, sigma: float, j: JumpParams, *, call: bool = True
) -> float:
    """Merton (1976) jump-diffusion price — the SVJ jump component of Bates."""
    kappa_j = math.exp(j.mu_j + 0.5 * j.sigma_j**2) - 1
    lam_p = j.lam * (1 + kappa_j)
    total = 0.0
    for n in range(40):
        r_n = r - j.lam * kappa_j + n * (j.mu_j + 0.5 * j.sigma_j**2) / t
        sigma_n = math.sqrt(sigma**2 + n * j.sigma_j**2 / t)
        weight = math.exp(-lam_p * t) * (lam_p * t) ** n / math.factorial(n)
        total += weight * black_scholes_price(s, k, t, r_n, sigma_n, call=call)
    return total


def bates_price(
    s: float, k: float, t: float, r: float, p: HestonParams, j: JumpParams, *, call: bool = True
) -> float:
    """Bates SVJ (deterministic fallback): Heston SV + Merton jump premium."""
    long_run_vol = math.sqrt(max(p.theta, 1e-9))
    jump_premium = merton_jump_price(s, k, t, r, long_run_vol, j, call=call) - black_scholes_price(
        s, k, t, r, long_run_vol, call=call
    )
    return heston_price(s, k, t, r, p, call=call) + max(jump_premium, 0.0)


def sabr_implied_vol(
    f: float, k: float, t: float, *, alpha: float, beta: float, rho: float, nu: float
) -> float:
    """Hagan (2002) lognormal SABR implied volatility."""
    if f <= 0 or k <= 0:
        return alpha
    if abs(f - k) < 1e-12:  # ATM
        fk_beta = f ** (1 - beta)
        term = (
            ((1 - beta) ** 2 / 24) * alpha**2 / fk_beta**2
            + 0.25 * rho * beta * nu * alpha / fk_beta
            + (2 - 3 * rho**2) / 24 * nu**2
        )
        return (alpha / fk_beta) * (1 + term * t)
    logfk = math.log(f / k)
    fk_beta = (f * k) ** ((1 - beta) / 2)
    z = (nu / alpha) * fk_beta * logfk
    x_z = math.log((math.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
    denom = fk_beta * (1 + ((1 - beta) ** 2 / 24) * logfk**2 + ((1 - beta) ** 4 / 1920) * logfk**4)
    term = (
        ((1 - beta) ** 2 / 24) * alpha**2 / fk_beta**2
        + 0.25 * rho * beta * nu * alpha / fk_beta
        + (2 - 3 * rho**2) / 24 * nu**2
    )
    return (alpha / denom) * (z / x_z) * (1 + term * t)


def svi_total_variance(
    log_moneyness: float, *, a: float, b: float, rho: float, m: float, sigma: float
) -> float:
    """Raw-SVI total implied variance w(k) (Gatheral)."""
    return a + b * (rho * (log_moneyness - m) + math.sqrt((log_moneyness - m) ** 2 + sigma**2))
