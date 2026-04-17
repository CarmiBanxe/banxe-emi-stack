"""
tests/test_savings/test_product_catalog.py — Unit tests for ProductCatalog
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.savings.models import SavingsAccountType
from services.savings.product_catalog import ProductCatalog


@pytest.fixture()
def catalog() -> ProductCatalog:
    return ProductCatalog()


def test_list_products_returns_five(catalog: ProductCatalog) -> None:
    assert len(catalog.list_products()) == 5


def test_list_products_easy_access_filter(catalog: ProductCatalog) -> None:
    result = catalog.list_products(SavingsAccountType.EASY_ACCESS)
    assert len(result) == 1
    assert result[0].account_type == SavingsAccountType.EASY_ACCESS


def test_list_products_fixed_3m_filter(catalog: ProductCatalog) -> None:
    result = catalog.list_products(SavingsAccountType.FIXED_TERM_3M)
    assert len(result) == 1


def test_list_products_fixed_12m_filter(catalog: ProductCatalog) -> None:
    result = catalog.list_products(SavingsAccountType.FIXED_TERM_12M)
    assert len(result) == 1


def test_list_products_notice_30d_filter(catalog: ProductCatalog) -> None:
    result = catalog.list_products(SavingsAccountType.NOTICE_30D)
    assert len(result) == 1


def test_get_product_easy_access(catalog: ProductCatalog) -> None:
    p = catalog.get_product("prod-easy-access")
    assert p is not None
    assert p.product_id == "prod-easy-access"


def test_get_product_fixed_12m(catalog: ProductCatalog) -> None:
    p = catalog.get_product("prod-fixed-12m")
    assert p is not None
    assert p.term_days == 365


def test_get_product_nonexistent(catalog: ProductCatalog) -> None:
    assert catalog.get_product("nonexistent") is None


def test_list_eligible_includes_easy_access_for_1_gbp(catalog: ProductCatalog) -> None:
    result = catalog.list_eligible_products(Decimal("1.00"))
    ids = [p.product_id for p in result]
    assert "prod-easy-access" in ids


def test_list_eligible_excludes_fixed_for_below_min(catalog: ProductCatalog) -> None:
    result = catalog.list_eligible_products(Decimal("499.99"))
    ids = [p.product_id for p in result]
    assert "prod-fixed-3m" not in ids
    assert "prod-fixed-12m" not in ids


def test_list_eligible_includes_fixed_at_min(catalog: ProductCatalog) -> None:
    result = catalog.list_eligible_products(Decimal("500.00"))
    ids = [p.product_id for p in result]
    assert "prod-fixed-3m" in ids


def test_list_eligible_excludes_notice_below_100(catalog: ProductCatalog) -> None:
    result = catalog.list_eligible_products(Decimal("99.99"))
    ids = [p.product_id for p in result]
    assert "prod-notice-30d" not in ids


def test_list_eligible_includes_notice_at_100(catalog: ProductCatalog) -> None:
    result = catalog.list_eligible_products(Decimal("100.00"))
    ids = [p.product_id for p in result]
    assert "prod-notice-30d" in ids


def test_get_product_count(catalog: ProductCatalog) -> None:
    assert catalog.get_product_count() == 5
