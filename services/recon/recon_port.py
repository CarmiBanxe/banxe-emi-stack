"""
services/recon/recon_port.py
LedgerPort Protocol for safeguarding reconciliation (IL-SAF-01).

Hexagonal port: adapters fetch balances from Midaz, bank APIs, etc.
InMemoryLedgerPort for unit tests.

I-01: All monetary values are Decimal.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from services.recon.recon_models import AccountBalance


class LedgerPort(Protocol):
    """Port for fetching account balances from the ledger (Midaz adapter)."""

    def get_client_fund_balances(self, as_of_date: str) -> list[AccountBalance]:
        """Return all client fund account balances as of a given date."""
        ...

    def get_safeguarding_balances(self, as_of_date: str) -> list[AccountBalance]:
        """Return all safeguarding account balances as of a given date."""
        ...


class InMemoryLedgerPort:
    """Configurable in-memory stub for testing."""

    def __init__(self) -> None:
        self._client_funds: list[AccountBalance] = []
        self._safeguarding: list[AccountBalance] = []

    def set_client_funds(self, balances: list[AccountBalance]) -> None:
        self._client_funds = list(balances)

    def set_safeguarding(self, balances: list[AccountBalance]) -> None:
        self._safeguarding = list(balances)

    def add_client_fund(
        self,
        account_id: str,
        balance: Decimal,
        currency: str = "GBP",
        jurisdiction: str = "GB",
        account_name: str = "",
    ) -> None:
        self._client_funds.append(
            AccountBalance(
                account_id=account_id,
                account_name=account_name or f"Client-{account_id}",
                balance=balance,
                currency=currency,
                jurisdiction=jurisdiction,
            )
        )

    def add_safeguarding(
        self,
        account_id: str,
        balance: Decimal,
        currency: str = "GBP",
        jurisdiction: str = "GB",
        account_name: str = "",
    ) -> None:
        self._safeguarding.append(
            AccountBalance(
                account_id=account_id,
                account_name=account_name or f"Safeguarding-{account_id}",
                balance=balance,
                currency=currency,
                jurisdiction=jurisdiction,
            )
        )

    def get_client_fund_balances(self, as_of_date: str) -> list[AccountBalance]:
        return list(self._client_funds)

    def get_safeguarding_balances(self, as_of_date: str) -> list[AccountBalance]:
        return list(self._safeguarding)
