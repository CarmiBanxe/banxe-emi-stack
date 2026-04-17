"""
services/lending/loan_originator.py — Loan application and decision engine
IL-LCE-01 | Phase 25 | banxe-emi-stack

Handles loan applications, credit decisions, and disbursement.
All credit decisions are HITL_REQUIRED (I-27, FCA CONC).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.lending.models import (
    CreditDecision,
    CreditDecisionStorePort,
    CreditScore,
    DecisionOutcome,
    InMemoryCreditDecisionStore,
    InMemoryLoanApplicationStore,
    InMemoryLoanProductStore,
    LoanApplication,
    LoanApplicationStorePort,
    LoanProductStorePort,
    LoanStatus,
)


class LoanOriginator:
    """Manages the full loan origination lifecycle: apply → decide → disburse.

    All credit decisions wrap with HITL_REQUIRED flag per I-27 (FCA CONC).
    """

    def __init__(
        self,
        product_store: LoanProductStorePort | None = None,
        application_store: LoanApplicationStorePort | None = None,
        decision_store: CreditDecisionStorePort | None = None,
    ) -> None:
        self._products = product_store or InMemoryLoanProductStore()
        self._applications = application_store or InMemoryLoanApplicationStore()
        self._decisions = decision_store or InMemoryCreditDecisionStore()

    def apply(
        self,
        customer_id: str,
        product_id: str,
        requested_amount: Decimal,
        requested_term_months: int,
    ) -> LoanApplication:
        """Create a new loan application in PENDING status.

        Args:
            customer_id: Applicant customer ID.
            product_id: Catalogue product being applied for.
            requested_amount: Amount requested (Decimal, must be <= product max).
            requested_term_months: Term requested (must be <= product max).

        Returns:
            New LoanApplication with PENDING status.

        Raises:
            ValueError: If amount or term exceeds product limits, or product not found.
        """
        product = self._products.get(product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")

        if requested_amount > product.max_amount:
            raise ValueError(
                f"Requested amount {requested_amount} exceeds product max {product.max_amount}"
            )
        if requested_term_months > product.max_term_months:
            raise ValueError(
                f"Requested term {requested_term_months} exceeds product max {product.max_term_months}"
            )

        app = LoanApplication(
            application_id=str(uuid.uuid4()),
            customer_id=customer_id,
            product_id=product_id,
            requested_amount=requested_amount,
            requested_term_months=requested_term_months,
            status=LoanStatus.PENDING,
            applied_at=datetime.now(UTC),
        )
        self._applications.save(app)
        return app

    def decide(
        self,
        application_id: str,
        credit_score: CreditScore,
        actor: str = "system",
    ) -> dict:
        """Apply underwriting rules and return HITL_REQUIRED decision wrapper.

        Per I-27 (FCA CONC), ALL credit decisions require human approval.
        The decision record is stored; the caller receives a HITL gate response.

        Args:
            application_id: Application to decide on.
            credit_score: Pre-computed CreditScore for the applicant.
            actor: Who or what initiated the decision.

        Returns:
            dict with keys: status="HITL_REQUIRED", decision (CreditDecision),
            application (updated LoanApplication).

        Raises:
            ValueError: If application not found or not in PENDING status.
        """
        app = self._applications.get(application_id)
        if app is None:
            raise ValueError(f"Application not found: {application_id}")
        if app.status != LoanStatus.PENDING:
            raise ValueError(f"Application {application_id} is not in PENDING status")

        product = self._products.get(app.product_id)
        if product is None:
            raise ValueError(f"Product not found: {app.product_id}")

        if (
            credit_score.score >= product.min_credit_score
            and app.requested_amount <= product.max_amount
        ):
            outcome = DecisionOutcome.APPROVED
            approved_amount: Decimal | None = app.requested_amount
            approved_rate: Decimal | None = product.interest_rate
            new_status = LoanStatus.APPROVED
        else:
            outcome = DecisionOutcome.DECLINED
            approved_amount = None
            approved_rate = None
            new_status = LoanStatus.DECLINED

        now = datetime.now(UTC)
        decision = CreditDecision(
            decision_id=str(uuid.uuid4()),
            application_id=application_id,
            outcome=outcome,
            credit_score=credit_score.score,
            approved_amount=approved_amount,
            approved_rate=approved_rate,
            decided_at=now,
            decided_by=actor,
        )
        self._decisions.save(decision)

        updated_app = replace(app, status=new_status, decided_at=now)
        self._applications.save(updated_app)

        # I-27: ALL credit decisions require HITL — FCA CONC compliance
        return {
            "status": "HITL_REQUIRED",
            "decision": decision,
            "application": updated_app,
        }

    def disburse(self, application_id: str, actor: str) -> LoanApplication:
        """Transition an APPROVED application to DISBURSED status.

        Args:
            application_id: Application to disburse.
            actor: Authorising actor (must be human per HITL gate).

        Returns:
            Updated LoanApplication with DISBURSED status.

        Raises:
            ValueError: If application not found or not in APPROVED status.
        """
        app = self._applications.get(application_id)
        if app is None:
            raise ValueError(f"Application not found: {application_id}")
        if app.status != LoanStatus.APPROVED:
            raise ValueError(
                f"Cannot disburse: application {application_id} is in status {app.status}"
            )

        updated = replace(app, status=LoanStatus.DISBURSED)
        self._applications.save(updated)
        return updated

    def get_application(self, application_id: str) -> LoanApplication | None:
        """Retrieve a loan application by ID."""
        return self._applications.get(application_id)
