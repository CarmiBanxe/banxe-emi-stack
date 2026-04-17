"""
services/lending/repayment_engine.py — Loan repayment schedule calculator
IL-LCE-01 | Phase 25 | banxe-emi-stack

Generates amortisation schedules and processes repayments.
Uses Decimal arithmetic exclusively — NO float, NO numpy (I-01).
All monetary values in schedule installments stored as strings (I-05).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
import uuid

from services.lending.models import (
    InMemoryLoanApplicationStore,
    LoanApplicationStorePort,
    RepaymentSchedule,
    RepaymentType,
)


class RepaymentEngine:
    """Generates amortisation schedules and handles repayment processing."""

    def __init__(
        self,
        application_store: LoanApplicationStorePort | None = None,
    ) -> None:
        self._applications = application_store or InMemoryLoanApplicationStore()
        self._schedules: dict[str, RepaymentSchedule] = {}

    def generate_schedule(
        self,
        application_id: str,
        principal: Decimal,
        rate: Decimal,
        term_months: int,
        repayment_type: RepaymentType,
    ) -> RepaymentSchedule:
        """Generate an amortisation schedule for a loan.

        Args:
            application_id: Associated loan application.
            principal: Loan principal amount (Decimal).
            rate: Annual interest rate as decimal (e.g. Decimal("0.0499")).
            term_months: Number of monthly installments.
            repayment_type: ANNUITY (equal payments) or LINEAR (equal principal).

        Returns:
            RepaymentSchedule with all installments as string amounts (I-05).
        """
        monthly_rate = rate / Decimal("12")
        installments: list[dict] = []
        balance = principal
        total = Decimal("0")

        if repayment_type == RepaymentType.ANNUITY:
            monthly_payment = self._annuity_payment(principal, monthly_rate, term_months)
            for month in range(1, term_months + 1):
                interest = (balance * monthly_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
                principal_part = (monthly_payment - interest).quantize(
                    Decimal("0.01"), ROUND_HALF_UP
                )
                # Last installment: clear remaining balance
                if month == term_months:
                    principal_part = balance
                    payment = (principal_part + interest).quantize(Decimal("0.01"), ROUND_HALF_UP)
                else:
                    payment = monthly_payment
                balance = (balance - principal_part).quantize(Decimal("0.01"), ROUND_HALF_UP)
                total += payment
                installments.append(
                    {
                        "month": month,
                        "payment": str(payment),
                        "principal": str(principal_part),
                        "interest": str(interest),
                        "balance": str(balance),
                    }
                )
        else:  # LINEAR
            principal_installment = (principal / Decimal(term_months)).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )
            for month in range(1, term_months + 1):
                interest = (balance * monthly_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
                if month == term_months:
                    principal_part = balance
                else:
                    principal_part = principal_installment
                payment = (principal_part + interest).quantize(Decimal("0.01"), ROUND_HALF_UP)
                balance = (balance - principal_part).quantize(Decimal("0.01"), ROUND_HALF_UP)
                total += payment
                installments.append(
                    {
                        "month": month,
                        "payment": str(payment),
                        "principal": str(principal_part),
                        "interest": str(interest),
                        "balance": str(balance),
                    }
                )

        first_payment = Decimal(installments[0]["payment"]) if installments else Decimal("0")
        schedule = RepaymentSchedule(
            schedule_id=str(uuid.uuid4()),
            application_id=application_id,
            total_amount=total.quantize(Decimal("0.01"), ROUND_HALF_UP),
            monthly_payment=first_payment,
            repayment_type=repayment_type,
            installments=installments,
            created_at=datetime.now(UTC),
        )
        self._schedules[application_id] = schedule
        return schedule

    def get_schedule(self, application_id: str) -> RepaymentSchedule | None:
        """Retrieve a stored repayment schedule."""
        return self._schedules.get(application_id)

    def process_payment(self, application_id: str, amount: Decimal) -> dict:
        """Record a repayment against a loan.

        Args:
            application_id: Loan application receiving the payment.
            amount: Payment amount (Decimal).

        Returns:
            Confirmation dict with processed status and string amount (I-05).
        """
        return {
            "status": "processed",
            "amount": str(amount),
            "application_id": application_id,
        }

    def calculate_early_repayment_penalty(
        self,
        application_id: str,
        months_remaining: int,
        outstanding: Decimal,
    ) -> Decimal:
        """Compute early repayment penalty at 1% annualised rate.

        penalty = outstanding × 0.01 × (months_remaining / 12)

        Args:
            application_id: Loan application (for audit context).
            months_remaining: Remaining months on the loan term.
            outstanding: Outstanding principal balance (Decimal).

        Returns:
            Penalty amount as Decimal.
        """
        penalty = outstanding * Decimal("0.01") * (Decimal(months_remaining) / Decimal("12"))
        return penalty.quantize(Decimal("0.01"), ROUND_HALF_UP)

    @staticmethod
    def _annuity_payment(
        principal: Decimal,
        monthly_rate: Decimal,
        term_months: int,
    ) -> Decimal:
        """Compute the fixed annuity payment amount.

        Formula: P × r × (1+r)^n / ((1+r)^n - 1)
        When rate=0 returns principal/n.
        """
        if monthly_rate == Decimal("0"):
            return (principal / Decimal(term_months)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        n = Decimal(term_months)
        one_plus_r_n = (Decimal("1") + monthly_rate) ** term_months
        payment = principal * monthly_rate * one_plus_r_n / (one_plus_r_n - Decimal("1"))
        return payment.quantize(Decimal("0.01"), ROUND_HALF_UP)
