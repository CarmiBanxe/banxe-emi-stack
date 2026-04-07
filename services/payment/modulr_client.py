"""
modulr_client.py — Modulr Finance Payment Rail Adapter
Block C-fps + C-sepa, IL-014
FCA EMI | banxe-emi-stack

MODULR FINANCE
--------------
Regulatoy status: FCA EMI (FRN 900699), DNB Netherlands
Payment schemes: UK FPS (direct, RTGS), Bacs (direct), SEPA CT, SEPA Instant
API docs: https://modulr.readme.io/docs/intro
Sandbox: https://modulr.readme.io/docs/sandbox

HOW MODULR WORKS
----------------
1. Accounts are pre-created in Modulr (sort code + account number for GBP,
   IBAN for EUR). Banxe holds Modulr accounts for operational + client_funds.
2. Payments are submitted via POST /accounts/{id}/payments
3. Modulr returns a paymentId immediately (PROCESSING)
4. Status updates arrive via webhooks (payment.completed, payment.failed)
5. GBP FPS: near-instant (seconds). SEPA Instant: <10s. SEPA CT: D+1.

ENV VARS (in .env):
    MODULR_API_URL       = https://api.modulrfinance.com  (prod)
                           https://api-sandbox.modulrfinance.com  (sandbox)
    MODULR_API_KEY       = your-api-key (from Modulr portal)
    MODULR_API_SECRET    = your-api-secret
    MODULR_GBP_ACCOUNT_ID = acc-xxxxxxxx  (Modulr account ID for GBP payments)
    MODULR_EUR_ACCOUNT_ID = acc-xxxxxxxx  (Modulr account ID for EUR SEPA)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
    PaymentStatusUpdate,
)

logger = logging.getLogger(__name__)

MODULR_API_URL = os.environ.get(
    "MODULR_API_URL", "https://api-sandbox.modulrfinance.com"
)
MODULR_API_KEY = os.environ.get("MODULR_API_KEY", "")
MODULR_API_SECRET = os.environ.get("MODULR_API_SECRET", "")
MODULR_GBP_ACCOUNT_ID = os.environ.get("MODULR_GBP_ACCOUNT_ID", "")
MODULR_EUR_ACCOUNT_ID = os.environ.get("MODULR_EUR_ACCOUNT_ID", "")

_TIMEOUT = 30.0


class ModulrPaymentAdapter:
    """
    Production adapter for Modulr Finance payment API.

    Implements PaymentRailPort for:
      - GBP UK Faster Payments (PaymentRail.FPS)
      - EUR SEPA Credit Transfer (PaymentRail.SEPA_CT)
      - EUR SEPA Instant (PaymentRail.SEPA_INSTANT)

    Prerequisites:
      1. Modulr sandbox or production API key (from modulrfinance.com/developer)
      2. MODULR_GBP_ACCOUNT_ID and MODULR_EUR_ACCOUNT_ID configured
      3. Webhook endpoint registered in Modulr portal (see webhook_handler.py)
    """

    def __init__(
        self,
        api_url: str = MODULR_API_URL,
        api_key: str = MODULR_API_KEY,
        api_secret: str = MODULR_API_SECRET,
        gbp_account_id: str = MODULR_GBP_ACCOUNT_ID,
        eur_account_id: str = MODULR_EUR_ACCOUNT_ID,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._base = api_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._gbp_account_id = gbp_account_id
        self._eur_account_id = eur_account_id
        self._timeout = timeout

        if not api_key:
            logger.warning(
                "ModulrPaymentAdapter: MODULR_API_KEY not set. "
                "Use MockPaymentAdapter for testing without a key."
            )

    # ── PaymentRailPort interface ─────────────────────────────────────────────

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """
        Submit payment to Modulr API.
        Returns PaymentResult immediately (status = PROCESSING).
        Final status arrives via webhook.
        """
        source_account_id = self._resolve_source_account(intent)
        payload = self._build_payment_payload(intent)

        logger.info(
            "ModulrAdapter.submit_payment: rail=%s amount=%s%s idempotency_key=%s",
            intent.rail, intent.amount, intent.currency, intent.idempotency_key,
        )

        try:
            resp = self._post(
                f"/accounts/{source_account_id}/payments",
                payload,
                idempotency_key=intent.idempotency_key,
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Modulr API error: %s — %s", exc.response.status_code, exc.response.text)
            return PaymentResult(
                idempotency_key=intent.idempotency_key,
                provider_payment_id="",
                status=PaymentStatus.FAILED,
                rail=intent.rail,
                amount=intent.amount,
                currency=intent.currency,
                submitted_at=datetime.now(timezone.utc),
                error_code=str(exc.response.status_code),
                error_message=exc.response.text[:200],
            )

        data = resp.json()
        return PaymentResult(
            idempotency_key=intent.idempotency_key,
            provider_payment_id=data.get("id", ""),
            status=PaymentStatus.PROCESSING,
            rail=intent.rail,
            amount=intent.amount,
            currency=intent.currency,
            submitted_at=datetime.now(timezone.utc),
        )

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        """Fetch current payment status from Modulr."""
        resp = self._get(f"/payments/{provider_payment_id}")
        data = resp.json()
        return self._parse_payment_response(data)

    def health_check(self) -> bool:
        """Ping Modulr API health endpoint."""
        try:
            resp = self._get("/ping")
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Modulr health check failed: %s", exc)
            return False

    # ── Webhook signature verification ────────────────────────────────────────

    def verify_webhook_signature(self, payload_bytes: bytes, signature_header: str) -> bool:
        """
        Verify HMAC-SHA256 signature on incoming Modulr webhook.
        Modulr signs webhooks with the API secret.
        Must be called BEFORE processing any webhook payload.
        """
        if not self._api_secret:
            logger.warning("MODULR_API_SECRET not set — webhook signature NOT verified")
            return False
        expected = hmac.new(
            self._api_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    @staticmethod
    def parse_webhook_event(payload: dict) -> PaymentStatusUpdate:
        """Parse Modulr webhook payload → PaymentStatusUpdate."""
        status_map = {
            "PROCESSED": PaymentStatus.COMPLETED,
            "PROCESSING": PaymentStatus.PROCESSING,
            "SUBMITTED": PaymentStatus.PENDING,
            "FAILED": PaymentStatus.FAILED,
            "RETURNED": PaymentStatus.RETURNED,
        }
        raw_status = payload.get("status", "")
        amount_str = str(payload.get("amount", "0"))

        return PaymentStatusUpdate(
            provider_payment_id=payload.get("id", ""),
            idempotency_key=payload.get("externalReference"),
            new_status=status_map.get(raw_status, PaymentStatus.PENDING),
            previous_status=None,
            rail=PaymentRail.FPS,   # Modulr webhooks don't always include rail; infer from currency
            amount=Decimal(amount_str) / Decimal("100"),  # Modulr sends pence
            currency=payload.get("currency", "GBP"),
            occurred_at=datetime.now(timezone.utc),
            raw_payload=payload,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_source_account(self, intent: PaymentIntent) -> str:
        if intent.currency == "GBP":
            if not self._gbp_account_id:
                raise ValueError("MODULR_GBP_ACCOUNT_ID not configured")
            return self._gbp_account_id
        if intent.currency == "EUR":
            if not self._eur_account_id:
                raise ValueError("MODULR_EUR_ACCOUNT_ID not configured")
            return self._eur_account_id
        raise ValueError(f"Unsupported currency: {intent.currency}")

    def _build_payment_payload(self, intent: PaymentIntent) -> dict:
        """Build Modulr API request body for payment submission."""
        payload: dict = {
            "currency": intent.currency,
            # Modulr expects pence (minor units) as integer
            "amount": int(intent.amount * 100),
            "reference": intent.reference[:18],    # FPS: max 18 chars
            "externalReference": intent.idempotency_key,
            "endToEndReference": intent.end_to_end_id[:35],
        }

        # Destination account
        dest = intent.creditor_account
        if intent.rail == PaymentRail.FPS:
            # UK FPS: sort code + account number
            payload["destination"] = {
                "type": "SCAN",
                "name": dest.account_holder_name[:50],
                "sortCode": (dest.sort_code or "").replace("-", ""),
                "accountNumber": dest.account_number or "",
            }
        elif intent.rail in (PaymentRail.SEPA_CT, PaymentRail.SEPA_INSTANT):
            # SEPA: IBAN + BIC
            payload["destination"] = {
                "type": "IBAN",
                "name": dest.account_holder_name[:70],
                "iban": dest.iban or "",
                "bic": dest.bic or "",
            }
            if intent.rail == PaymentRail.SEPA_INSTANT:
                payload["type"] = "SEPA_INSTANT"

        return payload

    def _build_headers(self, idempotency_key: Optional[str] = None) -> dict:
        headers = {
            "Authorization": f"Basic {self._api_key}:{self._api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["x-mod-nonce"] = idempotency_key
        return headers

    def _get(self, path: str) -> httpx.Response:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(
                f"{self._base}{path}",
                headers=self._build_headers(),
            )
            resp.raise_for_status()
            return resp

    def _post(self, path: str, payload: dict, idempotency_key: Optional[str] = None) -> httpx.Response:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base}{path}",
                json=payload,
                headers=self._build_headers(idempotency_key),
            )
            resp.raise_for_status()
            return resp

    def _parse_payment_response(self, data: dict) -> PaymentResult:
        status_map = {
            "PROCESSED": PaymentStatus.COMPLETED,
            "PROCESSING": PaymentStatus.PROCESSING,
            "SUBMITTED": PaymentStatus.PENDING,
            "FAILED": PaymentStatus.FAILED,
        }
        raw_status = data.get("status", "PROCESSING")
        amount_pence = data.get("amount", 0)
        return PaymentResult(
            idempotency_key=data.get("externalReference", ""),
            provider_payment_id=data.get("id", ""),
            status=status_map.get(raw_status, PaymentStatus.PROCESSING),
            rail=PaymentRail.FPS,
            amount=Decimal(str(amount_pence)) / Decimal("100"),
            currency=data.get("currency", "GBP"),
            submitted_at=datetime.now(timezone.utc),
        )
