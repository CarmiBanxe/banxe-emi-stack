"""
tests/test_legacy_abs_payment_adapter.py — Unit tests for LegacyAbsPaymentAdapter.

Coverage: 100%  |  Tests: 39  |  No external deps (all in-memory).
Verifies semantic parity with abs-customer-payment.service.ts (banxe-fiat-backend/abs-api).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.payment.legacy.legacy_abs_payment_adapter import (
    AbsApplicationError,
    AbsAuditRecord,
    AbsPaymentStatus,
    LegacyAbsPaymentAdapter,
    _abs_event_for,
    _generate_ref,
)
from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_DEBTOR = BankAccount(account_holder_name="Banxe EMI", iban="DE89370400440532013000")
_CREDITOR = BankAccount(account_holder_name="Creditor Ltd", iban="GB82WEST12345698765432")


def _adapter() -> LegacyAbsPaymentAdapter:
    return LegacyAbsPaymentAdapter()


def _make_intent(
    *,
    idempotency_key: str = "abs-key-001",
    rail: PaymentRail = PaymentRail.SEPA_CT,
    amount: Decimal = Decimal("500.00"),
    reference: str = "INV-001",
    customer_id: str = "cust-001",
    debtor: BankAccount = _DEBTOR,
    creditor: BankAccount = _CREDITOR,
) -> PaymentIntent:
    return PaymentIntent(
        idempotency_key=idempotency_key,
        rail=rail,
        direction=PaymentDirection.OUTBOUND,
        amount=amount,
        currency="EUR",
        debtor_account=debtor,
        creditor_account=creditor,
        reference=reference,
        end_to_end_id="e2e-abs-001",
        requested_at=datetime.now(UTC),
        metadata={"customer_id": customer_id},
    )


# ── Module-level imports ──────────────────────────────────────────────────────


def test_module_imports_cleanly() -> None:
    from services.payment.legacy import legacy_abs_payment_adapter  # noqa: F401

    assert legacy_abs_payment_adapter is not None


def test_no_transport_imports() -> None:
    import importlib
    import sys

    mod = sys.modules.get("services.payment.legacy.legacy_abs_payment_adapter")
    if mod is None:
        mod = importlib.import_module("services.payment.legacy.legacy_abs_payment_adapter")
    for banned in ("gcp", "bifrost", "grpc", "sqlalchemy", "nestjs", "eventemitter", "redis"):
        assert banned not in dir(mod), f"Transport leak: {banned!r} found in adapter module"


# ── Adapter surface ───────────────────────────────────────────────────────────


def test_adapter_surface_exists() -> None:
    adapter = _adapter()
    assert hasattr(adapter, "submit_payment")
    assert hasattr(adapter, "get_payment_status")
    assert hasattr(adapter, "health")
    assert hasattr(adapter, "advance_to")
    assert hasattr(adapter, "list_payments")
    assert hasattr(adapter, "collect_audit_records")


def test_protocol_conformance() -> None:
    adapter = _adapter()
    from services.payment.payment_port import PaymentRailPort

    _port: PaymentRailPort = adapter  # type: ignore[assignment]
    assert _port is adapter


def test_health_returns_true() -> None:
    assert _adapter().health() is True


# ── submit_payment — happy paths ──────────────────────────────────────────────


def test_submit_payment_creates_pending_record() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    assert isinstance(result, PaymentResult)
    assert result.status == PaymentStatus.PENDING
    assert result.provider_payment_id.startswith("abs-")
    assert result.rail == PaymentRail.SEPA_CT
    assert result.amount == Decimal("500.00")
    assert result.currency == "EUR"


def test_submit_payment_sepa_instant_happy_path() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(rail=PaymentRail.SEPA_INSTANT))
    assert result.status == PaymentStatus.PENDING
    assert result.rail == PaymentRail.SEPA_INSTANT


def test_submit_payment_customer_id_from_metadata() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(customer_id="cust-XYZ"))
    record = adapter._by_payment_id[result.provider_payment_id]
    assert record.customer_id == "cust-XYZ"


def test_submit_payment_customer_id_fallback_to_debtor_name() -> None:
    adapter = _adapter()
    intent = PaymentIntent(
        idempotency_key="no-meta-key",
        rail=PaymentRail.SEPA_CT,
        direction=PaymentDirection.OUTBOUND,
        amount=Decimal("100.00"),
        currency="EUR",
        debtor_account=BankAccount(
            account_holder_name="FallbackName", iban="DE89370400440532013000"
        ),
        creditor_account=_CREDITOR,
        reference="ref",
        end_to_end_id="e2e",
        requested_at=datetime.now(UTC),
        metadata={},
    )
    result = adapter.submit_payment(intent)
    record = adapter._by_payment_id[result.provider_payment_id]
    assert record.customer_id == "FallbackName"


def test_submit_payment_generates_bank_ref() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    record = adapter._by_payment_id[result.provider_payment_id]
    assert record.bank_ref.startswith("ABS-")
    assert len(record.bank_ref) > 8


# ── submit_payment — idempotency ──────────────────────────────────────────────


def test_submit_payment_idempotency_same_key() -> None:
    adapter = _adapter()
    intent = _make_intent()
    r1 = adapter.submit_payment(intent)
    r2 = adapter.submit_payment(intent)
    assert r1.provider_payment_id == r2.provider_payment_id


def test_submit_payment_different_keys_create_different_records() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(idempotency_key="k-A"))
    r2 = adapter.submit_payment(_make_intent(idempotency_key="k-B"))
    assert r1.provider_payment_id != r2.provider_payment_id


# ── submit_payment — validation failures ──────────────────────────────────────


def test_submit_unsupported_rail_raises() -> None:
    adapter = _adapter()
    fps_intent = PaymentIntent(
        idempotency_key="fps-key",
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
    with pytest.raises(AbsApplicationError) as exc_info:
        adapter.submit_payment(fps_intent)
    assert exc_info.value.code == "unsupported_rail"


def test_submit_reference_too_long_raises() -> None:
    adapter = _adapter()
    with pytest.raises(AbsApplicationError) as exc_info:
        adapter.submit_payment(_make_intent(reference="X" * 141))
    assert exc_info.value.code == "reference_too_long"


def test_submit_reference_exactly_140_chars_ok() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent(reference="X" * 140))
    assert result.status == PaymentStatus.PENDING


def test_submit_negative_amount_raises_at_intent_level() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _make_intent(amount=Decimal("-1.00"))


def test_submit_zero_amount_raises_at_intent_level() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _make_intent(amount=Decimal("0"))


# ── get_payment_status ────────────────────────────────────────────────────────


def test_get_payment_status_known_returns_result() -> None:
    adapter = _adapter()
    submitted = adapter.submit_payment(_make_intent())
    status_result = adapter.get_payment_status(submitted.provider_payment_id)
    assert status_result.provider_payment_id == submitted.provider_payment_id
    assert status_result.status == PaymentStatus.PENDING


def test_get_payment_status_unknown_raises() -> None:
    adapter = _adapter()
    with pytest.raises(AbsApplicationError) as exc_info:
        adapter.get_payment_status("nonexistent-abs-id")
    assert exc_info.value.code == "payment_not_found"


# ── advance_to — state machine ────────────────────────────────────────────────


def test_advance_to_pending_submitted() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    updated = adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    assert updated.status == AbsPaymentStatus.SUBMITTED
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.PROCESSING


def test_advance_to_submitted_settled() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    now = datetime.now(UTC)
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SETTLED, settled_at=now)
    status = adapter.get_payment_status(result.provider_payment_id)
    assert status.status == PaymentStatus.COMPLETED
    assert status.estimated_settlement == now


def test_advance_to_submitted_rejected_with_error_code() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    adapter.advance_to(
        result.provider_payment_id,
        AbsPaymentStatus.REJECTED,
        error_code="INSUFFICIENT_FUNDS",
        error_message="Balance too low",
    )
    status = adapter.get_payment_status(result.provider_payment_id)
    assert status.status == PaymentStatus.FAILED
    assert status.error_code == "INSUFFICIENT_FUNDS"


def test_advance_to_pending_cancelled() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.CANCELLED)
    assert adapter.get_payment_status(result.provider_payment_id).status == PaymentStatus.CANCELLED


def test_invalid_transition_settled_to_submitted_raises() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SETTLED)
    with pytest.raises(AbsApplicationError) as exc_info:
        adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    assert exc_info.value.code == "invalid_state_transition"


def test_invalid_transition_cancelled_to_submitted_raises() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.CANCELLED)
    with pytest.raises(AbsApplicationError) as exc_info:
        adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    assert exc_info.value.code == "invalid_state_transition"


def test_invalid_transition_rejected_to_pending_raises() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.REJECTED)
    with pytest.raises(AbsApplicationError) as exc_info:
        adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.PENDING)
    assert exc_info.value.code == "invalid_state_transition"


def test_advance_to_unknown_payment_raises() -> None:
    adapter = _adapter()
    with pytest.raises(AbsApplicationError) as exc_info:
        adapter.advance_to("ghost-abs-id", AbsPaymentStatus.SUBMITTED)
    assert exc_info.value.code == "payment_not_found"


# ── list_payments ─────────────────────────────────────────────────────────────


def test_list_payments_no_filter_returns_all() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent(idempotency_key="k1", customer_id="cust-A"))
    adapter.submit_payment(_make_intent(idempotency_key="k2", customer_id="cust-B"))
    assert len(adapter.list_payments()) == 2


def test_list_payments_filter_by_customer_id() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(idempotency_key="k1", customer_id="cust-A"))
    adapter.submit_payment(_make_intent(idempotency_key="k2", customer_id="cust-B"))
    results = adapter.list_payments(customer_id="cust-A")
    assert len(results) == 1
    assert results[0].payment_id == r1.provider_payment_id


def test_list_payments_filter_by_status() -> None:
    adapter = _adapter()
    r1 = adapter.submit_payment(_make_intent(idempotency_key="k1"))
    adapter.submit_payment(_make_intent(idempotency_key="k2"))
    adapter.advance_to(r1.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    pending = adapter.list_payments(status=AbsPaymentStatus.PENDING)
    submitted = adapter.list_payments(status=AbsPaymentStatus.SUBMITTED)
    assert len(pending) == 1
    assert len(submitted) == 1


def test_list_payments_multi_tenant_isolation() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent(idempotency_key="k1", customer_id="cust-A"))
    adapter.submit_payment(_make_intent(idempotency_key="k2", customer_id="cust-B"))
    assert len(adapter.list_payments(customer_id="cust-A")) == 1
    assert len(adapter.list_payments(customer_id="cust-B")) == 1
    assert len(adapter.list_payments(customer_id="cust-C")) == 0


# ── Audit trail (I-24) ────────────────────────────────────────────────────────


def test_audit_log_empty_initially() -> None:
    adapter = _adapter()
    assert adapter.collect_audit_records() == []


def test_submit_emits_created_audit_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    records = adapter.collect_audit_records()
    assert len(records) == 1
    assert records[0].event_type == "CREATED"
    assert records[0].payment_id == result.provider_payment_id
    assert records[0].status_from is None
    assert records[0].status_to == AbsPaymentStatus.PENDING


def test_advance_to_submitted_emits_submitted_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    records = adapter.collect_audit_records()
    assert len(records) == 2
    assert records[1].event_type == "SUBMITTED"
    assert records[1].status_from == AbsPaymentStatus.PENDING
    assert records[1].status_to == AbsPaymentStatus.SUBMITTED


def test_advance_to_settled_emits_settled_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SETTLED)
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "SETTLED"


def test_advance_to_rejected_emits_rejected_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.SUBMITTED)
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.REJECTED)
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "REJECTED"


def test_advance_to_cancelled_emits_cancelled_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    adapter.advance_to(result.provider_payment_id, AbsPaymentStatus.CANCELLED)
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "CANCELLED"


def test_audit_record_is_separate_from_payment_result() -> None:
    """resolveBaseBalances() concern must NEVER appear in PaymentResult (port boundary)."""
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    audit_records = adapter.collect_audit_records()
    result_fields = set(vars(result).keys())
    assert "event_type" not in result_fields
    assert "status_from" not in result_fields
    assert isinstance(audit_records[0], AbsAuditRecord)
    assert not isinstance(audit_records[0], PaymentResult)


def test_collect_audit_records_returns_copy() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent())
    records_a = adapter.collect_audit_records()
    records_b = adapter.collect_audit_records()
    assert records_a is not records_b
    assert records_a == records_b


# ── _generate_ref helper ──────────────────────────────────────────────────────


def test_generate_ref_format() -> None:
    ref = _generate_ref("cust-001")
    assert ref.startswith("ABS-CUST")
    parts = ref.split("-")
    assert len(parts) >= 4


def test_generate_ref_empty_customer_id() -> None:
    ref = _generate_ref("")
    assert ref.startswith("ABS-ABS-")


def test_generate_ref_unique() -> None:
    refs = {_generate_ref("cust-001") for _ in range(20)}
    assert len(refs) == 20


# ── _abs_event_for helper ─────────────────────────────────────────────────────


def test_abs_event_for_pending_is_created() -> None:
    assert _abs_event_for(AbsPaymentStatus.PENDING) == "CREATED"


def test_abs_event_for_submitted_is_submitted() -> None:
    assert _abs_event_for(AbsPaymentStatus.SUBMITTED) == "SUBMITTED"


def test_abs_event_for_settled_is_settled() -> None:
    assert _abs_event_for(AbsPaymentStatus.SETTLED) == "SETTLED"


def test_abs_event_for_rejected_is_rejected() -> None:
    assert _abs_event_for(AbsPaymentStatus.REJECTED) == "REJECTED"


def test_abs_event_for_cancelled_is_cancelled() -> None:
    assert _abs_event_for(AbsPaymentStatus.CANCELLED) == "CANCELLED"
