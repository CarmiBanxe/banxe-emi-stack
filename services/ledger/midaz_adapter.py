"""
midaz_adapter.py — Sync LedgerPort adapter for Midaz CBS
Block D-recon, IL-013 Sprint 9
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
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
import logging
import os

import httpx

logger = logging.getLogger(__name__)

MIDAZ_BASE_URL = os.environ.get("MIDAZ_BASE_URL", "http://localhost:8095")
MIDAZ_TOKEN = os.environ.get("MIDAZ_TOKEN", "")
_TIMEOUT = 10.0


class MidazLedgerAdapter:
    """
    Synchronous adapter implementing LedgerPortProtocol.

    Wraps async Midaz HTTP calls in asyncio.run() so that
    ReconciliationEngine (sync) can use Midaz (async) without
    coupling the domain layer to an event loop.

    Thread safety: one asyncio.run() per call — safe for cron / CLI use.
    Not intended for high-frequency async contexts (use midaz_client.py directly).
    """

    def __init__(
        self,
        base_url: str = MIDAZ_BASE_URL,
        token: str = MIDAZ_TOKEN,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Only set Authorization header when token is non-empty.
        # Midaz v3.5.x in local mode may not require auth.
        self._headers: dict = {"Content-Type": "application/json"}
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

        FCA invariant: amounts MUST be Decimal, never float (I-24).
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

    # ── internal async implementation ────────────────────────────────────────

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


class StubLedgerAdapter:
    """
    In-memory stub for unit tests and CI environments without Midaz.

    Usage:
        adapter = StubLedgerAdapter({"acct-id": Decimal("5000.00")})
        balance = adapter.get_balance(org, ledger, "acct-id")  # → 5000.00
    """

    def __init__(self, balances: dict | None = None) -> None:
        self._balances: dict[str, Decimal] = balances or {}

    def get_balance(self, org_id: str, ledger_id: str, account_id: str) -> Decimal:
        return self._balances.get(account_id, Decimal("0"))
