"""
tests/test_beneficiary_management/test_payment_rail_router.py
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.beneficiary_management.models import PaymentRail
from services.beneficiary_management.payment_rail_router import PaymentRailRouter


def _router() -> PaymentRailRouter:
    return PaymentRailRouter()


class TestFpsRouting:
    def test_gbp_uk_below_limit_routes_fps(self) -> None:
        router = _router()
        result = router.route(Decimal("1000.00"), "GBP", "GB")
        assert result["rail"] == PaymentRail.FPS.value

    def test_fps_settlement_instant(self) -> None:
        router = _router()
        result = router.route(Decimal("100.00"), "GBP", "GB")
        assert result["estimated_settlement"] == "instant"

    def test_fps_boundary_exactly_250k(self) -> None:
        router = _router()
        result = router.route(Decimal("250000.00"), "GBP", "GB")
        assert result["rail"] == PaymentRail.FPS.value

    def test_fps_fee_low(self) -> None:
        router = _router()
        result = router.route(Decimal("500.00"), "GBP", "GB")
        assert result["fee_indicator"] == "low"


class TestChapsRouting:
    def test_gbp_uk_above_250k_routes_chaps(self) -> None:
        router = _router()
        result = router.route(Decimal("250000.01"), "GBP", "GB")
        assert result["rail"] == PaymentRail.CHAPS.value

    def test_chaps_settlement_same_day(self) -> None:
        router = _router()
        result = router.route(Decimal("500000.00"), "GBP", "GB")
        assert result["estimated_settlement"] == "same-day"

    def test_chaps_fee_high(self) -> None:
        router = _router()
        result = router.route(Decimal("1000000.00"), "GBP", "GB")
        assert result["fee_indicator"] == "high"


class TestSepaRouting:
    def test_eur_sepa_country_routes_sepa(self) -> None:
        router = _router()
        result = router.route(Decimal("500.00"), "EUR", "DE")
        assert result["rail"] == PaymentRail.SEPA.value

    def test_sepa_settlement_t1(self) -> None:
        router = _router()
        result = router.route(Decimal("500.00"), "EUR", "FR")
        assert result["estimated_settlement"] == "T+1"

    def test_sepa_with_nl(self) -> None:
        router = _router()
        result = router.route(Decimal("200.00"), "EUR", "NL")
        assert result["rail"] == PaymentRail.SEPA.value

    def test_sepa_fee_low(self) -> None:
        router = _router()
        result = router.route(Decimal("100.00"), "EUR", "ES")
        assert result["fee_indicator"] == "low"


class TestSwiftRouting:
    def test_non_sepa_eur_routes_swift(self) -> None:
        router = _router()
        result = router.route(Decimal("500.00"), "EUR", "US")
        assert result["rail"] == PaymentRail.SWIFT.value

    def test_usd_routes_swift(self) -> None:
        router = _router()
        result = router.route(Decimal("1000.00"), "USD", "US")
        assert result["rail"] == PaymentRail.SWIFT.value

    def test_swift_settlement_t5(self) -> None:
        router = _router()
        result = router.route(Decimal("500.00"), "USD", "JP")
        assert result["estimated_settlement"] == "T+5"

    def test_swift_fee_high(self) -> None:
        router = _router()
        result = router.route(Decimal("100.00"), "JPY", "JP")
        assert result["fee_indicator"] == "high"


class TestValidation:
    def test_zero_amount_raises(self) -> None:
        router = _router()
        with pytest.raises(ValueError, match="positive"):
            router.route(Decimal("0"), "GBP", "GB")

    def test_negative_amount_raises(self) -> None:
        router = _router()
        with pytest.raises(ValueError, match="positive"):
            router.route(Decimal("-1.00"), "GBP", "GB")

    def test_amount_as_string_in_result(self) -> None:
        router = _router()
        result = router.route(Decimal("99.99"), "GBP", "GB")
        assert result["amount"] == "99.99"


class TestRailDetails:
    def test_get_fps_details(self) -> None:
        router = _router()
        result = router.get_rail_details(PaymentRail.FPS)
        assert result["rail"] == "FPS"
        assert result["estimated_settlement"] == "instant"

    def test_get_chaps_details(self) -> None:
        router = _router()
        result = router.get_rail_details("CHAPS")
        assert result["estimated_settlement"] == "same-day"

    def test_list_rails_count(self) -> None:
        router = _router()
        result = router.list_rails()
        assert result["count"] == 5
