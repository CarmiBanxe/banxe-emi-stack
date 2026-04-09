"""
test_config_service.py — Config-as-Data: YAMLConfigStore + fee/limit calculations
Geniusto v5 Pattern #6 | FCA: COBS 6, PSR 2017 Reg.67
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from services.config.config_port import FeeSchedule, PaymentLimits, ProductConfig
from services.config.config_service import InMemoryConfigStore, YAMLConfigStore

yaml = pytest.importorskip("yaml", reason="pyyaml not installed")

YAML_PATH = Path(__file__).parent.parent / "config" / "banxe_config.yaml"


# ── YAML store — loading ───────────────────────────────────────────────────────


class TestYAMLConfigStore:
    @pytest.fixture
    def store(self):
        return YAMLConfigStore(YAML_PATH)

    def test_loads_emi_account(self, store):
        product = store.get_product("EMI_ACCOUNT")
        assert product is not None
        assert product.display_name == "Banxe EMI Account"

    def test_loads_all_four_products(self, store):
        products = store.list_products()
        ids = {p.product_id for p in products}
        assert ids == {"EMI_ACCOUNT", "BUSINESS_ACCOUNT", "FX_ACCOUNT", "PREPAID_CARD"}

    def test_active_flag(self, store):
        assert store.get_product("EMI_ACCOUNT").active is True

    def test_currencies(self, store):
        product = store.get_product("EMI_ACCOUNT")
        assert "GBP" in product.currencies
        assert "EUR" in product.currencies

    def test_unknown_product_returns_none(self, store):
        assert store.get_product("NONEXISTENT") is None

    def test_reload_idempotent(self, store):
        store.reload()
        assert store.get_product("EMI_ACCOUNT") is not None


# ── Fee schedules ──────────────────────────────────────────────────────────────


class TestFeeSchedules:
    @pytest.fixture
    def store(self):
        return YAMLConfigStore(YAML_PATH)

    def test_fps_fee_exists(self, store):
        fee = store.get_fee("EMI_ACCOUNT", "FPS")
        assert fee is not None
        assert fee.fee_type == "FLAT"

    def test_fps_fee_is_20p(self, store):
        fee = store.get_fee("EMI_ACCOUNT", "FPS")
        assert fee.flat_fee == Decimal("0.20")

    def test_fx_fee_is_percentage(self, store):
        fee = store.get_fee("EMI_ACCOUNT", "FX")
        assert fee.fee_type == "PERCENTAGE"
        assert fee.percentage == Decimal("0.0025")

    def test_fx_fee_calculation_small(self, store):
        fee = store.get_fee("EMI_ACCOUNT", "FX")
        # 0.25% of £100 = £0.25, but min_fee = £1.00
        assert fee.calculate(Decimal("100")) == Decimal("1.00")

    def test_fx_fee_calculation_large(self, store):
        fee = store.get_fee("EMI_ACCOUNT", "FX")
        # 0.25% of £10,000 = £25.00
        assert fee.calculate(Decimal("10000")) == Decimal("25.00")

    def test_fx_fee_capped_at_max(self, store):
        fee = store.get_fee("EMI_ACCOUNT", "FX")
        # 0.25% of £300,000 = £750, but max_fee = £500
        assert fee.calculate(Decimal("300000")) == Decimal("500.00")

    def test_unknown_tx_type_returns_none(self, store):
        assert store.get_fee("EMI_ACCOUNT", "CHAPS") is None

    def test_business_fx_rate_lower_than_emi(self, store):
        emi_fx = store.get_fee("EMI_ACCOUNT", "FX")
        biz_fx = store.get_fee("BUSINESS_ACCOUNT", "FX")
        assert biz_fx.percentage < emi_fx.percentage  # Business gets better rate

    def test_prepaid_card_fx_higher(self, store):
        prepaid_fx = store.get_fee("PREPAID_CARD", "FX")
        emi_fx = store.get_fee("EMI_ACCOUNT", "FX")
        assert prepaid_fx.percentage > emi_fx.percentage  # Prepaid = higher spread

    def test_fee_schedule_frozen(self, store):
        fee = store.get_fee("EMI_ACCOUNT", "FPS")
        with pytest.raises((AttributeError, TypeError)):
            fee.flat_fee = Decimal("1.00")  # type: ignore[misc]


# ── Payment limits ─────────────────────────────────────────────────────────────


class TestPaymentLimits:
    @pytest.fixture
    def store(self):
        return YAMLConfigStore(YAML_PATH)

    def test_individual_limits_exist(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits is not None
        assert limits.entity_type == "INDIVIDUAL"

    def test_company_limits_exist(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "COMPANY")
        assert limits is not None
        assert limits.entity_type == "COMPANY"

    def test_company_limits_higher_than_individual(self, store):
        ind = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        corp = store.get_limits("EMI_ACCOUNT", "COMPANY")
        assert corp.single_tx_max > ind.single_tx_max
        assert corp.daily_max > ind.daily_max
        assert corp.monthly_max > ind.monthly_max

    def test_individual_single_tx_50k(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits.single_tx_max == Decimal("50000")

    def test_company_single_tx_500k(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "COMPANY")
        assert limits.single_tx_max == Decimal("500000")

    def test_check_single_within_limit(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits.check_single(Decimal("1000")) is True

    def test_check_single_exceeds_limit(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits.check_single(Decimal("100000")) is False

    def test_check_daily_within(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits.check_daily(Decimal("1000"), Decimal("0"), 0) is True

    def test_check_daily_exceeds_amount(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        # daily_max = 25,000
        assert limits.check_daily(Decimal("1000"), Decimal("24500"), 1) is False

    def test_check_daily_exceeds_count(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        # daily_tx_count = 10
        assert limits.check_daily(Decimal("1"), Decimal("0"), 10) is False

    def test_check_monthly_within(self, store):
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits.check_monthly(Decimal("5000"), Decimal("0"), 0) is True

    def test_unknown_entity_type_returns_none(self, store):
        assert store.get_limits("EMI_ACCOUNT", "ROBOT") is None


# ── InMemoryConfigStore ────────────────────────────────────────────────────────


class TestInMemoryConfigStore:
    def _make_product(self) -> ProductConfig:
        fee = FeeSchedule(
            product_id="TEST",
            tx_type="FPS",
            fee_type="FLAT",
            flat_fee=Decimal("0.50"),
            percentage=Decimal("0"),
            min_fee=Decimal("0.50"),
            max_fee=None,
        )
        limits = PaymentLimits(
            product_id="TEST",
            entity_type="INDIVIDUAL",
            single_tx_max=Decimal("10000"),
            daily_max=Decimal("5000"),
            monthly_max=Decimal("20000"),
            daily_tx_count=5,
            monthly_tx_count=50,
        )
        return ProductConfig(
            product_id="TEST",
            display_name="Test Product",
            currencies=["GBP"],
            fee_schedules=[fee],
            individual_limits=limits,
            company_limits=limits,
        )

    def test_get_injected_product(self):
        product = self._make_product()
        store = InMemoryConfigStore([product])
        assert store.get_product("TEST") is not None

    def test_list_products(self):
        store = InMemoryConfigStore([self._make_product()])
        assert len(store.list_products()) == 1

    def test_get_fee(self):
        store = InMemoryConfigStore([self._make_product()])
        fee = store.get_fee("TEST", "FPS")
        assert fee.flat_fee == Decimal("0.50")

    def test_reload_noop(self):
        store = InMemoryConfigStore([self._make_product()])
        store.reload()  # Should not raise
        assert store.get_product("TEST") is not None


# ── FeeSchedule.calculate edge cases ──────────────────────────────────────────


class TestFeeCalculate:
    def test_flat_fee(self):
        fee = FeeSchedule(
            product_id="P",
            tx_type="FPS",
            fee_type="FLAT",
            flat_fee=Decimal("0.20"),
            percentage=Decimal("0"),
            min_fee=Decimal("0.20"),
            max_fee=None,
        )
        assert fee.calculate(Decimal("1000")) == Decimal("0.20")

    def test_percentage_with_min(self):
        fee = FeeSchedule(
            product_id="P",
            tx_type="FX",
            fee_type="PERCENTAGE",
            flat_fee=Decimal("0"),
            percentage=Decimal("0.001"),  # 0.1%
            min_fee=Decimal("2.00"),
            max_fee=None,
        )
        # 0.1% of £50 = £0.05 → raised to min £2.00
        assert fee.calculate(Decimal("50")) == Decimal("2.00")

    def test_percentage_above_min(self):
        fee = FeeSchedule(
            product_id="P",
            tx_type="FX",
            fee_type="PERCENTAGE",
            flat_fee=Decimal("0"),
            percentage=Decimal("0.001"),
            min_fee=Decimal("2.00"),
            max_fee=None,
        )
        # 0.1% of £5,000 = £5.00 → above min
        assert fee.calculate(Decimal("5000")) == Decimal("5.00")

    def test_max_fee_cap(self):
        fee = FeeSchedule(
            product_id="P",
            tx_type="FX",
            fee_type="PERCENTAGE",
            flat_fee=Decimal("0"),
            percentage=Decimal("0.01"),  # 1%
            min_fee=Decimal("1.00"),
            max_fee=Decimal("100.00"),
        )
        # 1% of £50,000 = £500 → capped at £100
        assert fee.calculate(Decimal("50000")) == Decimal("100.00")

    def test_mixed_fee(self):
        fee = FeeSchedule(
            product_id="P",
            tx_type="SEPA",
            fee_type="MIXED",
            flat_fee=Decimal("0.50"),
            percentage=Decimal("0.001"),  # 0.1%
            min_fee=Decimal("0.50"),
            max_fee=None,
        )
        # 0.50 + 0.1% of £1000 = £0.50 + £1.00 = £1.50
        assert fee.calculate(Decimal("1000")) == Decimal("1.50")
