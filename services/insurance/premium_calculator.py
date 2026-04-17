"""
services/insurance/premium_calculator.py
IL-INS-01 | Phase 26

Risk-adjusted premium calculation. All amounts Decimal — never float (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.insurance.models import (
    InMemoryInsuranceProductStore,
    InsuranceProduct,
    InsuranceProductStorePort,
    RiskAssessment,
)


class PremiumCalculator:
    """Calculates risk-adjusted premiums. Pure Decimal arithmetic throughout."""

    def __init__(self, store: InsuranceProductStorePort | None = None) -> None:
        self._store: InsuranceProductStorePort = store or InMemoryInsuranceProductStore()

    def calculate(
        self,
        product: InsuranceProduct,
        coverage_amount: Decimal,
        term_days: int,
        risk_score: Decimal,
    ) -> Decimal:
        """Return premium rounded to 2 d.p. — no float used anywhere."""
        base = product.base_premium
        coverage_factor = coverage_amount / product.max_coverage
        risk_factor = Decimal("1.0") + (risk_score / Decimal("100")) * Decimal("0.5")
        term_factor = Decimal(str(term_days)) / Decimal("30")
        premium = base * coverage_factor * risk_factor * term_factor
        return premium.quantize(Decimal("0.01"))

    def assess_risk(
        self,
        customer_id: str,
        product_id: str,
        coverage_amount: Decimal,
    ) -> RiskAssessment:
        """Stub: flat risk score of 25.0 for all customers."""
        product = self._store.get(product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        risk_score = Decimal("25.0")
        recommended_premium = self.calculate(product, coverage_amount, 30, risk_score)
        return RiskAssessment(
            assessment_id=str(uuid.uuid4()),
            customer_id=customer_id,
            product_id=product_id,
            risk_score=risk_score,
            recommended_premium=recommended_premium,
            assessed_at=datetime.now(UTC),
        )


__all__ = ["PremiumCalculator"]
