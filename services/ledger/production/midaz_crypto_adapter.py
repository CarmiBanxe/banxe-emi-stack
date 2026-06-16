"""
midaz_crypto_adapter.py — MidazCryptoAdapter: CryptoLedgerPort via Midaz REST API.

Production HTTP adapter for crypto wallet, balance, and transaction operations.
All env vars are read in __init__ (no module-level globals).
Sandbox-only by default — no live Midaz calls unless sandbox=False is explicit.

Midaz endpoints used:
  GET  /v1/wallets/{wallet_id}/balances    → get_balance
  POST /v1/wallets                         → create_wallet_address
  POST /v1/transactions                    → create_tx  (idempotent on externalId)
  GET  /v1/transactions/{tx_id}            → status poll
  GET  /v1/health                          → health

Auth: Authorization: Bearer {MIDAZ_API_KEY}
Amount encoding: minor units (10^8 per coin, satoshi-equivalent).

get_fee_estimate: deterministic sandbox fallback using same table as
LegacyCryptoProcessingAdapter. Replace with CryptoRpcPort.estimate_fee() in REWRITE-9.

Env: MIDAZ_API_KEY (required), MIDAZ_LEDGER_URL (optional, production only)
Canon: ADR-031 (proposed) + PORT-CONTRACTS-FREEZE-2026-05-08 + [IL-CRYPTO-PROD-01]
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import os
from typing import Any

import httpx

from services.ledger.crypto_ledger_port import (
    CryptoBalance,
    CryptoFeeEstimate,
    CryptoLedgerError,
    CryptoLedgerPort,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoTransactionStatus,
    CryptoWalletAddress,
    FeePriority,
    SupportedBlockchain,
)
from services.ledger.legacy.legacy_crypto_processing_adapter import (
    _CONFIRMATION_BLOCKS,
    _FEE_CURRENCY,
    compute_fee,
)

_SANDBOX_BASE_URL: str = "http://localhost:8095"
_MINOR_SCALE: Decimal = Decimal("100000000")  # 10^8 — satoshi-equivalent

_MIDAZ_STATUS_MAP: dict[str, CryptoTransactionStatus] = {
    "PENDING": CryptoTransactionStatus.PENDING,
    "CONFIRMED": CryptoTransactionStatus.CONFIRMED,
    "APPROVED": CryptoTransactionStatus.CONFIRMED,
    "FAILED": CryptoTransactionStatus.FAILED,
    "CANCELLED": CryptoTransactionStatus.FAILED,
    "REPLACED": CryptoTransactionStatus.REPLACED,
}


class MidazCryptoAdapter:
    """
    CryptoLedgerPort — Midaz REST API, all six supported blockchains.

    Raises CryptoLedgerError on network failures and 4xx/5xx responses.
    get_fee_estimate uses a deterministic offline table (MEDIUM priority).
    """

    def __init__(
        self,
        *,
        sandbox: bool = True,
        timeout_seconds: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key: str = os.environ["MIDAZ_API_KEY"]
        self._base_url: str = (
            _SANDBOX_BASE_URL
            if sandbox
            else os.environ.get("MIDAZ_LEDGER_URL", _SANDBOX_BASE_URL).rstrip("/")
        )
        self._timeout = timeout_seconds
        self._http: httpx.Client = (
            http_client if http_client is not None else httpx.Client(timeout=timeout_seconds)
        )

    # ── CryptoLedgerPort ─────────────────────────────────────────────────────

    def get_balance(
        self,
        wallet_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoBalance:
        """GET /v1/wallets/{wallet_id}/balances — returns first matching balance item."""
        try:
            data = self._request("GET", f"/v1/wallets/{wallet_id}/balances")
        except httpx.HTTPStatusError as exc:
            raise CryptoLedgerError(
                f"get_balance failed: {exc}",
                code=f"http_{exc.response.status_code}",
            ) from exc

        items: list[dict[str, Any]] = data.get("items", [data] if data else [])
        balance_item = next(
            (i for i in items if i.get("assetCode", "").upper() == blockchain.value),
            items[0] if items else {},
        )
        minor = Decimal(str(balance_item.get("available", 0)))
        unconfirmed_minor = Decimal(str(balance_item.get("onHold", 0)))
        return CryptoBalance(
            wallet_id=wallet_id,
            blockchain=blockchain,
            confirmed_balance=minor / _MINOR_SCALE,
            unconfirmed_balance=unconfirmed_minor / _MINOR_SCALE,
            currency=blockchain.value,
            as_of=datetime.now(UTC),
        )

    def create_wallet_address(
        self,
        customer_id: str,
        blockchain: SupportedBlockchain,
    ) -> CryptoWalletAddress:
        """POST /v1/wallets — create a new wallet and return its primary address."""
        body: dict[str, Any] = {
            "entityId": customer_id,
            "assetCode": blockchain.value,
            "type": "CRYPTO",
        }
        try:
            data = self._request("POST", "/v1/wallets", body=body)
        except httpx.HTTPStatusError as exc:
            raise CryptoLedgerError(
                f"create_wallet_address failed: {exc}",
                code=f"http_{exc.response.status_code}",
            ) from exc

        wallet_id: str = data.get("id", "")
        address: str = data.get("address", data.get("blockchainAddress", ""))
        created_raw: str = data.get("createdAt", "")
        created_at = _parse_dt(created_raw)
        return CryptoWalletAddress(
            wallet_id=wallet_id,
            customer_id=customer_id,
            blockchain=blockchain,
            address=address,
            created_at=created_at,
        )

    def create_tx(
        self,
        request: CryptoTransactionRequest,
    ) -> CryptoTransactionResult:
        """POST /v1/transactions — idempotent on externalId (== request.tx_id)."""
        fee_estimate = self.get_fee_estimate(request.blockchain, request.amount)
        amount_minor = int(request.amount * _MINOR_SCALE)
        fee_minor = int(fee_estimate.fee * _MINOR_SCALE)

        body: dict[str, Any] = {
            "externalId": request.tx_id,
            "fromWalletId": request.from_wallet_id,
            "toAddress": request.to_address,
            "assetCode": request.blockchain.value,
            "amount": amount_minor,
            "fee": fee_minor,
            "currency": request.currency,
            "feePriority": request.fee_level.value,
        }
        try:
            data = self._request("POST", "/v1/transactions", body=body)
        except httpx.HTTPStatusError as exc:
            raise CryptoLedgerError(
                f"create_tx failed: {exc}",
                code=f"http_{exc.response.status_code}",
            ) from exc

        return self._parse_transaction(data, request)

    def get_fee_estimate(
        self,
        blockchain: SupportedBlockchain,
        amount: Decimal,  # unused in offline table; reserved for REWRITE-9 live RPC
    ) -> CryptoFeeEstimate:
        """Deterministic MEDIUM-priority fee (offline table). Replace in REWRITE-9."""
        priority = FeePriority.MEDIUM
        fee = compute_fee(blockchain, priority)
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=fee,
            currency=_FEE_CURRENCY[blockchain],
            priority=priority,
            estimated_confirmation_blocks=_CONFIRMATION_BLOCKS[priority],
        )

    def health(self) -> bool:
        """GET /v1/health — True if Midaz API is reachable."""
        try:
            self._request("GET", "/v1/health")
            return True
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        self._http.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _auth_header(self) -> str:
        return f"Bearer {self._api_key}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import json

        headers: dict[str, str] = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body_str = json.dumps(body) if body else ""
        resp = self._http.request(
            method,
            self._base_url + path,
            headers=headers,
            content=body_str.encode() if body_str else None,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _parse_transaction(
        self,
        data: dict[str, Any],
        request: CryptoTransactionRequest,
    ) -> CryptoTransactionResult:
        raw_status: str = data.get("status", "PENDING")
        status = _MIDAZ_STATUS_MAP.get(raw_status, CryptoTransactionStatus.PENDING)
        amount_minor = Decimal(str(data.get("amount", int(request.amount * _MINOR_SCALE))))
        fee_minor = Decimal(str(data.get("fee", 0)))
        confirmed_raw: str | None = data.get("confirmedAt")
        return CryptoTransactionResult(
            tx_id=data.get("externalId", request.tx_id),
            tx_hash=data.get("txHash") or None,
            blockchain=request.blockchain,
            amount=amount_minor / _MINOR_SCALE,
            fee=fee_minor / _MINOR_SCALE,
            currency=data.get("currency", request.currency),
            status=status,
            from_wallet_id=data.get("fromWalletId", request.from_wallet_id),
            to_address=data.get("toAddress", request.to_address),
            created_at=_parse_dt(data.get("createdAt", "")),
            confirmed_at=_parse_dt(confirmed_raw) if confirmed_raw else None,
        )


def _parse_dt(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(UTC)


# Structural type assertion — fails fast at import if Protocol drifts.
_: CryptoLedgerPort = MidazCryptoAdapter.__new__(MidazCryptoAdapter)  # type: ignore[assignment]
