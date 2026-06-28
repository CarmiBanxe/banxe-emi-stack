"""
modulr_sepa_adapter.py — ModulrSepaAdapter: PaymentRailPort via Modulr Finance REST API.

Production HTTP adapter for SEPA CT + SEPA Instant payments.
All env vars are read in __init__ (no module-level globals).
Sandbox-only by default — no live API calls unless sandbox=False is explicit.

Modulr endpoints used:
  POST /accounts/{eur_account_id}/payments   → submit_payment
  GET  /payments/{payment_id}                → get_payment_status
  GET  /ping                                 → health

Auth: Authorization: Basic {api_key}:{api_secret}
Idempotency: x-mod-nonce: {idempotency_key} header

Env: MODULR_API_KEY, MODULR_API_SECRET, MODULR_EUR_ACCOUNT_ID, MODULR_API_URL
Canon: ADR-025 §15-16 + PORT-CONTRACTS-FREEZE-2026-05-08 + [IL-SEPA-PROD-01]
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
import os
from typing import Any

import httpx

from services.payment.payment_port import (
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)
from services.payment.sepa_validation import (
    SCT_INSTANT_MAX_EUR as _SCT_INST_MAX_EUR,
)
from services.payment.sepa_validation import (
    validate_bic as _validate_bic,
)
from services.payment.sepa_validation import (
    validate_iban as _validate_iban,
)

_SEPA_RAILS: frozenset[PaymentRail] = frozenset({PaymentRail.SEPA_CT, PaymentRail.SEPA_INSTANT})
_SANDBOX_BASE_URL: str = "https://api-sandbox.modulrfinance.com"
_PROD_BASE_URL: str = "https://api.modulrfinance.com"

_MODULR_STATUS_MAP: dict[str, PaymentStatus] = {
    "PROCESSED": PaymentStatus.COMPLETED,
    "PROCESSING": PaymentStatus.PROCESSING,
    "SUBMITTED": PaymentStatus.PENDING,
    "FAILED": PaymentStatus.FAILED,
    "RETURNED": PaymentStatus.RETURNED,
}


class ModulrSepaError(Exception):
    def __init__(self, message: str, *, code: str = "modulr_error") -> None:
        super().__init__(message)
        self.code = code


class ModulrSepaAdapter:
    """
    PaymentRailPort — Modulr Finance REST API, SEPA CT + SEPA Instant only.

    SEPA validation: IBAN mod-97, BIC SWIFT regex, SCT_INST ≤ €100k.
    4xx/5xx responses are fail-safe: returns PaymentResult(status=FAILED).
    """

    def __init__(
        self,
        *,
        sandbox: bool = True,
        timeout_seconds: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key: str = os.environ["MODULR_API_KEY"]
        self._api_secret: str = os.environ.get("MODULR_API_SECRET", "")
        self._eur_account_id: str = os.environ["MODULR_EUR_ACCOUNT_ID"]
        self._base_url: str = (
            _SANDBOX_BASE_URL
            if sandbox
            else os.environ.get("MODULR_API_URL", _PROD_BASE_URL).rstrip("/")
        )
        self._timeout = timeout_seconds
        self._http: httpx.Client = (
            http_client if http_client is not None else httpx.Client(timeout=timeout_seconds)
        )

    # ── PaymentRailPort ───────────────────────────────────────────────────────

    def submit_payment(self, intent: PaymentIntent) -> PaymentResult:
        """POST /accounts/{eur_account_id}/payments — SEPA CT / SEPA Instant."""
        if intent.rail not in _SEPA_RAILS:
            return self._fail_result(
                intent,
                code="unsupported_rail",
                message=f"ModulrSepaAdapter only handles SEPA rails, got {intent.rail.value}",
            )

        creditor = intent.creditor_account
        iban = creditor.iban or ""
        bic = creditor.bic or ""

        if not _validate_iban(iban):
            return self._fail_result(intent, code="invalid_iban", message=f"Invalid IBAN: {iban!r}")
        if bic and not _validate_bic(bic):
            return self._fail_result(intent, code="invalid_bic", message=f"Invalid BIC: {bic!r}")

        if intent.rail == PaymentRail.SEPA_INSTANT and intent.amount > _SCT_INST_MAX_EUR:
            return self._fail_result(
                intent,
                code="amount_exceeds_sct_inst_max",
                message=f"SEPA Instant max €{_SCT_INST_MAX_EUR}, got €{intent.amount}",
            )

        amount_minor = int(intent.amount * 100)

        body: dict[str, Any] = {
            "type": "SEPA_INSTANT" if intent.rail == PaymentRail.SEPA_INSTANT else "SEPA_CT",
            "amount": amount_minor,
            "currency": intent.currency,
            "destination": {
                "type": "IBAN",
                "iban": iban.replace(" ", "").upper(),
                "name": creditor.account_holder_name[:70],
            },
            "reference": intent.reference[:140],
            "externalReference": intent.idempotency_key,
            "endToEndReference": intent.end_to_end_id[:35],
        }
        if bic:
            body["destination"]["bic"] = bic.upper()

        try:
            data = self._request(
                "POST",
                f"/accounts/{self._eur_account_id}/payments",
                body=body,
                idempotency_key=intent.idempotency_key,
            )
        except httpx.HTTPStatusError as exc:
            return self._fail_result(
                intent,
                code=f"http_{exc.response.status_code}",
                message=str(exc),
            )

        provider_id: str = data.get("id", "")
        raw_status: str = data.get("status", "SUBMITTED")
        status = _MODULR_STATUS_MAP.get(raw_status, PaymentStatus.PENDING)
        return PaymentResult(
            idempotency_key=intent.idempotency_key,
            provider_payment_id=provider_id,
            status=status,
            rail=intent.rail,
            amount=intent.amount,
            currency=intent.currency,
            submitted_at=datetime.now(UTC),
        )

    def get_payment_status(self, provider_payment_id: str) -> PaymentResult:
        """GET /payments/{payment_id} — returns current Modulr status."""
        try:
            data = self._request("GET", f"/payments/{provider_payment_id}")
        except httpx.HTTPStatusError as exc:
            return PaymentResult(
                idempotency_key="",
                provider_payment_id=provider_payment_id,
                status=PaymentStatus.FAILED,
                rail=PaymentRail.SEPA_CT,
                amount=Decimal("0"),
                currency="EUR",
                submitted_at=datetime.now(UTC),
                error_code=f"http_{exc.response.status_code}",
                error_message=str(exc),
            )

        raw_status: str = data.get("status", "FAILED")
        status = _MODULR_STATUS_MAP.get(raw_status, PaymentStatus.FAILED)
        amount_minor: int = data.get("amount", 0)
        amount = Decimal(amount_minor) / 100
        rail_raw: str = data.get("type", "SEPA_CT")
        rail = PaymentRail.SEPA_INSTANT if rail_raw == "SEPA_INSTANT" else PaymentRail.SEPA_CT
        ext_ref: str = data.get("externalReference", "")
        return PaymentResult(
            idempotency_key=ext_ref,
            provider_payment_id=provider_payment_id,
            status=status,
            rail=rail,
            amount=amount,
            currency=data.get("currency", "EUR"),
            submitted_at=datetime.now(UTC),
        )

    def health(self) -> bool:
        """GET /ping — True if Modulr API is reachable."""
        try:
            self._request("GET", "/ping")
            return True
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        self._http.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _auth_header(self) -> str:
        credentials = f"{self._api_key}:{self._api_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        import json

        headers: dict[str, str] = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["x-mod-nonce"] = idempotency_key

        body_str = json.dumps(body) if body else ""
        resp = self._http.request(
            method,
            self._base_url + path,
            headers=headers,
            content=body_str.encode() if body_str else None,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _fail_result(self, intent: PaymentIntent, *, code: str, message: str) -> PaymentResult:
        return PaymentResult(
            idempotency_key=intent.idempotency_key,
            provider_payment_id="",
            status=PaymentStatus.FAILED,
            rail=intent.rail,
            amount=intent.amount,
            currency=intent.currency,
            submitted_at=datetime.now(UTC),
            error_code=code,
            error_message=message,
        )
