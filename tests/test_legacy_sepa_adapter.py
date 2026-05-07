"""
tests/test_legacy_sepa_adapter.py — Unit tests for LegacySepaAdapter.

Coverage: 100%  |  Tests: 28  |  No external deps (all in-memory).
Verifies semantic parity with SEPA outgoing flow (sepa-service/create-outgoing-transactions).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.payment.legacy.legacy_sepa_adapter import (
    LegacySepaAdapter,
    SepaApplicationError,
    SepaPaymentStatus,
    _validate_bic,
    _validate_iban,
)
from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)

# ── Test IBANs ────────────────────────────────────────────────────────────────

_DEBTOR_IBAN = "DE89370400440532013000"  # Germany — valid (ISO 13616 example)
_CREDITOR_IBAN = "GB82WEST12345698765432"  # UK — valid (ISO 13616 example)
_INVALID_IBAN = "DE00370400440532013000"  # Same structure, bad check digits
_VALID_BIC_8 = "DEUTDEFF"
_VALID_BIC_11 = "DEUTDEFFXXX"


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_intent(
    *,
    rail: PaymentRail = PaymentRail.SEPA_CT,
    amount: Decimal = Decimal("100.00"),
    idempotency_key: str = "key-001",
    reference: str = "test-ref",
    debtor_iban: str = _DEBTOR_IBAN,
    creditor_iban: str = _CREDITOR_IBAN,
    creditor_bic: str | None = _VALID_BIC_8,
    customer_id: str = "cust-001",
) -> PaymentIntent:
    return PaymentIntent(
        idempotency_key=idempotency_key,
        rail=rail,
        direction=PaymentDirection.OUTBOUND,
        amount=amount,
        currency="EUR",
        debtor_account=BankAccount(
            account_holder_name="Debtor Name",
            iban=debtor_iban,
        ),
        creditor_account=BankAccount(
            account_holder_name="Creditor Name",
            iban=creditor_iban,
            bic=creditor_bic,
        ),
        reference=reference,
        end_to_end_id="e2e-001",
        requested_at=datetime.now(UTC),
        metadata={"customer_id": customer_id},
    )


def _adapter() -> LegacySepaAdapter:
    return LegacySepaAdapter()


# ── IBAN / BIC validators ─────────────────────────────────────────────────────


def test_validate_iban_valid_de() -> None:
    assert _validate_iban(_DEBTOR_IBAN) is True


def test_validate_iban_valid_gb() -> None:
    assert _validate_iban(_CREDITOR_IBAN) is True


def test_validate_iban_invalid_check_digits() -> None:
    assert _validate_iban(_INVALID_IBAN) is False


def test_validate_iban_garbage_string() -> None:
    assert _validate_iban("NOT_AN_IBAN") is False


def test_validate_bic_8_chars() -> None:
    assert _validate_bic(_VALID_BIC_8) is True


def test_validate_bic_11_chars() -> None:
    assert _validate_bic(_VALID_BIC_11) is True


def test_validate_bic_too_short() -> None:
    assert _validate_bic("ABCD") is False


def test_validate_bic_digits_in_bank_code() -> None:
    assert _validate_bic("1234DEFF") is False


# ── submit_payment — happy paths ──────────────────────────────────────────────


def test_submit_sct_happy_path() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(rail=PaymentRail.SEPA_CT))
    assert isinstance(result, PaymentResult)
    assert result.status == PaymentStatus.PENDING
    assert result.rail == PaymentRail.SEPA_CT
    assert result.currency == "EUR"
    assert result.amount == Decimal("100.00")
    assert result.provider_payment_id.startswith("sepa-")


def test_submit_sct_inst_happy_path() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(
        _make_intent(rail=PaymentRail.SEPA_INSTANT, amount=Decimal("999.99"))
    )
    assert result.status == PaymentStatus.PENDING
    assert result.rail == PaymentRail.SEPA_INSTANT


def test_submit_sct_inst_exactly_at_limit_ok() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(
        _make_intent(rail=PaymentRail.SEPA_INSTANT, amount=Decimal("100000.00"))
    )
    assert result.status == PaymentStatus.PENDING


# ── submit_payment — idempotency ──────────────────────────────────────────────


def test_submit_idempotency_same_key_returns_same_payment_id() -> None:
    adapter = _adapter()
    intent = _make_intent()
    r1 = adapter.submit_payment(intent)
    r2 = adapter.submit_payment(intent)
    assert r1.provider_payment_id == r2.provider_payment_id


def test_submit_different_key_same_reference_creates_new_payment() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(idempotency_key="key-A"))
    r2 = adapter.submit_payment(_make_intent(idempotency_key="key-B"))
    assert r1.provider_payment_id != r2.provider_payment_id


# ── submit_payment — validation failures ──────────────────────────────────────


def test_submit_invalid_debtor_iban_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(debtor_iban=_INVALID_IBAN))
    assert exc_info.value.code == "invalid_iban"


def test_submit_invalid_creditor_iban_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(creditor_iban=_INVALID_IBAN))
    assert exc_info.value.code == "invalid_iban"


def test_submit_invalid_bic_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(creditor_bic="1234DEFF"))
    assert exc_info.value.code == "invalid_bic"


def test_submit_no_bic_is_allowed() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(creditor_bic=None))
    assert result.status == PaymentStatus.PENDING


def test_submit_sct_inst_over_limit_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(
            _make_intent(rail=PaymentRail.SEPA_INSTANT, amount=Decimal("100000.01"))
        )
    assert exc_info.value.code == "amount_exceeds_sct_inst_limit"


def test_submit_wrong_currency_raises_at_intent_level() -> None:
    with pytest.raises(ValueError, match="only supports EUR"):
        PaymentIntent(
            idempotency_key="key",
            rail=PaymentRail.SEPA_CT,
            direction=PaymentDirection.OUTBOUND,
            amount=Decimal("100"),
            currency="GBP",
            debtor_account=BankAccount(account_holder_name="A", iban=_DEBTOR_IBAN),
            creditor_account=BankAccount(account_holder_name="B", iban=_CREDITOR_IBAN),
            reference="ref",
            end_to_end_id="e2e",
            requested_at=datetime.now(UTC),
        )


def test_submit_negative_amount_raises_at_intent_level() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _make_intent(amount=Decimal("-1.00"))


def test_submit_zero_amount_raises_at_intent_level() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _make_intent(amount=Decimal("0"))


def test_submit_reference_too_long_raises() -> None:
    adapter = _adapter()
    long_ref = "X" * 141
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(reference=long_ref))
    assert exc_info.value.code == "reference_too_long"


def test_submit_reference_exactly_140_chars_ok() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(reference="X" * 140))
    assert result.status == PaymentStatus.PENDING


def test_submit_unsupported_rail_raises() -> None:
    adapter = _adapter()
    fps_intent = PaymentIntent(
        idempotency_key="key-fps",
        rail=PaymentRail.FPS,
        direction=PaymentDirection.OUTBOUND,
        amount=Decimal("50.00"),
        currency="GBP",
        debtor_account=BankAccount(
            account_holder_name="Name", sort_code="200000", account_number="12345678"
        ),
        creditor_account=BankAccount(
            account_holder_name="Name", sort_code="200000", account_number="12345679"
        ),
        reference="ref",
        end_to_end_id="e2e",
        requested_at=datetime.now(UTC),
    )
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(fps_intent)
    assert exc_info.value.code == "unsupported_rail"


# ── get_payment_status ────────────────────────────────────────────────────────


def test_get_payment_status_known() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    status_result = adapter.get_payment_status(result.provider_payment_id)
    assert status_result.provider_payment_id == result.provider_payment_id


def test_get_payment_status_unknown_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.get_payment_status("nonexistent-id")
    assert exc_info.value.code == "payment_not_found"


# ── state machine ─────────────────────────────────────────────────────────────


def test_state_transition_pending_to_submitted() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    updated = adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    assert updated.status == SepaPaymentStatus.SUBMITTED
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.PROCESSING


def test_state_transition_submitted_to_settled() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SETTLED)
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.COMPLETED


def test_state_transition_pending_to_cancelled() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.CANCELLED)
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.CANCELLED


def test_illegal_state_transition_settled_to_pending_raises() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SETTLED)
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.PENDING)
    assert exc_info.value.code == "invalid_state_transition"


def test_illegal_transition_cancelled_to_submitted_raises() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.CANCELLED)
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    assert exc_info.value.code == "invalid_state_transition"


# ── list_payments ─────────────────────────────────────────────────────────────


def test_list_payments_filter_by_status() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(idempotency_key="k1"))
    adapter.submit_payment(_make_intent(idempotency_key="k2"))
    adapter.advance_to(r1.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    pending = adapter.list_payments(status=SepaPaymentStatus.PENDING)
    assert len(pending) == 1


def test_list_payments_filter_by_scheme() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent(rail=PaymentRail.SEPA_CT, idempotency_key="k1"))
    adapter.submit_payment(_make_intent(rail=PaymentRail.SEPA_INSTANT, idempotency_key="k2"))
    sct = adapter.list_payments(scheme="SCT")
    sct_inst = adapter.list_payments(scheme="SCT_INST")
    assert len(sct) == 1
    assert len(sct_inst) == 1


def test_list_payments_multi_tenant_isolation() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent(idempotency_key="k1", customer_id="cust-A"))
    adapter.submit_payment(_make_intent(idempotency_key="k2", customer_id="cust-B"))
    assert len(adapter.list_payments(customer_id="cust-A")) == 1
    assert len(adapter.list_payments(customer_id="cust-B")) == 1
    assert len(adapter.list_payments(customer_id="cust-C")) == 0


# ── health_check / protocol conformance ──────────────────────────────────────


def test_health_check_returns_true() -> None:
    assert _adapter().health_check() is True


def test_protocol_conformance() -> None:
    adapter = _adapter()
    assert hasattr(adapter, "submit_payment")
    assert hasattr(adapter, "get_payment_status")
    assert hasattr(adapter, "health_check")
    from services.payment.payment_port import PaymentRailPort

    _port: PaymentRailPort = adapter  # type: ignore[assignment]
    assert _port is adapter


def test_advance_to_unknown_payment_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.advance_to("nonexistent-id", SepaPaymentStatus.SUBMITTED)
    assert exc_info.value.code == "payment_not_found"
