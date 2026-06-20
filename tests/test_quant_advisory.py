"""
tests/test_quant_advisory.py — IMPL-4 quant pricing/risk advisory (GAP-070)

Pricing sanity (BS/Heston/Bates), SABR vol-surface, Greeks, VaR, Avellaneda-Stoikov
spread, and the advisory-only guard (QUANT_CAN_EXECUTE False, no execution path).
"""

from __future__ import annotations

import math

from services.quant_advisory.market_making import AvellanedaStoikov
from services.quant_advisory.pricing import (
    HestonParams,
    JumpParams,
    PricingModel,
    bates_price,
    black_scholes_price,
    heston_price,
    sabr_implied_vol,
    svi_total_variance,
)
from services.quant_advisory.risk_metrics import greeks, parametric_var, stress_scenarios
from services.quant_advisory.service import QUANT_CAN_EXECUTE, QuantAdvisoryService

_HESTON = HestonParams(v0=0.04, kappa=1.5, theta=0.04, sigma=0.3, rho=-0.6)
_JUMP = JumpParams(lam=0.3, mu_j=-0.1, sigma_j=0.15)


class TestBlackScholes:
    def test_atm_call_positive_and_below_spot(self) -> None:
        price = black_scholes_price(100, 100, 1.0, 0.0, 0.2, call=True)
        assert 0 < price < 100

    def test_put_call_parity(self) -> None:
        c = black_scholes_price(100, 95, 1.0, 0.05, 0.25, call=True)
        p = black_scholes_price(100, 95, 1.0, 0.05, 0.25, call=False)
        # c - p == s - k*e^{-rT}
        assert math.isclose(c - p, 100 - 95 * math.exp(-0.05), abs_tol=1e-6)

    def test_intrinsic_at_expiry(self) -> None:
        assert black_scholes_price(120, 100, 0.0, 0.0, 0.2, call=True) == 20


class TestHestonBates:
    def test_heston_atm_reasonable(self) -> None:
        price = heston_price(100, 100, 1.0, 0.0, _HESTON, call=True)
        # Near the BS price at comparable vol — sanity band.
        assert 0 < price < 30

    def test_bates_adds_jump_premium(self) -> None:
        h = heston_price(100, 100, 1.0, 0.0, _HESTON, call=True)
        b = bates_price(100, 100, 1.0, 0.0, _HESTON, _JUMP, call=True)
        assert b >= h  # jumps never reduce value in the fallback


class TestVolSurface:
    def test_sabr_atm_close_to_alpha(self) -> None:
        # beta=1 (lognormal SABR): ATM implied vol ≈ alpha (Hagan).
        vol = sabr_implied_vol(100, 100, 1.0, alpha=0.2, beta=1.0, rho=-0.3, nu=0.4)
        assert 0.15 < vol < 0.3

    def test_svi_total_variance_positive(self) -> None:
        w = svi_total_variance(0.0, a=0.04, b=0.1, rho=-0.3, m=0.0, sigma=0.1)
        assert w > 0


class TestGreeks:
    def test_call_delta_in_unit_interval(self) -> None:
        g = greeks(100, 100, 1.0, 0.0, 0.2, call=True)
        assert 0 < g.delta < 1
        assert g.gamma > 0
        assert g.vega > 0

    def test_put_delta_negative(self) -> None:
        g = greeks(100, 100, 1.0, 0.0, 0.2, call=False)
        assert -1 < g.delta < 0


class TestVaR:
    def test_var_positive_and_scales_with_sigma(self) -> None:
        v1 = parametric_var(1_000_000, 0.2, horizon_days=1)
        v2 = parametric_var(1_000_000, 0.4, horizon_days=1)
        assert v1 > 0
        assert v2 > v1

    def test_stress_scenarios_present(self) -> None:
        results = stress_scenarios(1_000_000, 0.2)
        assert any(r.scenario.startswith("spot") for r in results)
        assert any(r.scenario == "vol+50%" for r in results)


class TestMarketMaking:
    def test_spread_positive_and_symmetric_quotes(self) -> None:
        q = AvellanedaStoikov().quote(100, 0.0, gamma=0.1, sigma=0.2, time_left=1.0, k=1.5)
        assert q.optimal_spread > 0
        assert q.bid < q.reservation_price < q.ask

    def test_long_inventory_lowers_reservation_price(self) -> None:
        a = AvellanedaStoikov()
        flat = a.reservation_price(100, 0.0, gamma=0.1, sigma=0.2, time_left=1.0)
        long = a.reservation_price(100, 5.0, gamma=0.1, sigma=0.2, time_left=1.0)
        assert long < flat  # inventory risk skews quotes down


class TestPricingBranches:
    def test_bs_put_intrinsic_at_expiry(self) -> None:
        assert black_scholes_price(80, 100, 0.0, 0.0, 0.2, call=False) == 20

    def test_sabr_non_atm_smile(self) -> None:
        otm = sabr_implied_vol(100, 120, 1.0, alpha=0.2, beta=1.0, rho=-0.3, nu=0.4)
        assert otm > 0

    def test_greeks_at_expiry_branch(self) -> None:
        g = greeks(120, 100, 0.0, 0.0, 0.2, call=True)
        assert g.delta == 1.0
        assert g.gamma == 0.0


class TestService:
    def test_recommend_bundles_advisory_metrics(self) -> None:
        rec = QuantAdvisoryService().recommend(
            PricingModel.HESTON, 100, 100, 1.0, 0.0, sigma=0.2, position_value=1_000_000
        )
        assert rec.price > 0
        assert rec.var99 > 0
        assert rec.execution_allowed is False

    def test_service_price_all_models(self) -> None:
        svc = QuantAdvisoryService()
        bs = svc.price(PricingModel.BLACK_SCHOLES, 100, 100, 1.0, 0.0, sigma=0.2)
        bates = svc.price(PricingModel.BATES, 100, 100, 1.0, 0.0, sigma=0.2)
        assert bs > 0
        assert bates > 0

    def test_service_vol_surface_and_stress(self) -> None:
        svc = QuantAdvisoryService()
        surface = svc.vol_surface(100, 1.0, [90, 100, 110])
        assert len(surface) == 3
        assert all(p.implied_vol > 0 for p in surface)
        assert len(svc.stress(1_000_000, 0.2)) >= 1


class TestAdvisoryOnlyGuard:
    def test_quant_cannot_execute(self) -> None:
        assert QUANT_CAN_EXECUTE is False

    def test_service_exposes_no_execution_method(self) -> None:
        svc = QuantAdvisoryService()
        forbidden = {"execute", "place_order", "trade", "submit_order", "run_mm"}
        assert forbidden.isdisjoint(dir(svc))
