"""
tests/test_payment_processing_service.py
Tests for PaymentProcessingService (IL-PAY-02).

Acceptance criteria:
- test_payment_authorize_success (Decimal amounts, I-01)
- test_payment_authorize_blocked_jurisdiction (I-02)
- test_payment_capture_after_auth
- test_payment_refund_after_capture (partial + full)
- test_payment_duplicate_idempotency_key
- test_payment_amount_exceeds_threshold_requires_edd (I-04)
- test_payment_audit_trail_recorded (I-24)
"""

from decimal import Decimal

import pytest

from services.payment.currency_validator import (
    AmountValidationError,
    CurrencyValidationError,
    requires_edd,
    requires_mlro_escalation,
    validate_amount,
    validate_currency,
)
from services.payment.payment_gateway_port import InMemoryGateway
from services.payment.payment_models import (
    SUPPORTED_CURRENCIES,
    VALID_TRANSITIONS,
    PaymentTransaction,
    TransactionStatus,
)
from services.payment.payment_processing_service import (
    DuplicateIdempotencyKeyError,
    EDDHITLProposal,
    InMemoryAuditPort,
    InvalidTransitionError,
    JurisdictionBlockedError,
    PaymentProcessingService,
    RefundExceedsAmountError,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def gateway():
    return InMemoryGateway()


@pytest.fixture
def audit():
    return InMemoryAuditPort()


@pytest.fixture
def service(gateway, audit):
    return PaymentProcessingService(gateway=gateway, audit=audit)


# ── Authorization Tests ──────────────────────────────────────────────────────


class TestAuthorize:
    def test_payment_authorize_success(self, service):
        """AC: authorize with Decimal amount returns AUTHORIZED transaction (I-01)."""
        result = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        assert isinstance(result, PaymentTransaction)
        assert result.status == TransactionStatus.AUTHORIZED
        assert isinstance(result.amount, Decimal)
        assert result.amount == Decimal("100.00")
        assert result.currency == "GBP"
        assert result.customer_id == "cust-001"

    def test_payment_authorize_eur(self, service):
        """Authorize EUR payment."""
        result = service.authorize(
            customer_id="cust-002",
            amount=Decimal("250.50"),
            currency="EUR",
            beneficiary_jurisdiction="DE",
        )
        assert isinstance(result, PaymentTransaction)
        assert result.status == TransactionStatus.AUTHORIZED
        assert result.currency == "EUR"

    def test_payment_authorize_usd(self, service):
        """Authorize USD payment."""
        result = service.authorize(
            customer_id="cust-003",
            amount=Decimal("500.00"),
            currency="USD",
            beneficiary_jurisdiction="US",
        )
        assert isinstance(result, PaymentTransaction)
        assert result.currency == "USD"

    def test_payment_authorize_blocked_jurisdiction_ru(self, service):
        """AC: RU jurisdiction raises JurisdictionBlockedError (I-02)."""
        with pytest.raises(JurisdictionBlockedError, match="sanctioned"):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("100.00"),
                currency="GBP",
                beneficiary_jurisdiction="RU",
            )

    def test_payment_authorize_blocked_jurisdiction_ir(self, service):
        """AC: IR jurisdiction blocked (I-02)."""
        with pytest.raises(JurisdictionBlockedError):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("100.00"),
                currency="GBP",
                beneficiary_jurisdiction="IR",
            )

    def test_payment_authorize_blocked_jurisdiction_kp(self, service):
        """AC: KP jurisdiction blocked (I-02)."""
        with pytest.raises(JurisdictionBlockedError):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("100.00"),
                currency="GBP",
                beneficiary_jurisdiction="KP",
            )

    def test_payment_authorize_blocked_jurisdiction_case_insensitive(self, service):
        """Jurisdiction check is case-insensitive."""
        with pytest.raises(JurisdictionBlockedError):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("100.00"),
                currency="GBP",
                beneficiary_jurisdiction="ru",
            )

    def test_payment_authorize_zero_amount(self, service):
        """Zero amount raises AmountValidationError."""
        with pytest.raises(AmountValidationError):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("0"),
                currency="GBP",
                beneficiary_jurisdiction="GB",
            )

    def test_payment_authorize_negative_amount(self, service):
        """Negative amount raises AmountValidationError."""
        with pytest.raises(AmountValidationError):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("-50.00"),
                currency="GBP",
                beneficiary_jurisdiction="GB",
            )

    def test_payment_authorize_unsupported_currency(self, service):
        """Unsupported currency raises CurrencyValidationError."""
        with pytest.raises(CurrencyValidationError):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("100.00"),
                currency="JPY",
                beneficiary_jurisdiction="JP",
            )

    def test_payment_authorize_gateway_failure(self, service, gateway):
        """Gateway failure returns FAILED transaction."""
        gateway.set_fail_next(True)
        result = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        assert isinstance(result, PaymentTransaction)
        assert result.status == TransactionStatus.FAILED


