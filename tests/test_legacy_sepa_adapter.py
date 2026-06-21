"""
tests/test_legacy_sepa_adapter.py — Unit tests for LegacySepaAdapter (REWRITE-3).

Coverage target: 100% | Tests: ≥30 | No external deps (all in-memory).
Verifies semantic parity with SEPA outgoing flow (sepa-service/create-outgoing-transactions).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.payment.legacy.legacy_sepa_adapter import (
    LegacySepaAdapter,
    SepaApplicationError,
    SepaAuditRecord,
    SepaPaymentRecord,
    SepaPaymentStatus,
    _sepa_event_for,
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

_DEBTOR_IBAN = "DE89370400440532013000"  # Germany — valid ISO 13616
_CREDITOR_IBAN = "GB82WEST12345698765432"  # UK — valid ISO 13616

# Five invalid IBANs (parametrised below)
_INVALID_IBANS = [
    "DE00370400440532013000",  # bad check digits (00 never valid)
    "NOTANIBAN",  # garbage
    "DE89",  # too short (fails regex)
    "",  # empty string
    "FR7630006000011234567890182",  # wrong checksum for this account number
]

# Valid IBANs across ≥3 countries (parametrised below) — all verified ISO 13616 mod-97
_VALID_IBANS = [
    "DE89370400440532013000",  # Germany (ISO 13616 example)
    "GB82WEST12345698765432",  # United Kingdom (ISO 13616 example)
    "FR7630006000011234567890189",  # France (verified mod-97 = 1)
    "NL91ABNA0417164300",  # Netherlands (ISO 13616 example)
]

_VALID_BIC_8 = "DEUTDEFF"
_VALID_BIC_11 = "DEUTDEFFXXX"

_INVALID_BICS = [
    "ABCD",  # too short
    "1234DEFF",  # digits in bank code
    "DEUTDE",  # 6 chars
    "DEUTDEFF1234",  # too long (12 chars)
]


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
    creditor_name: str = "Acme GmbH",
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
            account_holder_name=creditor_name,
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


# ── No transport imports ──────────────────────────────────────────────────────


def test_no_gcp_bifrost_import() -> None:
    import sys

    import services.payment.legacy.legacy_sepa_adapter as mod

    assert not hasattr(mod, "requestToGCPProcessing")
    # sepa-scoped (matches test_no_typeorm_import convention): the SEPA adapter must not pull in
    # the GCP Bifrost transport; the standalone Wave-D bifrost_adapter (ADR-025 §15-16) is unrelated.
    assert not any("bifrost" in k for k in sys.modules if "sepa" in k)


def test_no_typeorm_import() -> None:
    import sys

    assert not any("typeorm" in k for k in sys.modules)
    assert not any("sqlalchemy" in k for k in sys.modules if "sepa" in k)


def test_no_redis_import() -> None:
    import services.payment.legacy.legacy_sepa_adapter as mod

    assert not hasattr(mod, "redis")
    assert not hasattr(mod, "RedisService")
    assert not hasattr(mod, "redisService")


# ── IBAN validator — parametrised invalids ────────────────────────────────────


@pytest.mark.parametrize("bad_iban", _INVALID_IBANS)
def test_validate_iban_invalid(bad_iban: str) -> None:
    assert _validate_iban(bad_iban) is False


# ── IBAN validator — parametrised valids ─────────────────────────────────────


@pytest.mark.parametrize("good_iban", _VALID_IBANS)
def test_validate_iban_valid(good_iban: str) -> None:
    assert _validate_iban(good_iban) is True


# ── BIC validator ─────────────────────────────────────────────────────────────


def test_validate_bic_8_chars() -> None:
    assert _validate_bic(_VALID_BIC_8) is True


def test_validate_bic_11_chars() -> None:
    assert _validate_bic(_VALID_BIC_11) is True


@pytest.mark.parametrize("bad_bic", _INVALID_BICS)
def test_validate_bic_invalid(bad_bic: str) -> None:
    assert _validate_bic(bad_bic) is False


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_protocol_conformance() -> None:
    adapter = _adapter()
    assert hasattr(adapter, "submit_payment")
    assert hasattr(adapter, "get_payment_status")
    assert hasattr(adapter, "health")
    from services.payment.payment_port import PaymentRailPort

    _port: PaymentRailPort = adapter  # type: ignore[assignment]
    assert _port is adapter


def test_health_returns_true() -> None:
    assert _adapter().health() is True


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


def test_submit_no_bic_is_allowed() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(creditor_bic=None))
    assert result.status == PaymentStatus.PENDING


def test_submit_stores_record_as_sepa_payment_record() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    record = adapter._by_payment_id[result.provider_payment_id]
    assert isinstance(record, SepaPaymentRecord)
    assert record.creditor_name == "Acme GmbH"
    assert record.submitted_at is not None


# ── submit_payment — idempotency (customer_id, reference) ────────────────────


def test_submit_same_customer_same_reference_returns_same_payment_id() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(reference="ref-A", customer_id="cust-1"))
    r2 = adapter.submit_payment(
        _make_intent(idempotency_key="key-different", reference="ref-A", customer_id="cust-1")
    )
    assert r1.provider_payment_id == r2.provider_payment_id


def test_submit_same_reference_different_customer_creates_new_payment() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(reference="ref-A", customer_id="cust-1"))
    r2 = adapter.submit_payment(
        _make_intent(idempotency_key="key-2", reference="ref-A", customer_id="cust-2")
    )
    assert r1.provider_payment_id != r2.provider_payment_id


def test_submit_same_customer_different_reference_creates_new_payment() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(reference="ref-A", customer_id="cust-1"))
    r2 = adapter.submit_payment(
        _make_intent(idempotency_key="key-2", reference="ref-B", customer_id="cust-1")
    )
    assert r1.provider_payment_id != r2.provider_payment_id


# ── submit_payment — creditor_name validation ─────────────────────────────────


def test_submit_empty_creditor_name_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(creditor_name=""))
    assert exc_info.value.code == "invalid_creditor_name"


def test_submit_whitespace_only_creditor_name_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(creditor_name="   "))
    assert exc_info.value.code == "invalid_creditor_name"


def test_submit_creditor_name_71_chars_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(creditor_name="A" * 71))
    assert exc_info.value.code == "creditor_name_too_long"


def test_submit_creditor_name_exactly_70_chars_ok() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(creditor_name="A" * 70))
    assert result.status == PaymentStatus.PENDING


def test_submit_whitespace_reference_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(reference="   "))
    assert exc_info.value.code == "invalid_reference"


# ── submit_payment — amount precision ─────────────────────────────────────────


def test_submit_amount_3_decimal_places_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(amount=Decimal("100.001")))
    assert exc_info.value.code == "invalid_amount_precision"


def test_submit_amount_exactly_2_decimal_places_ok() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(amount=Decimal("99.99")))
    assert result.status == PaymentStatus.PENDING


def test_submit_amount_integer_ok() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(amount=Decimal("50")))
    assert result.status == PaymentStatus.PENDING


# ── submit_payment — other validation failures ────────────────────────────────


def test_submit_invalid_debtor_iban_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(debtor_iban=_INVALID_IBANS[0]))
    assert exc_info.value.code == "invalid_iban"


def test_submit_invalid_creditor_iban_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(creditor_iban=_INVALID_IBANS[0]))
    assert exc_info.value.code == "invalid_iban"


def test_submit_invalid_bic_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(creditor_bic="1234DEFF"))
    assert exc_info.value.code == "invalid_bic"


def test_submit_sct_inst_over_limit_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(
            _make_intent(rail=PaymentRail.SEPA_INSTANT, amount=Decimal("100000.01"))
        )
    assert exc_info.value.code == "amount_exceeds_sct_inst_limit"


def test_submit_reference_too_long_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(reference="X" * 141))
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


def test_state_transition_submitted_to_settled_with_settled_at() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    ts = datetime.now(UTC)
    updated = adapter.advance_to(
        result.provider_payment_id, SepaPaymentStatus.SETTLED, settled_at=ts
    )
    assert updated.settled_at == ts
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.COMPLETED


def test_state_transition_submitted_to_rejected_with_error() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    updated = adapter.advance_to(
        result.provider_payment_id,
        SepaPaymentStatus.REJECTED,
        error_code="RJCT_AC01",
        error_message="Incorrect account number",
    )
    assert updated.error_code == "RJCT_AC01"
    assert updated.error_message == "Incorrect account number"
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.FAILED


def test_state_transition_pending_to_cancelled() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.CANCELLED)
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.CANCELLED


def test_state_transition_submitted_to_cancelled() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
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


def test_advance_to_unknown_payment_raises() -> None:
    adapter = _adapter()
    with pytest.raises(SepaApplicationError) as exc_info:
        adapter.advance_to("nonexistent-id", SepaPaymentStatus.SUBMITTED)
    assert exc_info.value.code == "payment_not_found"


# ── list_payments ─────────────────────────────────────────────────────────────


def test_list_payments_no_filter_returns_all() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent(reference="ref-1", idempotency_key="k1"))
    adapter.submit_payment(_make_intent(reference="ref-2", idempotency_key="k2"))
    assert len(adapter.list_payments()) == 2


def test_list_payments_filter_by_status() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(reference="ref-1", idempotency_key="k1"))
    adapter.submit_payment(_make_intent(reference="ref-2", idempotency_key="k2"))
    adapter.advance_to(r1.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    pending = adapter.list_payments(status=SepaPaymentStatus.PENDING)
    assert len(pending) == 1


def test_list_payments_filter_by_scheme() -> None:
    adapter = _adapter()
    adapter.submit_payment(
        _make_intent(rail=PaymentRail.SEPA_CT, reference="r1", idempotency_key="k1")
    )
    adapter.submit_payment(
        _make_intent(rail=PaymentRail.SEPA_INSTANT, reference="r2", idempotency_key="k2")
    )
    assert len(adapter.list_payments(scheme="SCT")) == 1
    assert len(adapter.list_payments(scheme="SCT_INST")) == 1


def test_list_payments_multi_tenant_isolation() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent(reference="r1", idempotency_key="k1", customer_id="cust-A"))
    adapter.submit_payment(_make_intent(reference="r2", idempotency_key="k2", customer_id="cust-B"))
    assert len(adapter.list_payments(customer_id="cust-A")) == 1
    assert len(adapter.list_payments(customer_id="cust-B")) == 1
    assert len(adapter.list_payments(customer_id="cust-C")) == 0


# ── Audit trail ───────────────────────────────────────────────────────────────


def test_audit_empty_initially() -> None:
    assert _adapter().collect_audit_records() == []


def test_audit_created_event_on_submit() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    records = adapter.collect_audit_records()
    assert len(records) == 1
    assert records[0].event_type == "CREATED"
    assert records[0].payment_id == result.provider_payment_id
    assert records[0].status_from is None
    assert records[0].status_to == SepaPaymentStatus.PENDING


def test_audit_submitted_event_on_advance_submitted() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    records = adapter.collect_audit_records()
    assert len(records) == 2
    assert records[1].event_type == "SUBMITTED"
    assert records[1].status_from == SepaPaymentStatus.PENDING
    assert records[1].status_to == SepaPaymentStatus.SUBMITTED


def test_audit_settled_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SETTLED)
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "SETTLED"
    assert records[-1].status_to == SepaPaymentStatus.SETTLED


def test_audit_rejected_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.REJECTED)
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "REJECTED"


def test_audit_cancelled_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, SepaPaymentStatus.CANCELLED)
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "CANCELLED"


def test_audit_record_is_separate_from_payment_result() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    audit = adapter.collect_audit_records()[0]
    assert isinstance(audit, SepaAuditRecord)
    assert not hasattr(result, "event_type")
    assert not hasattr(result, "status_from")


def test_audit_log_copy_semantics() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent())
    snapshot = adapter.collect_audit_records()
    adapter.advance_to(snapshot[0].payment_id, SepaPaymentStatus.SUBMITTED)
    assert len(snapshot) == 1
    assert len(adapter.collect_audit_records()) == 2


# ── _sepa_event_for helper ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (SepaPaymentStatus.SUBMITTED, "SUBMITTED"),
        (SepaPaymentStatus.SETTLED, "SETTLED"),
        (SepaPaymentStatus.REJECTED, "REJECTED"),
        (SepaPaymentStatus.CANCELLED, "CANCELLED"),
        (SepaPaymentStatus.PENDING, "CREATED"),
    ],
)
def test_sepa_event_for(status: SepaPaymentStatus, expected: str) -> None:
    assert _sepa_event_for(status) == expected
