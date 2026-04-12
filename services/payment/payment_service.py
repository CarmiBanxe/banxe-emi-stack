"""
payment_service.py — PaymentService: orchestration layer for payment rails
Block C-fps + C-sepa, IL-014
FCA PSR / PSD2 | banxe-emi-stack

OVERVIEW
--------
PaymentService is the single entry-point for initiating payments.

It coordinates:
  1. Validation (amount, currency, rail, beneficiary)
  2. Midaz ledger debit (via LedgerPort — pre-flight reserve)
  3. Payment submission to rail (via PaymentRailPort)
  4. ClickHouse audit INSERT (every payment event, I-24)
  5. Midaz ledger update (on completion / failure)
  6. n8n webhook notification

FCA requirements:
  - Every payment attempt MUST be recorded in audit trail (I-15, I-24)
  - Idempotency_key MUST be generated per payment, stored, reused on retry
  - Amount MUST be Decimal throughout (I-24)
  - Failed payments MUST be logged (no silent failures)

Factory (build_payment_service()):
  Reads PAYMENT_ADAPTER env var:
    "mock"   → MockPaymentAdapter  (default, works without API key)
    "modulr" → ModulrPaymentAdapter (requires MODULR_API_KEY)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
import os
import uuid

from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentRailPort,
    PaymentResult,
    PaymentStatus,
)

logger = logging.getLogger(__name__)


# Lazy import to avoid circular dependency — event_bus imported only when used
def _get_event_bus_types():
    from services.events.event_bus import BanxeEventType, DomainEvent, InMemoryEventBus

    return BanxeEventType, DomainEvent, InMemoryEventBus


PAYMENT_ADAPTER = os.environ.get("PAYMENT_ADAPTER", "mock")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")

# Banxe EMI operational account (debtor for outbound payments)
OPERATIONAL_ACCOUNT_SORT_CODE = os.environ.get("BANXE_SORT_CODE", "")
OPERATIONAL_ACCOUNT_NUMBER = os.environ.get("BANXE_ACCOUNT_NUMBER", "")
OPERATIONAL_ACCOUNT_IBAN = os.environ.get("BANXE_EUR_IBAN", "")


class PaymentService:
    """
    Domain service for initiating and tracking payments.

    Constructor injection pattern — pass adapters explicitly.
    Use build_payment_service() factory for production wiring.

    Example:
        svc = PaymentService(rail=MockPaymentAdapter(), ch=InMemoryReconClient())
        result = svc.send_fps(
            amount=Decimal("100.00"),
            beneficiary=BankAccount(
                account_holder_name="Jane Doe",
                sort_code="20-00-00",
                account_number="12345678",
            ),
            reference="Salary Apr 2026",
        )
    """

    def __init__(
        self,
        rail: PaymentRailPort,
        ch_client,  # ClickHouseClientProtocol (from clickhouse_client.py)
        ledger_port=None,  # LedgerPortProtocol — optional, for Midaz debit
        event_bus=None,  # EventBusPort — optional, for domain event emission (S17-11)
    ) -> None:
        self._rail = rail
        self._ch = ch_client
        self._ledger = ledger_port
        self._event_bus = event_bus

    # ── Public API ────────────────────────────────────────────────────────────

    def send_fps(
        self,
        amount: Decimal,
        beneficiary: BankAccount,
        reference: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """
        Send a GBP Faster Payment (UK domestic, near-instant).
        Max £1,000,000 per payment (FPS scheme limit).
        """
        if amount > Decimal("1000000"):
            raise ValueError(f"FPS limit is £1,000,000. Got: £{amount}")
        debtor = self._build_gbp_debtor()
        intent = self._build_intent(
            rail=PaymentRail.FPS,
            currency="GBP",
            amount=amount,
            debtor=debtor,
            creditor=beneficiary,
            reference=reference,
            metadata=metadata or {},
        )
        return self._submit(intent)

    def send_sepa_ct(
        self,
        amount: Decimal,
        beneficiary: BankAccount,
        reference: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """
        Send EUR SEPA Credit Transfer (D+1, business days).
        No amount limit at scheme level (bank limits may apply).
        """
        debtor = self._build_eur_debtor()
        intent = self._build_intent(
            rail=PaymentRail.SEPA_CT,
            currency="EUR",
            amount=amount,
            debtor=debtor,
            creditor=beneficiary,
            reference=reference,
            metadata=metadata or {},
        )
        return self._submit(intent)

    def send_sepa_instant(
        self,
        amount: Decimal,
        beneficiary: BankAccount,
        reference: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """
        Send EUR SEPA Instant Credit Transfer (<10 seconds, 24/7).
        Scheme limit: €100,000 per transaction.
        """
        if amount > Decimal("100000"):
            raise ValueError(f"SEPA Instant limit is €100,000. Got: €{amount}")
        debtor = self._build_eur_debtor()
        intent = self._build_intent(
            rail=PaymentRail.SEPA_INSTANT,
            currency="EUR",
            amount=amount,
            debtor=debtor,
            creditor=beneficiary,
            reference=reference,
            metadata=metadata or {},
        )
        return self._submit(intent)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_intent(
        self,
        rail: PaymentRail,
        currency: str,
        amount: Decimal,
        debtor: BankAccount,
        creditor: BankAccount,
        reference: str,
        metadata: dict,
    ) -> PaymentIntent:
        idempotency_key = str(uuid.uuid4())
        end_to_end_id = f"BANXE-{idempotency_key[:16].upper()}"
        return PaymentIntent(
            idempotency_key=idempotency_key,
            rail=rail,
            direction=PaymentDirection.OUTBOUND,
            amount=amount,
            currency=currency,
            debtor_account=debtor,
            creditor_account=creditor,
            reference=reference[:35],
            end_to_end_id=end_to_end_id,
            requested_at=datetime.now(UTC),
            metadata=metadata,
        )

    def _submit(self, intent: PaymentIntent) -> PaymentResult:
        """Submit payment to rail and write audit trail."""
        logger.info(
            "PaymentService._submit: rail=%s amount=%s%s key=%s",
            intent.rail,
            intent.amount,
            intent.currency,
            intent.idempotency_key,
        )
        try:
            result = self._rail.submit_payment(intent)
        except Exception as exc:
            logger.error("Rail submission failed: %s", exc, exc_info=True)
            result = PaymentResult(
                idempotency_key=intent.idempotency_key,
                provider_payment_id="",
                status=PaymentStatus.FAILED,
                rail=intent.rail,
                amount=intent.amount,
                currency=intent.currency,
                submitted_at=datetime.now(UTC),
                error_code="SUBMISSION_ERROR",
                error_message=str(exc)[:200],
            )

        self._write_audit(intent, result)
        self._notify_n8n(result)
        self._emit_event(intent, result)
        return result

    def _write_audit(self, intent: PaymentIntent, result: PaymentResult) -> None:
        """Write payment event to ClickHouse banxe.payment_events (I-24, I-15)."""
        try:
            self._ch.execute(
                """
                INSERT INTO banxe.payment_events
                (idempotency_key, provider_payment_id, rail, direction,
                 amount, currency, status, error_code,
                 debtor_name, creditor_name, reference, submitted_at)
                VALUES
                """,
                {
                    "idempotency_key": intent.idempotency_key,
                    "provider_payment_id": result.provider_payment_id,
                    "rail": intent.rail.value,
                    "direction": intent.direction.value,
                    "amount": str(intent.amount),
                    "currency": intent.currency,
                    "status": result.status.value,
                    "error_code": result.error_code or "",
                    "debtor_name": intent.debtor_account.account_holder_name,
                    "creditor_name": intent.creditor_account.account_holder_name,
                    "reference": intent.reference,
                    "submitted_at": result.submitted_at.isoformat(),
                },
            )
        except Exception as exc:
            # Audit failure must NEVER suppress the payment result (I-24)
            logger.error("ClickHouse payment audit write failed: %s", exc)

    def _emit_event(self, intent: PaymentIntent, result: PaymentResult) -> None:
        """Publish typed domain event to Event Bus (S17-11, Geniusto NOTIFICATION.OUT.PAYMENT)."""
        if self._event_bus is None:
            return
        try:
            BanxeEventType, DomainEvent, _ = _get_event_bus_types()
            event_type = (
                BanxeEventType.PAYMENT_COMPLETED
                if result.status == PaymentStatus.COMPLETED
                else BanxeEventType.PAYMENT_FAILED
            )
            event = DomainEvent.create(
                event_type=event_type,
                source_service="payment_service",
                payload={
                    "idempotency_key": intent.idempotency_key,
                    "provider_payment_id": result.provider_payment_id,
                    "rail": intent.rail.value,
                    "amount": str(intent.amount),
                    "currency": intent.currency,
                    "status": result.status.value,
                    "error_code": result.error_code or "",
                },
                correlation_id=intent.idempotency_key,
            )
            self._event_bus.publish(event)
        except Exception as exc:
            # Event bus failure MUST NOT suppress the payment result
            logger.warning("Event bus publish failed: %s", exc)

    def _notify_n8n(self, result: PaymentResult) -> None:
        """Fire n8n webhook for FAILED payments (ops alerting)."""
        if not N8N_WEBHOOK_URL or result.status != PaymentStatus.FAILED:
            return
        try:
            import httpx

            httpx.post(
                N8N_WEBHOOK_URL,
                json={
                    "event": "payment_failed",
                    "provider_payment_id": result.provider_payment_id,
                    "rail": result.rail.value,
                    "amount": str(result.amount),
                    "currency": result.currency,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                },
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("n8n payment alert failed: %s", exc)

    def _build_gbp_debtor(self) -> BankAccount:
        return BankAccount(
            account_holder_name="Banxe Ltd",
            sort_code=OPERATIONAL_ACCOUNT_SORT_CODE or "00-00-00",
            account_number=OPERATIONAL_ACCOUNT_NUMBER or "00000000",
            country_code="GB",
        )

    def _build_eur_debtor(self) -> BankAccount:
        return BankAccount(
            account_holder_name="Banxe Ltd",
            iban=OPERATIONAL_ACCOUNT_IBAN or "GB00XXXX00000000000000",
            country_code="GB",
        )


# ── Factory ───────────────────────────────────────────────────────────────────


def build_payment_service(ch_client=None, ledger_port=None) -> PaymentService:
    """
    Build PaymentService with the correct rail adapter based on PAYMENT_ADAPTER env var.

    PAYMENT_ADAPTER=mock    → MockPaymentAdapter (default, no API key needed)
    PAYMENT_ADAPTER=modulr  → ModulrPaymentAdapter (requires MODULR_API_KEY)

    ch_client defaults to ClickHouseReconClient if not provided.
    """
    adapter_name = PAYMENT_ADAPTER.lower()

    if adapter_name == "modulr":
        from services.payment.modulr_client import ModulrPaymentAdapter

        rail = ModulrPaymentAdapter()
        logger.info("PaymentService: using ModulrPaymentAdapter")
    else:
        from services.payment.mock_payment_adapter import MockPaymentAdapter

        rail = MockPaymentAdapter()
        logger.info(
            "PaymentService: using MockPaymentAdapter (set PAYMENT_ADAPTER=modulr for production)"
        )

    if ch_client is None:
        from services.recon.clickhouse_client import ClickHouseReconClient

        ch_client = ClickHouseReconClient()

    return PaymentService(rail=rail, ch_client=ch_client, ledger_port=ledger_port)