# ── Idempotency Tests ────────────────────────────────────────────────────────


class TestIdempotency:
    def test_payment_duplicate_idempotency_key(self, service):
        """AC: duplicate idempotency key raises DuplicateIdempotencyKeyError."""
        service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
            idempotency_key="key-001",
        )
        with pytest.raises(DuplicateIdempotencyKeyError, match="key-001"):
            service.authorize(
                customer_id="cust-001",
                amount=Decimal("100.00"),
                currency="GBP",
                beneficiary_jurisdiction="GB",
                idempotency_key="key-001",
            )

    def test_different_idempotency_keys_ok(self, service):
        """Different idempotency keys create separate transactions."""
        r1 = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
            idempotency_key="key-a",
        )
        r2 = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
            idempotency_key="key-b",
        )
        assert r1.transaction_id != r2.transaction_id


# ── EDD Threshold Tests ─────────────────────────────────────────────────────


class TestEDDThreshold:
    def test_payment_amount_exceeds_threshold_requires_edd(self, service):
        """AC: amount >= £10k returns EDDHITLProposal (I-04, I-27)."""
        result = service.authorize(
            customer_id="cust-001",
            amount=Decimal("10000"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        assert isinstance(result, EDDHITLProposal)
        assert result.requires_approval_from == "MLRO"
        assert result.amount == "10000"
        assert result.currency == "GBP"

    def test_payment_amount_above_threshold(self, service):
        """Amount above threshold returns EDDHITLProposal."""
        result = service.authorize(
            customer_id="cust-001",
            amount=Decimal("15000.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        assert isinstance(result, EDDHITLProposal)

    def test_payment_below_threshold_authorized(self, service):
        """Amount below threshold authorizes normally."""
        result = service.authorize(
            customer_id="cust-001",
            amount=Decimal("9999.99"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        assert isinstance(result, PaymentTransaction)
        assert result.status == TransactionStatus.AUTHORIZED

    def test_edd_approved_bypasses_threshold(self, service):
        """Pre-approved EDD allows authorization above threshold."""
        result = service.authorize(
            customer_id="cust-001",
            amount=Decimal("15000.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
            edd_approved=True,
        )
        assert isinstance(result, PaymentTransaction)
        assert result.status == TransactionStatus.AUTHORIZED

    def test_high_value_mlro_escalation(self, service):
        """High-value (>£50k) produces MLRO escalation message."""
        result = service.authorize(
            customer_id="cust-001",
            amount=Decimal("55000.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        assert isinstance(result, EDDHITLProposal)
        assert "MLRO escalation" in result.reason


# ── Capture Tests ────────────────────────────────────────────────────────────


class TestCapture:
    def test_payment_capture_after_auth(self, service):
        """AC: capture after authorization succeeds."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        captured = service.capture(tx.transaction_id)
        assert captured.status == TransactionStatus.CAPTURED
        assert captured.amount == Decimal("100.00")

    def test_capture_without_auth_fails(self, service):
        """Capture without prior authorization raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            service.capture("tx-nonexistent")

    def test_capture_already_captured_fails(self, service):
        """Capture of already-captured transaction raises InvalidTransitionError."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        service.capture(tx.transaction_id)
        with pytest.raises(InvalidTransitionError):
            service.capture(tx.transaction_id)


# ── Settle Tests ─────────────────────────────────────────────────────────────


class TestSettle:
    def test_settle_after_capture(self, service):
        """Settle after capture succeeds."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        service.capture(tx.transaction_id)
        settled = service.settle(tx.transaction_id)
        assert settled.status == TransactionStatus.SETTLED

    def test_settle_without_capture_fails(self, service):
        """Settle without capture raises InvalidTransitionError."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        with pytest.raises(InvalidTransitionError):
            service.settle(tx.transaction_id)


# ── Refund Tests ─────────────────────────────────────────────────────────────


class TestRefund:
    def _settled_tx(self, service):
        """Helper: create an authorized → captured → settled transaction."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("200.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        service.capture(tx.transaction_id)
        service.settle(tx.transaction_id)
        return tx

    def test_payment_full_refund_after_settle(self, service):
        """AC: full refund after settlement succeeds."""
        tx = self._settled_tx(service)
        refunded = service.refund(tx.transaction_id)
        assert refunded.status == TransactionStatus.REFUNDED
        assert refunded.refunded_amount == Decimal("200.00")

    def test_payment_partial_refund(self, service):
        """AC: partial refund returns PARTIALLY_REFUNDED."""
        tx = self._settled_tx(service)
        refunded = service.refund(tx.transaction_id, amount=Decimal("50.00"))
        assert refunded.status == TransactionStatus.PARTIALLY_REFUNDED
        assert refunded.refunded_amount == Decimal("50.00")

    def test_payment_multiple_partial_refunds(self, service):
        """Multiple partial refunds accumulate."""
        tx = self._settled_tx(service)
        r1 = service.refund(tx.transaction_id, amount=Decimal("50.00"))
        assert r1.refunded_amount == Decimal("50.00")
        r2 = service.refund(tx.transaction_id, amount=Decimal("50.00"))
        assert r2.refunded_amount == Decimal("100.00")

    def test_partial_then_full_refund(self, service):
        """Partial refund followed by remaining amount gives REFUNDED."""
        tx = self._settled_tx(service)
        service.refund(tx.transaction_id, amount=Decimal("100.00"))
        r2 = service.refund(tx.transaction_id, amount=Decimal("100.00"))
        assert r2.status == TransactionStatus.REFUNDED
        assert r2.refunded_amount == Decimal("200.00")

    def test_refund_exceeds_amount(self, service):
        """Refund exceeding original amount raises RefundExceedsAmountError."""
        tx = self._settled_tx(service)
        with pytest.raises(RefundExceedsAmountError):
            service.refund(tx.transaction_id, amount=Decimal("201.00"))

    def test_refund_before_settle_fails(self, service):
        """Refund before settlement raises InvalidTransitionError."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        service.capture(tx.transaction_id)
        with pytest.raises(InvalidTransitionError):
            service.refund(tx.transaction_id)


# ── Audit Trail Tests ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_payment_audit_trail_recorded(self, service, audit):
        """AC: audit entry recorded for every state transition (I-24)."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.transaction_id == tx.transaction_id
        assert entry.action == "AUTHORIZE"
        assert entry.new_status == TransactionStatus.AUTHORIZED
        assert entry.old_status is None
        assert isinstance(entry.amount, Decimal)

    def test_full_lifecycle_audit_trail(self, service, audit):
        """Full lifecycle: authorize → capture → settle → refund produces 4 entries."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        service.capture(tx.transaction_id)
        service.settle(tx.transaction_id)
        service.refund(tx.transaction_id)
        assert len(audit.entries) == 4
        actions = [e.action for e in audit.entries]
        assert actions == ["AUTHORIZE", "CAPTURE", "SETTLE", "REFUND"]

    def test_audit_entry_immutable(self, audit):
        """Audit entries are frozen dataclasses (I-24)."""
        from services.payment.payment_models import AuditEntry

        entry = AuditEntry(
            transaction_id="tx-001",
            action="TEST",
            old_status=None,
            new_status=TransactionStatus.AUTHORIZED,
            amount=Decimal("100"),
            currency="GBP",
            actor="test",
        )
        with pytest.raises(AttributeError):
            entry.action = "MODIFIED"  # type: ignore[misc]

    def test_audit_records_refund_details(self, service, audit):
        """Refund audit entry includes refund amount details."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("200.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        service.capture(tx.transaction_id)
        service.settle(tx.transaction_id)
        service.refund(tx.transaction_id, amount=Decimal("75.00"))
        refund_entry = audit.entries[-1]
        assert refund_entry.action == "REFUND"
        assert "75.00" in refund_entry.details


# ── Transaction Query Tests ──────────────────────────────────────────────────


class TestQuery:
    def test_get_transaction(self, service):
        """get_transaction returns stored transaction."""
        tx = service.authorize(
            customer_id="cust-001",
            amount=Decimal("100.00"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
        )
        found = service.get_transaction(tx.transaction_id)
        assert found is not None
        assert found.transaction_id == tx.transaction_id

    def test_get_transaction_not_found(self, service):
        """get_transaction returns None for unknown ID."""
        assert service.get_transaction("tx-nonexistent") is None


# ── Currency Validator Tests ─────────────────────────────────────────────────


class TestCurrencyValidator:
    def test_validate_supported_currencies(self):
        """All supported currencies pass validation."""
        for cur in SUPPORTED_CURRENCIES:
            validate_currency(cur)

    def test_validate_unsupported_currency(self):
        with pytest.raises(CurrencyValidationError):
            validate_currency("CHF")

    def test_validate_amount_decimal(self):
        validate_amount(Decimal("100.00"), "GBP")

    def test_validate_amount_not_decimal(self):
        with pytest.raises(AmountValidationError, match="Decimal"):
            validate_amount(100.0, "GBP")  # type: ignore[arg-type]

    def test_validate_amount_exceeds_scheme_limit(self):
        with pytest.raises(AmountValidationError, match="exceeds scheme limit"):
            validate_amount(Decimal("1000001"), "GBP")

    def test_requires_edd_at_threshold(self):
        assert requires_edd(Decimal("10000"), "GBP") is True

    def test_requires_edd_below_threshold(self):
        assert requires_edd(Decimal("9999.99"), "GBP") is False

    def test_requires_mlro_at_threshold(self):
        assert requires_mlro_escalation(Decimal("50000"), "GBP") is True

    def test_requires_mlro_below_threshold(self):
        assert requires_mlro_escalation(Decimal("49999.99"), "GBP") is False


# ── Model Tests ──────────────────────────────────────────────────────────────


class TestModels:
    def test_payment_transaction_decimal_only(self):
        """PaymentTransaction rejects non-Decimal amount (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            PaymentTransaction(
                transaction_id="tx-001",
                idempotency_key="key-001",
                customer_id="cust-001",
                amount=100.0,  # type: ignore[arg-type]
                currency="GBP",
                beneficiary_jurisdiction="GB",
                status=TransactionStatus.PENDING,
            )

    def test_payment_transaction_positive_amount(self):
        """PaymentTransaction rejects non-positive amount."""
        with pytest.raises(ValueError, match="positive"):
            PaymentTransaction(
                transaction_id="tx-001",
                idempotency_key="key-001",
                customer_id="cust-001",
                amount=Decimal("-10"),
                currency="GBP",
                beneficiary_jurisdiction="GB",
                status=TransactionStatus.PENDING,
            )

    def test_payment_transaction_unsupported_currency(self):
        """PaymentTransaction rejects unsupported currency."""
        with pytest.raises(ValueError, match="unsupported currency"):
            PaymentTransaction(
                transaction_id="tx-001",
                idempotency_key="key-001",
                customer_id="cust-001",
                amount=Decimal("100"),
                currency="XYZ",
                beneficiary_jurisdiction="GB",
                status=TransactionStatus.PENDING,
            )

    def test_payment_transaction_frozen(self):
        """PaymentTransaction is immutable (frozen=True)."""
        tx = PaymentTransaction(
            transaction_id="tx-001",
            idempotency_key="key-001",
            customer_id="cust-001",
            amount=Decimal("100"),
            currency="GBP",
            beneficiary_jurisdiction="GB",
            status=TransactionStatus.PENDING,
        )
        with pytest.raises(AttributeError):
            tx.amount = Decimal("200")  # type: ignore[misc]

    def test_valid_transitions_complete(self):
        """Every TransactionStatus has an entry in VALID_TRANSITIONS."""
        for status in TransactionStatus:
            assert status in VALID_TRANSITIONS
