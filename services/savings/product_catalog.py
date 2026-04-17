"""
services/savings/product_catalog.py — Savings product catalog
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

from services.savings.models import (
    InMemorySavingsProductStore,
    SavingsAccountType,
    SavingsProduct,
    SavingsProductPort,
)


class ProductCatalog:
    def __init__(self, product_store: SavingsProductPort | None = None) -> None:
        self._store = product_store or InMemorySavingsProductStore()

    def get_product(self, product_id: str) -> SavingsProduct | None:
        return self._store.get(product_id)

    def list_products(self, account_type: SavingsAccountType | None = None) -> list[SavingsProduct]:
        products = self._store.list_active()
        if account_type is not None:
            products = [p for p in products if p.account_type == account_type]
        return products

    def list_eligible_products(self, deposit_amount: Decimal) -> list[SavingsProduct]:
        """Return products where deposit_amount >= min_deposit."""
        return [p for p in self._store.list_active() if deposit_amount >= p.min_deposit]

    def get_product_count(self) -> int:
        return len(self._store.list_active())
