"""
services/insurance/product_catalog.py
IL-INS-01 | Phase 26

Product catalog with card-tier filtering.
"""

from __future__ import annotations

from services.insurance.models import (
    CoverageType,
    InMemoryInsuranceProductStore,
    InsuranceProduct,
    InsuranceProductStorePort,
)


class ProductCatalog:
    """Filters insurance products by card tier and coverage type."""

    def __init__(self, store: InsuranceProductStorePort | None = None) -> None:
        self._store: InsuranceProductStorePort = store or InMemoryInsuranceProductStore()

    def get_products_for_tier(self, card_tier: str) -> list[InsuranceProduct]:
        all_products = self._store.list_products()
        if card_tier == "PREMIUM":
            return all_products
        if card_tier == "STANDARD":
            excluded = {CoverageType.PAYMENT_PROTECTION}
            return [p for p in all_products if p.coverage_type not in excluded]
        # Basic / unknown tier: TRAVEL + PURCHASE only
        allowed = {CoverageType.TRAVEL, CoverageType.PURCHASE}
        return [p for p in all_products if p.coverage_type in allowed]

    def get_product(self, product_id: str) -> InsuranceProduct | None:
        return self._store.get(product_id)

    def list_all(self) -> list[InsuranceProduct]:
        return self._store.list_products()


__all__ = ["ProductCatalog"]
