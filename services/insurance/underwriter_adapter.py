"""
services/insurance/underwriter_adapter.py
IL-INS-01 | Phase 26

Stub underwriter adapter — Lloyd's / Munich Re style external integration.
Production implementation replaces with real HTTP clients.
"""

from __future__ import annotations

import uuid

from services.insurance.models import (
    InMemoryInsuranceProductStore,
    InsuranceProductStorePort,
    Policy,
)


class UnderwriterAdapter:
    """Stub adapter for external underwriter APIs."""

    def __init__(self, product_store: InsuranceProductStorePort | None = None) -> None:
        self._product_store: InsuranceProductStorePort = (
            product_store or InMemoryInsuranceProductStore()
        )

    def submit_for_underwriting(self, policy: Policy) -> dict:
        product = self._product_store.get(policy.product_id)
        underwriter = product.underwriter.value if product else "INTERNAL"
        return {
            "status": "ACCEPTED",
            "underwriter": underwriter,
            "reference": f"UW-{uuid.uuid4().hex[:8].upper()}",
        }

    def check_underwriting_status(self, reference: str) -> dict:
        return {
            "status": "BOUND",
            "reference": reference,
        }


__all__ = ["UnderwriterAdapter"]
