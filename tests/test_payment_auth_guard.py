"""Tests for Payment Authorization Guard (IL-PAY-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.customer_lifecycle.lifecycle_models import CustomerState
from services.kyc.kyc_port import KYCStatus
from services.payment.payment_auth_guard import (
    CustomerNotActiveError,
    HITLProposal,
    InMemoryKYCApprovalPort,
    InMemoryLifecycleStatePort,
    InvalidPaymentAmountError,
    JurisdictionBlockedError,
    KYCRequiredError,
    PaymentAuthApproved,
    PaymentAuthGuard,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _guard(
    state: CustomerState = CustomerState.ACTIVE,
    kyc_status: KYCStatus = KYCStatus.APPROVED,
    entity_type: str = "INDIVIDUAL",
) -> PaymentAuthGuard:
    lc = InMemoryLifecycleStatePort(default=state)
    kyc = InMemoryKYCApprovalPort(default=kyc_status)
    return PaymentAuthGuard(lifecycle=lc, kyc=kyc, entity_type=entity_type)


def _authorize(
    guard: PaymentAuthGuard,
    amount: str = "500",
    currency: str = "GBP",
    jurisdiction: str = "GB",
    customer_id: str = "C-001",
) -> PaymentAuthApproved | HITLProposal:
    return guard.authorize(
        customer_id=customer_id,
        amount=Decimal(amount),
        currency=currency,
        beneficiary_jurisdiction=jurisdiction,
    )


# ── Happy-path: PaymentAuthApproved ──────────────────────────────────────────


class TestPaymentAuthApproved:
    def test_active_kyc_approved_below_edd_returns_approved(self) -> None:
        guard = _guard()
        result = _authorize(guard, amount="500")
        assert isinstance(result, PaymentAuthApproved)

    def test_approved_fields(self) -> None:
        guard = _guard()
        result = _authorize(guard, amount="999.99", currency="EUR", jurisdiction="FR")
        assert isinstance(result, PaymentAuthApproved)
        assert result.customer_id == "C-001"
        assert result.currency == "EUR"
        assert result.beneficiary_jurisdiction == "FR"
        assert result.amount == "999.99"

    def test_amount_stored_as_string(self) -> None:
        """I-01, I-05: amount in result is a plain string, not float."""
        guard = _guard()
        result = _authorize(guard, amount="1234.56")
        assert isinstance(result, PaymentAuthApproved)
        assert isinstance(result.amount, str)
        assert Decimal(result.amount) == Decimal("1234.56")

    def test_authorized_at_is_set(self) -> None:
        guard = _guard()
        result = _authorize(guard)
        assert isinstance(result, PaymentAuthApproved)
        assert result.authorized_at  # non-empty ISO timestamp

    def test_exactly_one_below_edd_threshold_approved(self) -> None:
        """£9999.99 is below INDIVIDUAL EDD threshold of £10k."""
        guard = _guard()
        result = _authorize(guard, amount="9999.99")
        assert isinstance(result, PaymentAuthApproved)

    def test_per_customer_state_override(self) -> None:
        lc = InMemoryLifecycleStatePort(default=CustomerState.SUSPENDED)
        lc.set_state("C-OK", CustomerState.ACTIVE)
        kyc = InMemoryKYCApprovalPort()
        guard = PaymentAuthGuard(lifecycle=lc, kyc=kyc)
        result = guard.authorize("C-OK", Decimal("100"), "GBP", "GB")
        assert isinstance(result, PaymentAuthApproved)


# ── EDD threshold: HITLProposal (I-04, I-27) ─────────────────────────────────


class TestHITLProposal:
    def test_at_edd_threshold_returns_hitl(self) -> None:
        """£10,000 exactly meets INDIVIDUAL EDD threshold → HITLProposal."""
        guard = _guard()
        result = _authorize(guard, amount="10000")
        assert isinstance(result, HITLProposal)

    def test_above_edd_threshold_returns_hitl(self) -> None:
        guard = _guard()
        result = _authorize(guard, amount="50000")
        assert isinstance(result, HITLProposal)

    def test_hitl_fields(self) -> None:
        guard = _guard()
        result = _authorize(guard, amount="10000", currency="GBP", jurisdiction="DE")
        assert isinstance(result, HITLProposal)
        assert result.customer_id == "C-001"
        assert result.amount == "10000"
        assert result.currency == "GBP"
        assert result.beneficiary_jurisdiction == "DE"
        assert result.requires_approval_from == "MLRO"

    def test_hitl_reason_mentions_edd(self) -> None:
        guard = _guard()
        result = _authorize(guard, amount="15000")
        assert isinstance(result, HITLProposal)
        assert "EDD" in result.reason or "edd" in result.reason.lower()

    def test_hitl_amount_is_string(self) -> None:
        """I-01: amount stored as Decimal string in HITLProposal."""
        guard = _guard()
        result = _authorize(guard, amount="10000")
        assert isinstance(result, HITLProposal)
        assert isinstance(result.amount, str)
        assert Decimal(result.amount) == Decimal("10000")

    def test_corporate_edd_threshold_is_50k(self) -> None:
        """COMPANY EDD threshold is £50k (I-04) — £49,999.99 approved."""
        guard = _guard(entity_type="COMPANY")
        result = _authorize(guard, amount="49999.99")
        assert isinstance(result, PaymentAuthApproved)

    def test_corporate_at_50k_hitl(self) -> None:
        guard = _guard(entity_type="COMPANY")
        result = _authorize(guard, amount="50000")
        assert isinstance(result, HITLProposal)


# ── Guard failures ────────────────────────────────────────────────────────────


class TestInvalidAmount:
    def test_zero_amount_raises(self) -> None:
        guard = _guard()
        with pytest.raises(InvalidPaymentAmountError):
            guard.authorize("C-001", Decimal("0"), "GBP", "GB")

    def test_negative_amount_raises(self) -> None:
        guard = _guard()
        with pytest.raises(InvalidPaymentAmountError):
            guard.authorize("C-001", Decimal("-100"), "GBP", "GB")

    def test_amount_check_runs_before_jurisdiction(self) -> None:
        """Amount guard is first — blocked jurisdiction not reached yet."""
        guard = _guard()
        with pytest.raises(InvalidPaymentAmountError):
            guard.authorize("C-001", Decimal("0"), "GBP", "RU")


class TestJurisdictionBlocked:
    @pytest.mark.parametrize("country", ["RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"])
    def test_all_blocked_jurisdictions_raise(self, country: str) -> None:
        guard = _guard()
        with pytest.raises(JurisdictionBlockedError):
            _authorize(guard, jurisdiction=country)

    def test_jurisdiction_checked_case_insensitive(self) -> None:
        guard = _guard()
        with pytest.raises(JurisdictionBlockedError):
            _authorize(guard, jurisdiction="ru")

    def test_gb_jurisdiction_allowed(self) -> None:
        guard = _guard()
        result = _authorize(guard, jurisdiction="GB")
        assert isinstance(result, PaymentAuthApproved)

    def test_jurisdiction_check_before_lifecycle(self) -> None:
        """Jurisdiction guard runs before lifecycle — blocked even for suspended customer."""
        guard = _guard(state=CustomerState.SUSPENDED)
        with pytest.raises(JurisdictionBlockedError):
            _authorize(guard, jurisdiction="RU")


class TestCustomerNotActive:
    @pytest.mark.parametrize(
        "state",
        [
            CustomerState.PROSPECT,
            CustomerState.ONBOARDING,
            CustomerState.KYC_PENDING,
            CustomerState.SUSPENDED,
            CustomerState.CLOSED,
            CustomerState.OFFBOARDED,
        ],
    )
    def test_non_active_states_raise(self, state: CustomerState) -> None:
        guard = _guard(state=state)
        with pytest.raises(CustomerNotActiveError):
            _authorize(guard)

    def test_error_message_contains_state(self) -> None:
        guard = _guard(state=CustomerState.SUSPENDED)
        with pytest.raises(CustomerNotActiveError, match="suspended"):
            _authorize(guard)

    def test_lifecycle_check_before_kyc(self) -> None:
        """Lifecycle guard runs before KYC — suspended customer with bad KYC gets lifecycle error."""
        guard = _guard(state=CustomerState.SUSPENDED, kyc_status=KYCStatus.PENDING)
        with pytest.raises(CustomerNotActiveError):
            _authorize(guard)


class TestKYCRequired:
    @pytest.mark.parametrize(
        "status",
        [KYCStatus.PENDING, KYCStatus.REJECTED, KYCStatus.EXPIRED],
    )
    def test_non_approved_kyc_raises(self, status: KYCStatus) -> None:
        guard = _guard(kyc_status=status)
        with pytest.raises(KYCRequiredError):
            _authorize(guard)

    def test_error_message_contains_status(self) -> None:
        guard = _guard(kyc_status=KYCStatus.PENDING)
        with pytest.raises(KYCRequiredError, match="PENDING"):
            _authorize(guard)


# ── Stub isolation ────────────────────────────────────────────────────────────


class TestStubs:
    def test_inmemory_lifecycle_default_active(self) -> None:
        port = InMemoryLifecycleStatePort()
        assert port.get_state("any") == CustomerState.ACTIVE

    def test_inmemory_lifecycle_set_and_get(self) -> None:
        port = InMemoryLifecycleStatePort()
        port.set_state("C-X", CustomerState.SUSPENDED)
        assert port.get_state("C-X") == CustomerState.SUSPENDED
        assert port.get_state("C-Y") == CustomerState.ACTIVE  # default unchanged

    def test_inmemory_kyc_default_approved(self) -> None:
        port = InMemoryKYCApprovalPort()
        assert port.get_status("any") == KYCStatus.APPROVED

    def test_inmemory_kyc_set_and_get(self) -> None:
        port = InMemoryKYCApprovalPort()
        port.set_status("C-X", KYCStatus.PENDING)
        assert port.get_status("C-X") == KYCStatus.PENDING
        assert port.get_status("C-Y") == KYCStatus.APPROVED

    def test_no_ports_injected_uses_defaults(self) -> None:
        """Default guard (no args) approves ACTIVE+APPROVED customer below EDD."""
        guard = PaymentAuthGuard()
        result = guard.authorize("C-001", Decimal("100"), "GBP", "GB")
        assert isinstance(result, PaymentAuthApproved)
