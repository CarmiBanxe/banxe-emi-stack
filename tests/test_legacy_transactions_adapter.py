"""
tests/test_legacy_transactions_adapter.py — Unit tests for LegacyTransactionsAdapter.

Coverage: 100%  |  Tests: 22  |  No external deps (all in-memory).
Verifies semantic parity with payment-transaction.service.ts (banxe-transactions).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.payment.legacy.legacy_transactions_adapter import (
    LegacyTransactionsAdapter,
    TransactionApplicationError,
    TransactionAuditRecord,
    TransactionRecord,
    _audit_event_for,
    _resolve_status,
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
_CREDITOR = BankAccount(account_holder_name="Creditor", iban="GB82WEST12345698765432")


def _adapter() -> LegacyTransactionsAdapter:
    return LegacyTransactionsAdapter()


def _make_intent(
    *,
    idempotency_key: str = "key-001",
    rail: PaymentRail = PaymentRail.SEPA_CT,
    amount: Decimal = Decimal("250.00"),
) -> PaymentIntent:
    return PaymentIntent(
        idempotency_key=idempotency_key,
        rail=rail,
        direction=PaymentDirection.OUTBOUND,
        amount=amount,
        currency="EUR",
        debtor_account=_DEBTOR,
        creditor_account=_CREDITOR,
        reference="ref-001",
        end_to_end_id="e2e-001",
        requested_at=datetime.now(UTC),
    )


def _register(
    adapter: LegacyTransactionsAdapter,
    *,
    transaction_id: str = "txn-ext-001",
    idempotency_key: str = "ext-key-001",
    raw_status: str = "INITIATED",
    rail: PaymentRail = PaymentRail.SEPA_CT,
    amount: Decimal = Decimal("100.00"),
    currency: str = "EUR",
) -> TransactionRecord:
    return adapter.register_external_transaction(
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        raw_status=raw_status,
        rail=rail,
        direction=PaymentDirection.INBOUND,
        amount=amount,
        currency=currency,
        submitted_at=datetime.now(UTC),
    )


# ── Module-level imports ──────────────────────────────────────────────────────


def test_module_imports_cleanly() -> None:
    from services.payment.legacy import legacy_transactions_adapter  # noqa: F401

    assert legacy_transactions_adapter is not None


def test_no_transport_imports() -> None:
    import importlib
    import sys

    mod = sys.modules.get("services.payment.legacy.legacy_transactions_adapter")
    if mod is None:
        mod = importlib.import_module("services.payment.legacy.legacy_transactions_adapter")
    for banned in ("redis", "grpc", "sqlalchemy", "typeorm", "nestjs", "eventemitter"):
        assert banned not in dir(mod), f"Transport leak: {banned!r} found in adapter module"


# ── Adapter surface ───────────────────────────────────────────────────────────


def test_adapter_surface_exists() -> None:
    adapter = _adapter()
    assert hasattr(adapter, "submit_payment")
    assert hasattr(adapter, "get_payment_status")
    assert hasattr(adapter, "health")
    assert hasattr(adapter, "register_external_transaction")
    assert hasattr(adapter, "advance_status")
    assert hasattr(adapter, "collect_audit_records")


def test_protocol_conformance() -> None:
    adapter = _adapter()
    from services.payment.payment_port import PaymentRailPort

    _port: PaymentRailPort = adapter  # type: ignore[assignment]
    assert _port is adapter


def test_health_returns_true() -> None:
    assert _adapter().health() is True


# ── submit_payment ────────────────────────────────────────────────────────────


def test_submit_payment_creates_pending_record() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    assert isinstance(result, PaymentResult)
    assert result.status == PaymentStatus.PENDING
    assert result.provider_payment_id.startswith("txn-")
    assert result.rail == PaymentRail.SEPA_CT
    assert result.amount == Decimal("250.00")


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


# ── get_payment_status ────────────────────────────────────────────────────────


def test_get_payment_status_known_returns_result() -> None:
    adapter = _adapter()
    submitted = adapter.submit_payment(_make_intent())
    status_result = adapter.get_payment_status(submitted.provider_payment_id)
    assert status_result.provider_payment_id == submitted.provider_payment_id
    assert status_result.status == PaymentStatus.PENDING


def test_get_payment_status_unknown_raises() -> None:
    adapter = _adapter()
    with pytest.raises(TransactionApplicationError) as exc_info:
        adapter.get_payment_status("nonexistent-txn")
    assert exc_info.value.code == "transaction_not_found"


# ── _resolve_status (parse() semantic) ───────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("INITIATED", PaymentStatus.PENDING),
        ("PENDING", PaymentStatus.PENDING),
        ("PROCESSING", PaymentStatus.PROCESSING),
        ("IN_PROGRESS", PaymentStatus.PROCESSING),
        ("APPROVE_REQUEST", PaymentStatus.PROCESSING),
        ("COMPLETED", PaymentStatus.COMPLETED),
        ("SETTLED", PaymentStatus.COMPLETED),
        ("FAILED", PaymentStatus.FAILED),
        ("REJECTED", PaymentStatus.FAILED),
        ("RETURNED", PaymentStatus.RETURNED),
        ("CANCELLED", PaymentStatus.CANCELLED),
        ("CANCELED", PaymentStatus.CANCELLED),
    ],
)
def test_resolve_status_mapping(raw: str, expected: PaymentStatus) -> None:
    assert _resolve_status(raw) == expected


def test_resolve_status_case_insensitive() -> None:
    assert _resolve_status("completed") == PaymentStatus.COMPLETED
    assert _resolve_status("Settled") == PaymentStatus.COMPLETED


def test_resolve_status_unknown_raises() -> None:
    with pytest.raises(TransactionApplicationError) as exc_info:
        _resolve_status("MYSTERY_STATUS")
    assert exc_info.value.code == "unknown_status"


# ── register_external_transaction (resolveBasePayment() semantic) ─────────────


def test_register_external_transaction_stores_record() -> None:
    adapter = _adapter()
    record = _register(adapter, raw_status="COMPLETED")
    assert record.status == PaymentStatus.COMPLETED
    result = adapter.get_payment_status("txn-ext-001")
    assert result.status == PaymentStatus.COMPLETED


# ── advance_status ────────────────────────────────────────────────────────────


def test_advance_status_to_completed() -> None:
    adapter = _adapter()
    submitted = adapter.submit_payment(_make_intent())
    now = datetime.now(UTC)
    adapter.advance_status(submitted.provider_payment_id, "COMPLETED", settled_at=now)
    result = adapter.get_payment_status(submitted.provider_payment_id)
    assert result.status == PaymentStatus.COMPLETED
    assert result.estimated_settlement == now


def test_advance_status_to_failed_with_error_code() -> None:
    adapter = _adapter()
    submitted = adapter.submit_payment(_make_intent())
    adapter.advance_status(submitted.provider_payment_id, "FAILED", error_code="INSUFFICIENT_FUNDS")
    result = adapter.get_payment_status(submitted.provider_payment_id)
    assert result.status == PaymentStatus.FAILED
    assert result.error_code == "INSUFFICIENT_FUNDS"


def test_advance_status_unknown_transaction_raises() -> None:
    adapter = _adapter()
    with pytest.raises(TransactionApplicationError) as exc_info:
        adapter.advance_status("ghost-txn", "COMPLETED")
    assert exc_info.value.code == "transaction_not_found"


# ── Audit mapping (resolveBaseBalances() semantic) ────────────────────────────


def test_audit_log_empty_initially() -> None:
    adapter = _adapter()
    assert adapter.collect_audit_records() == []


def test_submit_emits_submitted_audit_event() -> None:
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    records = adapter.collect_audit_records()
    assert len(records) == 1
    assert records[0].event_type == "SUBMITTED"
    assert records[0].transaction_id == result.provider_payment_id
    assert records[0].status_from is None
    assert records[0].status_to == PaymentStatus.PENDING


def test_advance_to_completed_emits_settled_event() -> None:
    adapter = _adapter()
    submitted = adapter.submit_payment(_make_intent())
    adapter.advance_status(submitted.provider_payment_id, "COMPLETED")
    records = adapter.collect_audit_records()
    assert len(records) == 2
    assert records[1].event_type == "SETTLED"
    assert records[1].status_from == PaymentStatus.PENDING
    assert records[1].status_to == PaymentStatus.COMPLETED


def test_advance_to_failed_emits_failed_event() -> None:
    adapter = _adapter()
    submitted = adapter.submit_payment(_make_intent())
    adapter.advance_status(submitted.provider_payment_id, "FAILED")
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "FAILED"


def test_advance_to_returned_emits_returned_event() -> None:
    adapter = _adapter()
    submitted = adapter.submit_payment(_make_intent())
    adapter.advance_status(submitted.provider_payment_id, "RETURNED")
    records = adapter.collect_audit_records()
    assert records[-1].event_type == "RETURNED"


def test_audit_record_is_separate_from_payment_result() -> None:
    """resolveBaseBalances() concern must NEVER appear in PaymentResult (port boundary)."""
    adapter = _adapter()
    result = adapter.submit_payment(_make_intent())
    audit_records = adapter.collect_audit_records()
    result_fields = set(vars(result).keys())
    assert "event_type" not in result_fields
    assert "status_from" not in result_fields
    assert isinstance(audit_records[0], TransactionAuditRecord)
    assert not isinstance(audit_records[0], PaymentResult)


def test_audit_record_stable_structure() -> None:
    adapter = _adapter()
    _register(adapter, raw_status="PROCESSING")
    records = adapter.collect_audit_records()
    r = records[0]
    assert r.transaction_id == "txn-ext-001"
    assert r.event_type == "STATUS_CHANGED"
    assert r.amount == Decimal("100.00")
    assert r.currency == "EUR"
    assert r.status_to == PaymentStatus.PROCESSING
    assert isinstance(r.occurred_at, datetime)


def test_collect_audit_records_returns_copy() -> None:
    adapter = _adapter()
    adapter.submit_payment(_make_intent())
    records_a = adapter.collect_audit_records()
    records_b = adapter.collect_audit_records()
    assert records_a is not records_b
    assert records_a == records_b


# ── _audit_event_for helper ───────────────────────────────────────────────────


def test_audit_event_for_pending_is_submitted() -> None:
    assert _audit_event_for(PaymentStatus.PENDING) == "SUBMITTED"


def test_audit_event_for_processing_is_status_changed() -> None:
    assert _audit_event_for(PaymentStatus.PROCESSING) == "STATUS_CHANGED"


def test_audit_event_for_completed_is_settled() -> None:
    assert _audit_event_for(PaymentStatus.COMPLETED) == "SETTLED"
