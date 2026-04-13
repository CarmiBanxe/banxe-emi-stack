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


# ── S13-05: Coverage gap tests (lines 53-55, 213-215, 258-260, 266-313, 343-363) ─


class TestRailExceptionHandling:
    """Lines 213-215: rail.submit_payment() raises → FAILED result, audit still written."""

    def test_rail_exception_returns_failed_status(self):
        from unittest.mock import MagicMock

        ch = InMemoryReconClient()
        rail = MagicMock()
        rail.submit_payment.side_effect = RuntimeError("Rail is down")
        svc = PaymentService(rail=rail, ch_client=ch)
        result = svc.send_fps(amount=Decimal("50.00"), beneficiary=uk_account(), reference="Test")
        assert result.status == PaymentStatus.FAILED
        assert result.error_code == "SUBMISSION_ERROR"
        assert "Rail is down" in (result.error_message or "")

    def test_rail_exception_audit_still_written(self):
        from unittest.mock import MagicMock

        ch = InMemoryReconClient()
        rail = MagicMock()
        rail.submit_payment.side_effect = RuntimeError("Timeout")
        svc = PaymentService(rail=rail, ch_client=ch)
        svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R")
        assert ch.call_count == 1  # audit written even on rail failure


class TestClickhouseAuditFailure:
    """Lines 258-260: ClickHouse.execute() raises → error logged, payment result returned."""

    def test_ch_exception_does_not_suppress_payment_result(self):
        from unittest.mock import MagicMock

        adapter = MockPaymentAdapter()
        ch = MagicMock()
        ch.execute.side_effect = Exception("ClickHouse unavailable")
        svc = PaymentService(rail=adapter, ch_client=ch)
        result = svc.send_fps(amount=Decimal("25.00"), beneficiary=uk_account(), reference="R")
        # Payment should succeed even if audit write fails (I-24 note)
        assert result is not None
        assert result.status == PaymentStatus.COMPLETED


class TestEventBusEmission:
    """Lines 266-290: _emit_event() with event bus wired."""

    def _svc_with_event_bus(self, event_bus):
        ch = InMemoryReconClient()
        adapter = MockPaymentAdapter()
        return PaymentService(rail=adapter, ch_client=ch, event_bus=event_bus)

    def test_emit_event_called_on_completed_payment(self):
        from unittest.mock import MagicMock

        bus = MagicMock()
        svc = self._svc_with_event_bus(bus)
        svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R")
        bus.publish.assert_called_once()

    def test_emit_event_called_on_failed_payment(self):
        from unittest.mock import MagicMock

        bus = MagicMock()
        ch = InMemoryReconClient()
        adapter = MockPaymentAdapter(failure_rate=1.0)
        svc = PaymentService(rail=adapter, ch_client=ch, event_bus=bus)
        svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R")
        bus.publish.assert_called_once()

    def test_event_bus_failure_does_not_suppress_payment(self):
        from unittest.mock import MagicMock

        bus = MagicMock()
        bus.publish.side_effect = Exception("Bus down")
        svc = self._svc_with_event_bus(bus)
        result = svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R")
        assert result is not None
        assert result.status == PaymentStatus.COMPLETED

    def test_no_event_bus_skips_emit(self):
        """Lines 264-265: early return when event_bus is None."""
        svc, _, _ = make_service()  # no event_bus
        # Should not raise
        result = svc.send_fps(amount=Decimal("5.00"), beneficiary=uk_account(), reference="R")
        assert result.status == PaymentStatus.COMPLETED


class TestN8nWebhook:
    """Lines 296-313: _notify_n8n() called for FAILED payments when N8N_WEBHOOK_URL set."""

    def test_n8n_called_on_failed_payment(self, monkeypatch):
        from unittest.mock import patch

        monkeypatch.setenv("N8N_WEBHOOK_URL", "http://n8n-test:5678/webhook/payment")
        # Reload module-level constant
        import services.payment.payment_service as psvc

        psvc.N8N_WEBHOOK_URL = "http://n8n-test:5678/webhook/payment"

        ch = InMemoryReconClient()
        adapter = MockPaymentAdapter(failure_rate=1.0)
        svc = PaymentService(rail=adapter, ch_client=ch)

        with patch("httpx.post") as mock_post:
            svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R")
            mock_post.assert_called_once()
            call_json = mock_post.call_args[1]["json"]
            assert call_json["event"] == "payment_failed"

        psvc.N8N_WEBHOOK_URL = ""  # reset

    def test_n8n_not_called_on_completed_payment(self, monkeypatch):
        from unittest.mock import patch

        import services.payment.payment_service as psvc

        psvc.N8N_WEBHOOK_URL = "http://n8n-test:5678/webhook/payment"

        svc, _, _ = make_service()
        with patch("httpx.post") as mock_post:
            svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R")
            mock_post.assert_not_called()

        psvc.N8N_WEBHOOK_URL = ""

    def test_n8n_failure_does_not_suppress_result(self, monkeypatch):
        from unittest.mock import patch

        import services.payment.payment_service as psvc

        psvc.N8N_WEBHOOK_URL = "http://n8n-test:5678/webhook/payment"

        ch = InMemoryReconClient()
        adapter = MockPaymentAdapter(failure_rate=1.0)
        svc = PaymentService(rail=adapter, ch_client=ch)

        with patch("httpx.post", side_effect=Exception("n8n down")):
            result = svc.send_fps(amount=Decimal("10.00"), beneficiary=uk_account(), reference="R")
        assert result.status == PaymentStatus.FAILED

        psvc.N8N_WEBHOOK_URL = ""


class TestBuildPaymentServiceFactory:
    """Lines 343-363: build_payment_service() both branches."""

    def test_build_with_mock_adapter(self, monkeypatch):
        from services.payment.payment_service import build_payment_service

        monkeypatch.setenv("PAYMENT_ADAPTER", "mock")
        import services.payment.payment_service as psvc

        psvc.PAYMENT_ADAPTER = "mock"

        from services.recon.clickhouse_client import InMemoryReconClient

        svc = build_payment_service(ch_client=InMemoryReconClient())
        assert svc is not None
        assert isinstance(svc, PaymentService)

    def test_get_event_bus_types_importable(self):
        """Lines 53-55: _get_event_bus_types() lazy import works."""
        from services.payment.payment_service import _get_event_bus_types

        types = _get_event_bus_types()
        assert len(types) == 3  # BanxeEventType, DomainEvent, InMemoryEventBus
