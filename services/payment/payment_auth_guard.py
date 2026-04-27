"""
services/payment/payment_auth_guard.py
Payment Authorization Guard (IL-PAY-01).

Wraps PaymentService with pre-flight compliance checks:
  - Customer lifecycle state must be ACTIVE (LifecycleStatePort)
  - KYC must be APPROVED (KYCApprovalPort)
  - Beneficiary jurisdiction must not be blocked (I-02)
  - Amount must be positive Decimal (I-01)
  - EDD amounts ≥ threshold require HITL L4 proposal (I-04, I-27)

I-01: all monetary comparisons use Decimal — never float.
I-02: blocked jurisdictions hard-blocked before any payment submission.
I-04: EDD threshold £10k individual / £50k corporate triggers HITLProposal.
I-27: EDD-level payments PROPOSE only — human approves, never auto-submitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from services.aml.aml_thresholds import get_thresholds
from services.customer_lifecycle.lifecycle_engine import BLOCKED_JURISDICTIONS
from services.customer_lifecycle.lifecycle_models import CustomerState
from services.kyc.kyc_port import KYCStatus

# ── Narrow ports ──────────────────────────────────────────────────────────────


class LifecycleStatePort(Protocol):
    """Narrow port: only the customer's current state is needed."""

    def get_state(self, customer_id: str) -> CustomerState: ...


class KYCApprovalPort(Protocol):
    """Narrow port: only the KYC approval status is needed."""

    def get_status(self, customer_id: str) -> KYCStatus: ...


# ── In-memory stubs ───────────────────────────────────────────────────────────


class InMemoryLifecycleStatePort:
    """Configurable stub: set state per customer_id."""

    def __init__(self, default: CustomerState = CustomerState.ACTIVE) -> None:
        self._states: dict[str, CustomerState] = {}
        self._default = default

    def set_state(self, customer_id: str, state: CustomerState) -> None:
        self._states[customer_id] = state

    def get_state(self, customer_id: str) -> CustomerState:
        return self._states.get(customer_id, self._default)


class InMemoryKYCApprovalPort:
    """Configurable stub: set KYC status per customer_id."""

    def __init__(self, default: KYCStatus = KYCStatus.APPROVED) -> None:
        self._statuses: dict[str, KYCStatus] = {}
        self._default = default

    def set_status(self, customer_id: str, status: KYCStatus) -> None:
        self._statuses[customer_id] = status

    def get_status(self, customer_id: str) -> KYCStatus:
        return self._statuses.get(customer_id, self._default)


# ── Result / proposal types ───────────────────────────────────────────────────


@dataclass(frozen=True)
class PaymentAuthApproved:
    """Payment pre-flight checks passed — safe to submit."""

    customer_id: str
    amount: str  # Decimal as string (I-01, I-05)
    currency: str
    beneficiary_jurisdiction: str
    authorized_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class HITLProposal:
    """Payment exceeds EDD threshold — HITL L4 required before submission (I-27)."""

    customer_id: str
    amount: str  # Decimal as string (I-01, I-05)
    currency: str
    beneficiary_jurisdiction: str
    reason: str
    requires_approval_from: str = "MLRO"
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── Guard errors ──────────────────────────────────────────────────────────────


class CustomerNotActiveError(ValueError):
    """Raised when the customer lifecycle state is not ACTIVE."""


class KYCRequiredError(ValueError):
    """Raised when the customer's KYC is not APPROVED."""


class JurisdictionBlockedError(ValueError):
    """Raised when the beneficiary jurisdiction is sanctioned (I-02)."""


class InvalidPaymentAmountError(ValueError):
    """Raised when the payment amount is zero or negative (I-01)."""


# ── Payment Authorization Guard ───────────────────────────────────────────────


class PaymentAuthGuard:
    """
    Pre-flight authorization guard for outbound payments (IL-PAY-01).

    I-01: amount comparisons are Decimal — never float.
    I-02: blocked jurisdictions raise JurisdictionBlockedError immediately.
    I-04: amounts ≥ EDD threshold return HITLProposal instead of approval.
    I-27: EDD-level payments are never auto-submitted; human approval required.
    """

    def __init__(
        self,
        lifecycle: LifecycleStatePort | None = None,
        kyc: KYCApprovalPort | None = None,
        entity_type: str = "INDIVIDUAL",
    ) -> None:
        self._lifecycle: LifecycleStatePort = lifecycle or InMemoryLifecycleStatePort()
        self._kyc: KYCApprovalPort = kyc or InMemoryKYCApprovalPort()
        self._entity_type = entity_type

    def authorize(
        self,
        customer_id: str,
        amount: Decimal,  # I-01: Decimal ONLY
        currency: str,
        beneficiary_jurisdiction: str,
    ) -> PaymentAuthApproved | HITLProposal:
        """Run pre-flight compliance checks for a payment.

        Returns PaymentAuthApproved when all guards pass and amount is below EDD.
        Returns HITLProposal when amount meets or exceeds EDD threshold (I-04, I-27).

        Raises:
            InvalidPaymentAmountError: amount ≤ 0.
            JurisdictionBlockedError: beneficiary jurisdiction is sanctioned (I-02).
            CustomerNotActiveError: customer lifecycle state is not ACTIVE.
            KYCRequiredError: customer KYC is not APPROVED.
        """
        self._check_amount(amount)
        self._check_jurisdiction(beneficiary_jurisdiction)
        self._check_lifecycle(customer_id)
        self._check_kyc(customer_id)

        thresholds = get_thresholds(self._entity_type)
        amount_str = str(amount)

        if amount >= thresholds.edd_trigger:  # I-01: Decimal comparison, I-04
            return HITLProposal(
                customer_id=customer_id,
                amount=amount_str,
                currency=currency,
                beneficiary_jurisdiction=beneficiary_jurisdiction,
                reason=(
                    f"Payment of {currency} {amount} meets EDD threshold "
                    f"({self._entity_type} ≥ {thresholds.edd_trigger}). "
                    "MLRO approval required before submission (I-04, I-27)."
                ),
            )

        return PaymentAuthApproved(
            customer_id=customer_id,
            amount=amount_str,
            currency=currency,
            beneficiary_jurisdiction=beneficiary_jurisdiction,
        )

    # ── Private guard methods ─────────────────────────────────────────────────

    def _check_amount(self, amount: Decimal) -> None:
        if amount <= Decimal("0"):  # I-01: Decimal comparison
            raise InvalidPaymentAmountError(
                f"Payment amount must be positive; got {amount!r} (I-01)."
            )

    def _check_jurisdiction(self, jurisdiction: str) -> None:
        if jurisdiction.upper() in BLOCKED_JURISDICTIONS:
            raise JurisdictionBlockedError(
                f"Beneficiary jurisdiction {jurisdiction!r} is sanctioned and blocked (I-02)."
            )

    def _check_lifecycle(self, customer_id: str) -> None:
        state = self._lifecycle.get_state(customer_id)
        if state != CustomerState.ACTIVE:
            raise CustomerNotActiveError(
                f"Customer {customer_id!r} lifecycle state is {state.value!r}; "
                "ACTIVE required to initiate payments."
            )

    def _check_kyc(self, customer_id: str) -> None:
        status = self._kyc.get_status(customer_id)
        if status != KYCStatus.APPROVED:
            raise KYCRequiredError(
                f"Customer {customer_id!r} KYC status is {status.value!r}; "
                "APPROVED required to initiate payments."
            )
