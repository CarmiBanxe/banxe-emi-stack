"""
midaz_adapter.py — Sync/Async LedgerPort adapter for Midaz CBS
Block D-recon, IL-013 Sprint 9 | S13-01
FCA CASS 7.15 | banxe-emi-stack

WHY THIS EXISTS
---------------
ReconciliationEngine uses a synchronous LedgerPortProtocol (Protocol class).
midaz_client.py exposes an async API (httpx.AsyncClient).

This adapter bridges the gap: it runs the async Midaz call inside
asyncio.run() so the engine stays I/O-framework-agnostic.

NEVER call Midaz HTTP directly from domain logic — always go via this adapter.
I-28 / CTX-06 AMBER.

Usage:
    from services.ledger.midaz_adapter import MidazLedgerAdapter
    adapter = MidazLedgerAdapter()
    balance = adapter.get_balance(org_id, ledger_id, account_id)
    tx = adapter.create_transaction(org_id, ledger_id, request)
    txns = adapter.list_transactions(org_id, ledger_id, account_id)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MIDAZ_BASE_URL = os.environ.get("MIDAZ_BASE_URL", "http://localhost:8095")
MIDAZ_TOKEN = os.environ.get("MIDAZ_TOKEN", "")
_TIMEOUT = 10.0


# ── Transaction models ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransactionRequest:
    """Request to create a transaction in Midaz GL.

    All amounts in GBP as Decimal — I-05: never float.
    """

    amount_gbp: Decimal  # positive value (direction set by debit/credit entries)
    description: str
    asset_code: str = "GBP"
    external_id: str = ""  # idempotency key / payment reference
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransactionRecord:
    """A transaction entry returned from Midaz GL."""

    transaction_id: str
    amount_gbp: Decimal
    asset_code: str
    description: str
    status: str  # APPROVED | PENDING | CANCELLED
    created_at: datetime
    external_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Main adapter ─────────────────────────────────────────────────────────────


class MidazLedgerAdapter:
    """
    Synchronous adapter implementing LedgerPortProtocol.

    Wraps async Midaz HTTP calls in asyncio.run() so that
    ReconciliationEngine (sync) can use Midaz (async) without
    coupling the domain layer to an event loop.

    Thread safety: one asyncio.run() per call — safe for cron / CLI use.
    Not intended for high-frequency async contexts (use midaz_client.py directly).

    Fallback: if MIDAZ_TOKEN is not set, all calls return safe defaults (0 / [])
    and log a warning. Swap in StubLedgerAdapter for tests.
    """

    def __init__(
        self,
        base_url: str = MIDAZ_BASE_URL,
        token: str = MIDAZ_TOKEN,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._timeout = timeout

    # ── LedgerPortProtocol interface ─────────────────────────────────────────

    def get_balance(self, org_id: str, ledger_id: str, account_id: str) -> Decimal:
        """
        Return GBP available balance for account_id as Decimal (never float).

        Returns Decimal("0") if:
          - Account not found in Midaz
          - Asset code is not GBP
          - Midaz is unreachable (logs error, returns 0 → PENDING in engine)

        FCA invariant: amounts MUST be Decimal, never float (I-05).
        """
        try:
            return asyncio.run(self._fetch_balance(org_id, ledger_id, account_id))
        except Exception as exc:
            logger.error(
                "MidazLedgerAdapter.get_balance failed: org=%s ledger=%s account=%s error=%s",
                org_id,
                ledger_id,
                account_id,
                exc,
            )
            return Decimal("0")

    def create_transaction(
        self,
        org_id: str,
        ledger_id: str,
        request: TransactionRequest,
    ) -> TransactionRecord | None:
        """
        POST /v1/organizations/{org_id}/ledgers/{ledger_id}/transactions

        Create a double-entry transaction in Midaz GL.
        Returns TransactionRecord on success, None on failure (logs error).

        I-05: amount_gbp MUST be Decimal — never float.
        I-24: all transaction events append-only in Midaz (no UPDATE/DELETE).
        """
        try:
            return asyncio.run(self._post_transaction(org_id, ledger_id, request))
        except Exception as exc:
            logger.error(
                "MidazLedgerAdapter.create_transaction failed: org=%s ledger=%s ext_id=%s error=%s",
                org_id,
                ledger_id,
                request.external_id,
                exc,
            )
            return None

    def list_transactions(
        self,
        org_id: str,
        ledger_id: str,
        account_id: str,
        limit: int = 50,
    ) -> list[TransactionRecord]:
        """
        GET /v1/organizations/{org_id}/ledgers/{ledger_id}/transactions?account_id={account_id}

        Returns transactions for account_id, newest first.
        Returns [] on failure.
        """
        try:
            return asyncio.run(self._fetch_transactions(org_id, ledger_id, account_id, limit))
        except Exception as exc:
            logger.error(
                "MidazLedgerAdapter.list_transactions failed: org=%s ledger=%s account=%s error=%s",
                org_id,
                ledger_id,
                account_id,
                exc,
            )
            return []

    # ── internal async implementations ───────────────────────────────────────

    async def _fetch_balance(self, org_id: str, ledger_id: str, account_id: str) -> Decimal:
        url = (
            f"{self._base_url}/v1/organizations/{org_id}"
            f"/ledgers/{ledger_id}/accounts/{account_id}/balances"
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

        return self._extract_gbp_balance(data, account_id)

    async def _post_transaction(
        self,
        org_id: str,
        ledger_id: str,
        request: TransactionRequest,
    ) -> TransactionRecord | None:
        url = f"{self._base_url}/v1/organizations/{org_id}/ledgers/{ledger_id}/transactions"
        # Midaz expects amount in minor units (pence)
        amount_pence = int(request.amount_gbp * 100)

        payload: dict[str, Any] = {
            "amount": amount_pence,
            "assetCode": request.asset_code,
            "description": request.description,
            "metadata": request.metadata,
        }
        if request.external_id:
            payload["externalId"] = request.external_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

        return self._parse_transaction(data)

    async def _fetch_transactions(
        self,
        org_id: str,
        ledger_id: str,
        account_id: str,
        limit: int,
    ) -> list[TransactionRecord]:
        url = f"{self._base_url}/v1/organizations/{org_id}/ledgers/{ledger_id}/transactions"
        params = {"accountId": account_id, "limit": limit, "orderBy": "createdAt:desc"}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("items", [data]) if isinstance(data, dict) else []
        return [self._parse_transaction(item) for item in items if item]

    # ── Parsers ───────────────────────────────────────────────────────────────

    def _extract_gbp_balance(self, data: dict, account_id: str) -> Decimal:
        """
        Parse Midaz balance response.

        Midaz v3.5.x returns:
          { "items": [ { "assetCode": "GBP", "available": 12500000 } ] }
        where `available` is in minor units (pence).
        """
        items = data.get("items", [data])
        for item in items:
            asset_code = item.get("assetCode", "").upper()
            if asset_code == "GBP":
                available_pence = item.get("available", 0)
                return Decimal(str(available_pence)) / Decimal("100")

        logger.warning(
            "MidazLedgerAdapter: no GBP balance found for account=%s. Response items: %s",
            account_id,
            [i.get("assetCode") for i in items],
        )
        return Decimal("0")

    def _parse_transaction(self, data: dict) -> TransactionRecord:
        """Parse Midaz transaction response → TransactionRecord (I-05: Decimal amounts)."""
        amount_pence = data.get("amount", 0)
        amount_gbp = Decimal(str(amount_pence)) / Decimal("100")

        created_raw = data.get("createdAt") or data.get("created_at") or ""
        try:
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(UTC)

        return TransactionRecord(
            transaction_id=str(data.get("id") or data.get("transactionId") or ""),
            amount_gbp=amount_gbp,
            asset_code=data.get("assetCode") or data.get("asset_code", "GBP"),
            description=data.get("description", ""),
            status=data.get("status", "APPROVED"),
            created_at=created_at,
            external_id=data.get("externalId") or data.get("external_id", ""),
            metadata=data.get("metadata") or {},
        )


# ── Stub adapter (tests / environments without Midaz) ─────────────────────────


class StubLedgerAdapter:
    """
    In-memory stub for unit tests and CI environments without Midaz.

    Usage:
        adapter = StubLedgerAdapter({"acct-id": Decimal("5000.00")})
        balance = adapter.get_balance(org, ledger, "acct-id")  # → 5000.00
    """

    def __init__(self, balances: dict | None = None) -> None:
        self._balances: dict[str, Decimal] = balances or {}
        self._transactions: list[TransactionRecord] = []

    def get_balance(self, org_id: str, ledger_id: str, account_id: str) -> Decimal:
        return self._balances.get(account_id, Decimal("0"))

    def create_transaction(
        self,
        org_id: str,
        ledger_id: str,
        request: TransactionRequest,
    ) -> TransactionRecord | None:
        record = TransactionRecord(
            transaction_id=f"stub-tx-{len(self._transactions) + 1:04d}",
            amount_gbp=request.amount_gbp,
            asset_code=request.asset_code,
            description=request.description,
            status="APPROVED",
            created_at=datetime.now(UTC),
            external_id=request.external_id,
            metadata=request.metadata,
        )
        self._transactions.append(record)
        return record

    def list_transactions(
        self,
        org_id: str,
        ledger_id: str,
        account_id: str,
        limit: int = 50,
    ) -> list[TransactionRecord]:
        return list(reversed(self._transactions[:limit]))
