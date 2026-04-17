"""
services/lending/lending_agent.py — Lending orchestration agent
IL-LCE-01 | Phase 25 | banxe-emi-stack

High-level agent that coordinates all lending subsystems.
ALL credit decisions return HITL_REQUIRED (I-27, FCA CONC).
"""

from __future__ import annotations

from decimal import Decimal

from services.lending.arrears_manager import ArrearsManager
from services.lending.credit_scorer import CreditScorer
from services.lending.loan_originator import LoanOriginator
from services.lending.models import IFRSStage, RepaymentType
from services.lending.provisioning_engine import ProvisioningEngine
from services.lending.repayment_engine import RepaymentEngine


class LendingAgent:
    """Orchestrates the lending lifecycle: apply, score, decide, schedule, monitor."""

    def __init__(self) -> None:
        self._scorer = CreditScorer()
        self._originator = LoanOriginator()
        self._repayment = RepaymentEngine()
        self._arrears = ArrearsManager()
        self._provisioning = ProvisioningEngine()

    def apply_for_loan(
        self,
        customer_id: str,
        product_id: str,
        requested_amount_str: str,
        term_months: int,
    ) -> dict:
        """Apply for a loan, score the customer, and return HITL_REQUIRED decision.

        Per I-27, all credit decisions require Compliance Officer approval (FCA CONC).

        Args:
            customer_id: Applicant customer ID.
            product_id: Loan product ID.
            requested_amount_str: Requested amount as decimal string.
            term_months: Requested term in months.

        Returns:
            dict with status=HITL_REQUIRED, application_id, credit_score.
        """
        requested_amount = Decimal(requested_amount_str)

        # Score using stub values (income=35000, age=24 months, aml_risk=10)
        credit_score = self._scorer.score_customer(
            customer_id=customer_id,
            income=Decimal("35000"),
            account_age_months=24,
            aml_risk_score=Decimal("10"),
        )

        app = self._originator.apply(
            customer_id=customer_id,
            product_id=product_id,
            requested_amount=requested_amount,
            requested_term_months=term_months,
        )

        decision_result = self._originator.decide(
            application_id=app.application_id,
            credit_score=credit_score,
        )

        # I-27: always return HITL_REQUIRED for credit decisions
        return {
            "status": "HITL_REQUIRED",
            "application_id": app.application_id,
            "credit_score": str(credit_score.score),
            "outcome": decision_result["decision"].outcome.value,
        }

    def get_repayment_schedule(self, application_id: str) -> dict:
        """Generate and return a repayment schedule for an application.

        Args:
            application_id: Loan application ID.

        Returns:
            Serialised RepaymentSchedule or error dict.
        """
        app = self._originator.get_application(application_id)
        if app is None:
            return {"error": f"Application not found: {application_id}"}

        product = self._originator._products.get(app.product_id)
        if product is None:
            return {"error": f"Product not found: {app.product_id}"}

        schedule = self._repayment.generate_schedule(
            application_id=application_id,
            principal=app.requested_amount,
            rate=product.interest_rate,
            term_months=app.requested_term_months,
            repayment_type=RepaymentType.ANNUITY,
        )
        return {
            "schedule_id": schedule.schedule_id,
            "application_id": schedule.application_id,
            "total_amount": str(schedule.total_amount),
            "monthly_payment": str(schedule.monthly_payment),
            "repayment_type": schedule.repayment_type.value,
            "installment_count": len(schedule.installments),
            "installments": schedule.installments,
        }

    def check_arrears_status(
        self,
        application_id: str,
        customer_id: str,
        days_overdue: int,
        outstanding_amount_str: str,
    ) -> dict:
        """Record and return arrears status for an application.

        Args:
            application_id: Loan application ID.
            customer_id: Customer ID.
            days_overdue: Days the payment is overdue.
            outstanding_amount_str: Outstanding balance as decimal string.

        Returns:
            Serialised ArrearsRecord.
        """
        outstanding = Decimal(outstanding_amount_str)
        record = self._arrears.check_arrears(
            application_id=application_id,
            customer_id=customer_id,
            days_overdue=days_overdue,
            outstanding_amount=outstanding,
        )
        return {
            "record_id": record.record_id,
            "application_id": record.application_id,
            "customer_id": record.customer_id,
            "stage": record.stage.value,
            "days_overdue": record.days_overdue,
            "outstanding_amount": str(record.outstanding_amount),
            "recorded_at": record.recorded_at.isoformat(),
        }

    def generate_provision_report(
        self,
        application_id: str,
        ifrs_stage_str: str,
        exposure_str: str,
    ) -> dict:
        """Compute and return an IFRS 9 ECL provision record.

        Args:
            application_id: Loan application ID.
            ifrs_stage_str: IFRS stage string (STAGE_1, STAGE_2, STAGE_3).
            exposure_str: Exposure at default as decimal string.

        Returns:
            Serialised ProvisionRecord with ECL breakdown.
        """
        ifrs_stage = IFRSStage(ifrs_stage_str)
        exposure = Decimal(exposure_str)
        record = self._provisioning.compute_ecl(
            application_id=application_id,
            ifrs_stage=ifrs_stage,
            exposure_at_default=exposure,
        )
        return {
            "record_id": record.record_id,
            "application_id": record.application_id,
            "ifrs_stage": record.ifrs_stage.value,
            "ecl_amount": str(record.ecl_amount),
            "probability_of_default": str(record.probability_of_default),
            "exposure_at_default": str(record.exposure_at_default),
            "computed_at": record.computed_at.isoformat(),
        }
