"""
tests/test_insurance/test_product_catalog.py
IL-INS-01 | Phase 26 — 15 tests for ProductCatalog tier filtering.
"""

from __future__ import annotations

import pytest

from services.insurance.models import CoverageType, InMemoryInsuranceProductStore
from services.insurance.product_catalog import ProductCatalog


@pytest.fixture
def catalog() -> ProductCatalog:
    return ProductCatalog(store=InMemoryInsuranceProductStore())


# ── Tier filtering ────────────────────────────────────────────────────────────


def test_premium_tier_returns_all_four(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("PREMIUM")
    assert len(products) == 4


def test_standard_tier_returns_three(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("STANDARD")
    assert len(products) == 3


def test_standard_tier_excludes_payment_protection(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("STANDARD")
    types = [p.coverage_type for p in products]
    assert CoverageType.PAYMENT_PROTECTION not in types


def test_standard_tier_includes_travel(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("STANDARD")
    types = [p.coverage_type for p in products]
    assert CoverageType.TRAVEL in types


def test_standard_tier_includes_device(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("STANDARD")
    types = [p.coverage_type for p in products]
    assert CoverageType.DEVICE in types


def test_basic_tier_returns_two(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("BASIC")
    assert len(products) == 2


def test_basic_tier_includes_travel(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("BASIC")
    types = [p.coverage_type for p in products]
    assert CoverageType.TRAVEL in types


def test_basic_tier_includes_purchase(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("BASIC")
    types = [p.coverage_type for p in products]
    assert CoverageType.PURCHASE in types


def test_basic_tier_excludes_device(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("BASIC")
    types = [p.coverage_type for p in products]
    assert CoverageType.DEVICE not in types


def test_unknown_tier_returns_two(catalog: ProductCatalog) -> None:
    products = catalog.get_products_for_tier("UNKNOWN_TIER")
    assert len(products) == 2


# ── get_product ───────────────────────────────────────────────────────────────


def test_get_product_found(catalog: ProductCatalog) -> None:
    product = catalog.get_product("ins-001")
    assert product is not None
    assert product.product_id == "ins-001"


def test_get_product_not_found(catalog: ProductCatalog) -> None:
    product = catalog.get_product("does-not-exist")
    assert product is None


def test_get_product_ins003_lloyds(catalog: ProductCatalog) -> None:
    from services.insurance.models import UnderwriterType

    product = catalog.get_product("ins-003")
    assert product is not None
    assert product.underwriter == UnderwriterType.LLOYDS_STUB


# ── list_all ──────────────────────────────────────────────────────────────────


def test_list_all_returns_four(catalog: ProductCatalog) -> None:
    products = catalog.list_all()
    assert len(products) == 4


def test_list_all_includes_munich_re(catalog: ProductCatalog) -> None:
    from services.insurance.models import UnderwriterType

    products = catalog.list_all()
    underwriters = [p.underwriter for p in products]
    assert UnderwriterType.MUNICH_RE_STUB in underwriters
