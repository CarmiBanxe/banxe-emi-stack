"""
test_payment_service.py — Unit tests for Payment Rails layer
IL-014 | Block C-fps + C-sepa | banxe-emi-stack

Tests cover:
  - PaymentIntent validation (Decimal, currency/rail consistency, amount limits)
  - MockPaymentAdapter: FPS → COMPLETED, SEPA CT → PROCESSING, idempotency
  - MockPaymentAdapter: failure simulation
  - PaymentService: send_fps, send_sepa_ct, send_sepa_instant
  - PaymentService: audit trail write on every submission
  - PaymentService: FAILED result still written to audit

Run:
    cd /home/mmber/banxe-emi-stack
    pytest tests/test_payment_service.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

import pytest

from services.payment.mock_payment_adapter import MockPaymentAdapter
from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentStatus,
)
from services.payment.payment_service import PaymentService
from services.recon.clickhouse_client import InMemoryReconClient

# ── Helpers ───────────────────────────────────────────────────────────────────


def uk_account(name: str = "Jane Doe") -> BankAccount:
    return BankAccount(
        account_holder_name=name,
        sort_code="20-00-00",
        account_number="12345678",
        country_code="GB",
    )


def eu_account(name: str = "Hans Schmidt") -> BankAccount:
    return BankAccount(
        account_holder_name=name,
        iban="DE89370400440532013000",
        bic="COBADEFFXXX",
        country_code="DE",
    )


def banxe_gbp_account() -> BankAccount:
    return BankAccount(
        account_holder_name="Banxe Ltd",
        sort_code="00-00-00",
        account_number="00000000",
        country_code="GB",
    )


def banxe_eur_account() -> BankAccount:
    return BankAccount(
        account_holder_name="Banxe Ltd",
        iban="GB00XXXX00000000000000",
        country_code="GB",
    )


def make_fps_intent(amount: str = "100.00") -> PaymentIntent:
    return PaymentIntent(
        idempotency_key=str(uuid.uuid4()),
        rail=PaymentRail.FPS,
        direction=PaymentDirection.OUTBOUND,
        amount=Decimal(amount),
        currency="GBP",
        debtor_account=banxe_gbp_account(),
        creditor_account=uk_account(),
        reference="Test Payment",
        end_to_end_id="E2E-TEST-001",
        requested_at=datetime.now(UTC),
    )


def make_service(
    failure_rate: float = 0.0,
) -> tuple[PaymentService, MockPaymentAdapter, InMemoryReconClient]:
    adapter = MockPaymentAdapter(failure_rate=failure_rate)
    ch = InMemoryReconClient()
    svc = PaymentService(rail=adapter, ch_client=ch)
    return svc, adapter, ch


# ── PaymentIntent validation ──────────────────────────────────────────────────


class TestPaymentIntentValidation:
    def test_amount_must_be_decimal(self):
        with pytest.raises(TypeError, match="Decimal"):
            PaymentIntent(
                idempotency_key=str(uuid.uuid4()),
                rail=PaymentRail.FPS,
                direction=PaymentDirection.OUTBOUND,
                amount=100.0,  # float — must raise
                currency="GBP",
                debtor_account=banxe_gbp_account(),
                creditor_account=uk_account(),
                reference="test",
                end_to_end_id="E2E-1",
                requested_at=datetime.now(UTC),
            )

    def test_amount_must_be_positive(self):
        with pytest.raises(ValueError, match="positive"):
            PaymentIntent(
                idempotency_key=str(uuid.uuid4()),
                rail=PaymentRail.FPS,
                direction=PaymentDirection.OUTBOUND,
                amount=Decimal("0"),
                currency="GBP",
                debtor_account=banxe_gbp_account(),
                creditor_account=uk_account(),
                reference="test",
                end_to_end_id="E2E-1",
                requested_at=datetime.now(UTC),
            )

    def test_fps_requires_gbp(self):
        with pytest.raises(ValueError, match="FPS.*GBP"):
            PaymentIntent(
                idempotency_key=str(uuid.uuid4()),
                rail=PaymentRail.FPS,
                direction=PaymentDirection.OUTBOUND,
                amount=Decimal("100.00"),
                currency="EUR",  # wrong currency for FPS
                debtor_account=banxe_gbp_account(),
                creditor_account=uk_account(),
                reference="test",
                end_to_end_id="E2E-1",
                requested_at=datetime.now(UTC),
            )

    def test_sepa_requires_eur(self):
        with pytest.raises(ValueError, match="EUR"):
            PaymentIntent(
                idempotency_key=str(uuid.uuid4()),
                rail=PaymentRail.SEPA_CT,
                direction=PaymentDirection.OUTBOUND,
                amount=Decimal("100.00"),
                currency="GBP",  # wrong currency for SEPA
                debtor_account=banxe_eur_account(),
                creditor_account=eu_account(),
                reference="test",
                end_to_end_id="E2E-1",
                requested_at=datetime.now(UTC),
            )

    def test_valid_fps_intent_created(self):
        intent = make_fps_intent("500.00")
        assert intent.amount == Decimal("500.00")
        assert isinstance(intent.amount, Decimal)
        assert intent.rail == PaymentRail.FPS
        assert intent.currency == "GBP"


# ── MockPaymentAdapter ────────────────────────────────────────────────────────


class TestMockPaymentAdapter:
    def test_fps_completes_instantly(self):
        adapter = MockPaymentAdapter()
        result = adapter.submit_payment(make_fps_intent())
        assert result.status == PaymentStatus.COMPLETED

    def test_sepa_ct_returns_processing(self):
        adapter = MockPaymentAdapter()
        intent = PaymentIntent(
            idempotency_key=str(uuid.uuid4()),
            rail=PaymentRail.SEPA_CT,
            direction=PaymentDirection.OUTBOUND,
            amount=Decimal("250.00"),
            currency="EUR",
            debtor_account=banxe_eur_account(),
            creditor_account=eu_account(),
            reference="Invoice 2026-001",
            end_to_end_id="E2E-SEPA-001",
            requested_at=datetime.now(UTC),
        )
        result = adapter.submit_payment(intent)
        assert result.status == PaymentStatus.PROCESSING

    def test_sepa_instant_completes_instantly(self):
        adapter = MockPaymentAdapter()
        intent = PaymentIntent(
            idempotency_key=str(uuid.uuid4()),
            rail=PaymentRail.SEPA_INSTANT,
            direction=PaymentDirection.OUTBOUND,
            amount=Decimal("75.50"),
            currency="EUR",
            debtor_account=banxe_eur_account(),
            creditor_account=eu_account(),
            reference="Instant Payment",
            end_to_end_id="E2E-INST-001",
            requested_at=datetime.now(UTC),
        )
        result = adapter.submit_payment(intent)
        assert result.status == PaymentStatus.COMPLETED

    def test_idempotency_same_key_same_result(self):
        adapter = MockPaymentAdapter()
        intent = make_fps_intent()
        result1 = adapter.submit_payment(intent)
        result2 = adapter.submit_payment(intent)  # same idempotency_key
        assert result1.provider_payment_id == result2.provider_payment_id
        assert result1.status == result2.status
        assert adapter.submission_count == 1  # only one actual submission

    def test_amount_is_decimal_in_result(self):
        adapter = MockPaymentAdapter()
        result = adapter.submit_payment(make_fps_intent("999.99"))
        assert isinstance(result.amount, Decimal)
        assert result.amount == Decimal("999.99")

    def test_reset_clears_state(self):
        adapter = MockPaymentAdapter()
        adapter.submit_payment(make_fps_intent())
        adapter.reset()
        assert adapter.submission_count == 0

    def test_health_check_returns_true(self):
        assert MockPaymentAdapter().health_check() is True


# ── PaymentService ────────────────────────────────────────────────────────────


class TestPaymentService:
    def test_send_fps_returns_completed(self):
        svc, _, _ = make_service()
        result = svc.send_fps(
            amount=Decimal("150.00"),
            beneficiary=uk_account(),
            reference="Test FPS",
        )
        assert result.status == PaymentStatus.COMPLETED
        assert result.rail == PaymentRail.FPS
        assert result.currency == "GBP"

    def test_send_sepa_ct_returns_processing(self):
        svc, _, _ = make_service()
        result = svc.send_sepa_ct(
            amount=Decimal("500.00"),
            beneficiary=eu_account(),
            reference="Invoice SEPA",
        )
        assert result.status == PaymentStatus.PROCESSING
        assert result.rail == PaymentRail.SEPA_CT
        assert result.currency == "EUR"

    def test_send_sepa_instant_returns_completed(self):
        svc, _, _ = make_service()
        result = svc.send_sepa_instant(
            amount=Decimal("99.99"),
            beneficiary=eu_account(),
            reference="Instant EUR",
        )
        assert result.status == PaymentStatus.COMPLETED
        assert result.rail == PaymentRail.SEPA_INSTANT

    def test_fps_amount_limit_enforced(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError, match="FPS limit"):
            svc.send_fps(
                amount=Decimal("1000001.00"),
                beneficiary=uk_account(),
                reference="Over limit",
            )

    def test_sepa_instant_amount_limit_enforced(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError, match="SEPA Instant limit"):
            svc.send_sepa_instant(
                amount=Decimal("100001.00"),
                beneficiary=eu_account(),
                reference="Over SEPA limit",
            )

    def test_audit_trail_written_for_every_payment(self):
        svc, _, ch = make_service()
        svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R1")
        svc.send_fps(amount=Decimal("20.00"), beneficiary=uk_account(), reference="R2")
        assert ch.call_count == 2

    def test_audit_trail_written_even_on_failure(self):
        """FCA I-24: failed payments MUST appear in audit trail."""
        svc, _, ch = make_service(failure_rate=1.0)  # 100% failure
        result = svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="Fail")
        assert result.status == PaymentStatus.FAILED
        assert ch.call_count == 1  # audit still written

    def test_audit_contains_correct_fields(self):
        svc, _, ch = make_service()
        svc.send_fps(
            amount=Decimal("42.00"),
            beneficiary=uk_account("Bob Smith"),
            reference="REF-042",
        )
        event = ch.events[0]
        assert event["amount"] == "42.00"
        assert event["currency"] == "GBP"
        assert event["rail"] == "FPS"
        assert event["creditor_name"] == "Bob Smith"
        assert event["reference"] == "REF-042"
