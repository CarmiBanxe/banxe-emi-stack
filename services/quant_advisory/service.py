"""
services/quant_advisory/service.py — QuantAdvisoryService orchestration
GAP-070 | IMPL-4 | banxe-emi-stack

Orchestrates pricing + market-making + risk metrics into an ADVISORY recommendation
(ADR-113; ties GAP-036 treasury/QuantLib, GAP-020 ICARA).

ADVISORY-SEAM ONLY — QUANT_CAN_EXECUTE = False. There is NO order/MM execution
path; outputs feed the Dynamic Spread Engine and a human decides (MiCA broker-dealer
avoidance, ADR-089/090/091/093). Reuses risk/treasury seams — does not reimplement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.quant_advisory.market_making import ASQuote, AvellanedaStoikov
from services.quant_advisory.pricing import (
    HestonParams,
    JumpParams,
    PricingModel,
    bates_price,
    black_scholes_price,
    heston_price,
    sabr_implied_vol,
)
from services.quant_advisory.risk_metrics import (
    Greeks,
    greeks,
    parametric_var,
    stress_scenarios,
)

# Hard invariant: this service is advisory-only. No execution path exists.
QUANT_CAN_EXECUTE = False


@dataclass(frozen=True)
class VolSurfacePoint:
    strike: float
    implied_vol: float


@dataclass(frozen=True)
class AdvisoryRecommendation:
    kind: str
    price: float
    greeks: Greeks
    var99: float
    note: str = "ADVISORY ONLY — feeds DSE; human decides. No autonomous execution."
    execution_allowed: bool = field(default=False)


class QuantAdvisoryService:
    """Quant pricing/risk advisory orchestrator (read/advisory only)."""

    def __init__(self) -> None:
        self._as = AvellanedaStoikov()

    def price(
        self,
        model: PricingModel,
        s: float,
        k: float,
        t: float,
        r: float,
        *,
        sigma: float = 0.2,
        heston: HestonParams | None = None,
        jump: JumpParams | None = None,
        call: bool = True,
    ) -> float:
        if model is PricingModel.BLACK_SCHOLES:
            return black_scholes_price(s, k, t, r, sigma, call=call)
        hp = heston or HestonParams(v0=sigma**2, kappa=1.5, theta=sigma**2, sigma=0.3, rho=-0.6)
        if model is PricingModel.HESTON:
            return heston_price(s, k, t, r, hp, call=call)
        jp = jump or JumpParams(lam=0.3, mu_j=-0.1, sigma_j=0.15)
        return bates_price(s, k, t, r, hp, jp, call=call)

    def vol_surface(
        self,
        forward: float,
        t: float,
        strikes: list[float],
        *,
        alpha: float = 0.2,
        beta: float = 0.5,
        rho: float = -0.3,
        nu: float = 0.4,
    ) -> list[VolSurfacePoint]:
        return [
            VolSurfacePoint(
                strike=k,
                implied_vol=sabr_implied_vol(forward, k, t, alpha=alpha, beta=beta, rho=rho, nu=nu),
            )
            for k in strikes
        ]

    def compute_greeks(
        self, s: float, k: float, t: float, r: float, sigma: float, *, call: bool = True
    ) -> Greeks:
        return greeks(s, k, t, r, sigma, call=call)

    def value_at_risk(
        self,
        position_value: float,
        sigma: float,
        *,
        horizon_days: int = 1,
        confidence: float = 0.99,
    ) -> float:
        return parametric_var(
            position_value, sigma, horizon_days=horizon_days, confidence=confidence
        )

    def mm_spread(
        self,
        mid: float,
        inventory: float,
        *,
        gamma: float = 0.1,
        sigma: float = 0.2,
        time_left: float = 1.0,
        k: float = 1.5,
    ) -> ASQuote:
        # Advisory recommendation only — never routed to an order/MM engine.
        return self._as.quote(mid, inventory, gamma=gamma, sigma=sigma, time_left=time_left, k=k)

    def recommend(
        self,
        model: PricingModel,
        s: float,
        k: float,
        t: float,
        r: float,
        *,
        sigma: float = 0.2,
        position_value: float = 0.0,
        call: bool = True,
    ) -> AdvisoryRecommendation:
        price = self.price(model, s, k, t, r, sigma=sigma, call=call)
        g = self.compute_greeks(s, k, t, r, sigma, call=call)
        var99 = self.value_at_risk(position_value or s, sigma)
        return AdvisoryRecommendation(kind=model.value, price=price, greeks=g, var99=var99)

    def stress(self, position_value: float, sigma: float) -> list:
        return stress_scenarios(position_value, sigma)
