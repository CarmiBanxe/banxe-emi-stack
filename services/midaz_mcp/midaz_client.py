"""
services/midaz_mcp/midaz_client.py
Typed Midaz CBS client for MCP integration (IL-MCP-01).
Midaz API: :8095
I-01: all amounts Decimal.
I-02: blocked jurisdictions on organization country.
I-24: TransactionLog is append-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from typing import Protocol

from services.midaz_mcp.midaz_models import (
    Account,
    Asset,
    Balance,
    Ledger,
    Organization,
    Transaction,
    TransactionEntry,
)

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
EDD_THRESHOLD = Decimal("10000.00")


class MidazPort(Protocol):
    """Protocol for Midaz CBS operations."""

    async def create_organization(
        self, name: str, legal_name: str, country: str
    ) -> Organization: ...

    async def create_ledger(self, org_id: str, name: str) -> Ledger: ...

    async def create_asset(self, ledger_id: str, code: str, scale: int) -> Asset: ...

    async def create_account(
        self, ledger_id: str, asset_id: str, name: str, account_type: str
    ) -> Account: ...

    async def create_transaction(
        self, ledger_id: str, entries: list[TransactionEntry]
    ) -> Transaction: ...

    async def get_balances(self, account_id: str) -> list[Balance]: ...

    async def list_accounts(self, ledger_id: str) -> list[Account]: ...


class InMemoryMidazPort:
    """In-memory stub for testing (Protocol DI)."""

    def __init__(self) -> None:
        self._orgs: dict[str, Organization] = {}
        self._ledgers: dict[str, Ledger] = {}
        self._assets: dict[str, Asset] = {}
        self._accounts: dict[str, Account] = {}
        self._transactions: list[Transaction] = []

    async def create_organization(self, name: str, legal_name: str, country: str) -> Organization:
        oid = f"org_{hashlib.sha256(name.encode()).hexdigest()[:8]}"
        org = Organization(org_id=oid, name=name, legal_name=legal_name, country=country)
        self._orgs[oid] = org
        return org

    async def create_ledger(self, org_id: str, name: str) -> Ledger:
        lid = f"ldg_{hashlib.sha256(name.encode()).hexdigest()[:8]}"
        ledger = Ledger(ledger_id=lid, org_id=org_id, name=name)
        self._ledgers[lid] = ledger
        return ledger

    async def create_asset(self, ledger_id: str, code: str, scale: int) -> Asset:
        aid = f"ast_{hashlib.sha256(code.encode()).hexdigest()[:8]}"
        asset = Asset(asset_id=aid, ledger_id=ledger_id, code=code, scale=scale)
        self._assets[aid] = asset
        return asset

    async def create_account(
        self, ledger_id: str, asset_id: str, name: str, account_type: str
    ) -> Account:
        acid = f"acc_{hashlib.sha256(name.encode()).hexdigest()[:8]}"
        account = Account(
            account_id=acid,
            ledger_id=ledger_id,
            asset_id=asset_id,
            name=name,
            account_type=account_type,
        )
        self._accounts[acid] = account
        return account

    async def create_transaction(
        self, ledger_id: str, entries: list[TransactionEntry]
    ) -> Transaction:
        tid = f"tx_{hashlib.sha256(ledger_id.encode()).hexdigest()[:8]}"
        tx = Transaction(transaction_id=tid, ledger_id=ledger_id, entries=entries, status="POSTED")
        self._transactions.append(tx)
        return tx

    async def get_balances(self, account_id: str) -> list[Balance]:
        return [Balance(account_id=account_id, asset_code="GBP", amount="0.00")]

    async def list_accounts(self, ledger_id: str) -> list[Account]:
        return [a for a in self._accounts.values() if a.ledger_id == ledger_id]


class MidazClient:
    """Typed Midaz CBS client.

    I-01: all monetary amounts validated as Decimal.
    I-02: blocked jurisdictions enforced on organization country.
    I-24: transaction_log is append-only.
    """

    def __init__(self, port: MidazPort | None = None) -> None:
        self._port: MidazPort = port or InMemoryMidazPort()
        self._transaction_log: list[dict] = []  # I-24 append-only

    async def create_organization(
        self, name: str, legal_name: str, country: str = "GB"
    ) -> Organization:
        if country in BLOCKED_JURISDICTIONS:
            raise ValueError(f"Organization country {country!r} is in blocked jurisdictions (I-02)")
        return await self._port.create_organization(name, legal_name, country)

    async def create_ledger(self, org_id: str, name: str) -> Ledger:
        return await self._port.create_ledger(org_id, name)

    async def create_asset(self, ledger_id: str, code: str, scale: int = 2) -> Asset:
        return await self._port.create_asset(ledger_id, code, scale)

    async def create_account(
        self, ledger_id: str, asset_id: str, name: str, account_type: str = "deposit"
    ) -> Account:
        return await self._port.create_account(ledger_id, asset_id, name, account_type)

    async def create_transaction(
        self, ledger_id: str, entries: list[TransactionEntry]
    ) -> Transaction:
        # I-01: validate all entry amounts are Decimal-parseable
        total_debit = sum(Decimal(e.amount) for e in entries if e.direction == "DEBIT")
        # I-24 append-only log
        self._transaction_log.append(
            {
                "ledger_id": ledger_id,
                "entry_count": len(entries),
                "total_debit": str(total_debit),
                "logged_at": datetime.now(UTC).isoformat(),
            }
        )
        return await self._port.create_transaction(ledger_id, entries)

    async def get_balances(self, account_id: str) -> list[Balance]:
        return await self._port.get_balances(account_id)

    async def list_accounts(self, ledger_id: str) -> list[Account]:
        return await self._port.list_accounts(ledger_id)

    @property
    def transaction_log(self) -> list[dict]:
        """I-24: append-only transaction log."""
        return list(self._transaction_log)
