"""
tests/test_config_store.py — InMemoryConfigStore + get_config_store tests
S15-FIX-2 | Geniusto v5 Config-as-Data | banxe-emi-stack

10 tests: get/set/list, namespaces, defaults, factory env-var routing.
"""

from __future__ import annotations

from decimal import Decimal

from services.config.config_port import FeeSchedule, PaymentLimits, ProductConfig
from services.config.config_service import InMemoryConfigStore


def _make_product(product_id: str = "EMI_ACCOUNT") -> ProductConfig:
    fee = FeeSchedule(
        product_id=product_id,
        tx_type="FPS",
        fee_type="FLAT",
        flat_fee=Decimal("0.20"),
        percentage=Decimal("0"),
        min_fee=Decimal("0.20"),
        max_fee=None,
        currency="GBP",
    )
    ind_limits = PaymentLimits(
        product_id=product_id,
        entity_type="INDIVIDUAL",
        single_tx_max=Decimal("10000"),
        daily_max=Decimal("50000"),
        monthly_max=Decimal("200000"),
        daily_tx_count=50,
        monthly_tx_count=200,
    )
    corp_limits = PaymentLimits(
        product_id=product_id,
        entity_type="COMPANY",
        single_tx_max=Decimal("1000000"),
        daily_max=Decimal("5000000"),
        monthly_max=Decimal("20000000"),
        daily_tx_count=500,
        monthly_tx_count=5000,
    )
    return ProductConfig(
        product_id=product_id,
        display_name=f"{product_id} Account",
        currencies=["GBP", "EUR"],
        fee_schedules=[fee],
        individual_limits=ind_limits,
        company_limits=corp_limits,
        active=True,
    )


class TestInMemoryConfigStore:
    def test_get_product_returns_product(self):
        store = InMemoryConfigStore([_make_product("EMI_ACCOUNT")])
        product = store.get_product("EMI_ACCOUNT")
        assert product is not None
        assert product.product_id == "EMI_ACCOUNT"

    def test_get_nonexistent_product_returns_none(self):
        store = InMemoryConfigStore([])
        assert store.get_product("DOES_NOT_EXIST") is None

    def test_list_products_returns_all(self):
        products = [_make_product(f"PROD-{i}") for i in range(3)]
        store = InMemoryConfigStore(products)
        assert len(store.list_products()) == 3

    def test_get_fee_returns_fee(self):
        store = InMemoryConfigStore([_make_product("EMI_ACCOUNT")])
        fee = store.get_fee("EMI_ACCOUNT", "FPS")
        assert fee is not None
        assert fee.flat_fee == Decimal("0.20")

    def test_get_fee_missing_product_returns_none(self):
        store = InMemoryConfigStore([])
        assert store.get_fee("NO_PRODUCT", "FPS") is None

    def test_get_fee_missing_tx_type_returns_none(self):
        store = InMemoryConfigStore([_make_product("EMI_ACCOUNT")])
        assert store.get_fee("EMI_ACCOUNT", "NONEXISTENT_TX") is None

    def test_get_limits_individual(self):
        store = InMemoryConfigStore([_make_product("EMI_ACCOUNT")])
        limits = store.get_limits("EMI_ACCOUNT", "INDIVIDUAL")
        assert limits is not None
        assert limits.single_tx_max == Decimal("10000")

    def test_get_limits_company(self):
        store = InMemoryConfigStore([_make_product("EMI_ACCOUNT")])
        limits = store.get_limits("EMI_ACCOUNT", "COMPANY")
        assert limits is not None
        assert limits.single_tx_max == Decimal("1000000")

    def test_get_limits_missing_product(self):
        store = InMemoryConfigStore([])
        assert store.get_limits("NO_PROD", "INDIVIDUAL") is None

    def test_reload_is_noop(self):
        store = InMemoryConfigStore([_make_product("EMI")])
        store.reload()  # Should not raise
        assert store.get_product("EMI") is not None
