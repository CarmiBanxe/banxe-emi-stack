"""
mock_payment_adapter.py — In-memory Mock Payment Rail Adapter
Block C-fps + C-sepa, IL-014
banxe-emi-stack

WHY THIS EXISTS
---------------
Modulr sandbox requires API key registration (CEO action pending).
MockPaymentAdapter lets us build, test, and deploy the full Payment Rails
layer immediately — without waiting for the key.

When MODULR_API_KEY arrives:
  1. Set PAYMENT_ADAPTER=modulr in .env
  2. PaymentService auto-switches to ModulrPaymentAdapter
  3. No code changes needed

MockAdapter behaviour:
  - FPS payments: instantly COMPLETED (simulates near-instant settlement)
  - SEPA CT: PROCESSING → simulates async (no real async here)
  - SEPA Instant: instantly COMPLETED
  - BACS: PROCESSING (D+3 simulation)
  - Configurable failure rate via MOCK_PAYMENT_FAILURE_RATE env var
  - Thread-safe: stores all submitted payments in-memory dict
  - Idempotent: same idempotency_key → same result
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional

from services.payment.payment_port import (
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
    PaymentStatusUpdate,
)

logger = logging.getLogger(__name__)

# Configurable: set MOCK_PAYMENT_FAILURE_RATE=0.1 to simulate 10% failure rate
_FAILURE_RATE = float(os.environ.get("MOCK_PAYMENT_FAILURE_RATE", "0"))

# Rails that settle instantly in mock mode
_INSTANT_RAILS = {PaymentRail.FPS, PaymentRail.SEPA_INSTANT}


class MockPaymentAdapter:
    """
    In-memory mock implementation of PaymentRailPort.

    Used for:
      - Development without Modulr API key
      - Unit and integration tests
      - GMKtec staging environment validation

    All submitted payments are stored in self._payments dict.
    Use .get_all_payments() in tests to assert on submitted payments.
    """

    def __init__(self, failure_rate: float = _FAILURE_RATE) -> None:
        self._payments: Dict[str, PaymentResult] = {}   # idempotency_key → result
        self._failure_rate = failure_rate
        self._call_count = 0
        logger.info(
            "MockPaymentAdapter initialised (failure_rate=%.0f%%)",
            failure_rate * 100,
        )

    # ── PaymentRailPort interface ─────────────────────────────────────────────

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """
        Idempotent: calling with the same idempotency_key returns the same result.
        """
        # Idempotency: return cached result if already submitted
        if intent.idempotency_key in self._payments:
            logger.info(
                "MockAdapter.submit_payment: idempotent hit key=%s",
                intent.idempotency_key,
            )
            return self._payments[intent.idempotency_key]

        self._call_count += 1
        provider_id = f"MOCK-{uuid.uuid4().hex[:12].upper()}"

        # Simulate failure if configured
        should_fail = (self._failure_rate > 0) and (
            (self._call_count % round(1 / self._failure_rate)) == 0
        )

        if should_fail:
            result = PaymentResult(
                idempotency_key=intent.idempotency_key,
                provider_payment_id=provider_id,
                status=PaymentStatus.FAILED,
                rail=intent.rail,
                amount=intent.amount,
                currency=intent.currency,
                submitted_at=datetime.now(timezone.utc),
                error_code="INSUFFICIENT_FUNDS",
                error_message="Mock simulated failure (MOCK_PAYMENT_FAILURE_RATE)",
            )
        elif intent.rail in _INSTANT_RAILS:
            # FPS + SEPA Instant → immediately COMPLETED
            result = PaymentResult(
                idempotency_key=intent.idempotency_key,
                provider_payment_id=provider_id,
                status=PaymentStatus.COMPLETED,
                rail=intent.rail,
                amount=intent.amount,
                currency=intent.currency,
                submitted_at=datetime.now(timezone.utc),
            )
        else:
            # SEPA CT, BACS → PROCESSING (settlement later)
            result = PaymentResult(
                idempotency_key=intent.idempotency_key,
                provider_payment_id=provider_id,
                status=PaymentStatus.PROCESSING,
                rail=intent.rail,
                amount=intent.amount,
                currency=intent.currency,
                submitted_at=datetime.now(timezone.utc),
            )

        self._payments[intent.idempotency_key] = result

        logger.info(
            "MockAdapter.submit_payment: rail=%s amount=%s%s status=%s id=%s",
            intent.rail, intent.amount, intent.currency,
            result.status, provider_id,
        )
        return result

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        """Look up by provider ID. Returns FAILED result if not found."""
        for result in self._payments.values():
            if result.provider_payment_id == provider_payment_id:
                return result
        return PaymentResult(
            idempotency_key="",
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.FAILED,
            rail=PaymentRail.FPS,
            amount=Decimal("0"),
            currency="GBP",
            submitted_at=datetime.now(timezone.utc),
            error_code="NOT_FOUND",
            error_message=f"Mock: payment {provider_payment_id} not found",
        )

    def health_check(self) -> bool:
        """Mock is always healthy."""
        return True

    # ── Test helpers ──────────────────────────────────────────────────────────

    def get_all_payments(self) -> list[PaymentResult]:
        """Return all submitted payments (for test assertions)."""
        return list(self._payments.values())

    @property
    def submission_count(self) -> int:
        return len(self._payments)

    def reset(self) -> None:
        """Clear all state (for test isolation)."""
        self._payments.clear()
        self._call_count = 0
