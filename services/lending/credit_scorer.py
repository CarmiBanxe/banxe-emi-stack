"""
services/lending/credit_scorer.py — Customer credit scoring engine
IL-LCE-01 | Phase 25 | banxe-emi-stack

Computes a 0-1000 composite credit score from income, account history,
and AML risk. All arithmetic uses Decimal (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.lending.models import CreditScore


class CreditScorer:
    """Scores customer creditworthiness on a 0-1000 Decimal scale.

    Score components:
    - income_factor: up to 400 pts, based on annual income vs £50k benchmark
    - history_factor: up to 300 pts, based on account age vs 24-month benchmark
    - aml_risk_factor: up to 300 pts, inversely proportional to AML risk score
    """

    def __init__(self) -> None:
        self._scores: dict[str, CreditScore] = {}

    def score_customer(
        self,
        customer_id: str,
        income: Decimal,
        account_age_months: int,
        aml_risk_score: Decimal,
    ) -> CreditScore:
        """Compute and store a credit score for the given customer.

        Args:
            customer_id: Customer identifier.
            income: Annual income as Decimal.
            account_age_months: Months since account opening.
            aml_risk_score: AML risk score (0=no risk, 100=max risk) as Decimal.

        Returns:
            CreditScore dataclass with all factor breakdowns.
        """
        income_factor = min(Decimal("1.0"), income / Decimal("50000")) * Decimal("400")
        history_factor = min(Decimal("1.0"), Decimal(account_age_months) / Decimal("24")) * Decimal(
            "300"
        )
        aml_risk_factor = (
            Decimal("1.0") - min(Decimal("1.0"), aml_risk_score / Decimal("100"))
        ) * Decimal("300")
        total_score = income_factor + history_factor + aml_risk_factor

        score = CreditScore(
            score_id=str(uuid.uuid4()),
            customer_id=customer_id,
            score=total_score,
            income_factor=income_factor,
            history_factor=history_factor,
            aml_risk_factor=aml_risk_factor,
            computed_at=datetime.now(UTC),
        )
        self._scores[customer_id] = score
        return score

    def get_latest_score(self, customer_id: str) -> CreditScore | None:
        """Retrieve the most recently computed score for a customer.

        Args:
            customer_id: Customer identifier.

        Returns:
            Latest CreditScore or None if not yet scored.
        """
        return self._scores.get(customer_id)
