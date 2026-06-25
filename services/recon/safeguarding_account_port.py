"""
services/recon/safeguarding_account_port.py
SafeguardingAccountPort — Leg B interface contract (E-D-CROSS-REPO-HANDOFF §4).

E-safeguard Leg B: provides safeguarding bank account balance to D-recon
three-leg reconciliation. Enforces client-money segregation (E-1):
operational accounts cannot draw on client_funds balances.

I-01: get_balance returns Decimal — never float.
I-24: append-only; segregation violations raise SegregationViolationError.
E-1:  operational debit cannot draw on client_funds (relevant_funds_fully_segregated).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

AccountType = Literal["client_funds", "operational"]


class SegregationViolationError(Exception):
    """Raised when an operational account attempts to access client_funds balance."""


@runtime_checkable
class SafeguardingAccountPort(Protocol):
    """Leg B balance port — FCA CASS 15 safeguarding accounts.

    E-D-CROSS-REPO-HANDOFF §4 interface contract:
        get_balance(account_id, currency) -> Decimal
    """

    def get_balance(self, account_id: str, currency: str) -> Decimal:
        """Return safeguarding account balance (Decimal, I-01).

        Raises:
            SegregationViolationError: if cross-type access is attempted.
            KeyError: if account_id is not registered.
        """
        ...


class InMemorySafeguardingAccountPort:
    """Test stub implementing SafeguardingAccountPort with E-1 segregation enforcement.

    Accounts are registered with an explicit ``account_type``:
      - "client_funds" — ring-fenced; only client_funds reads allowed
      - "operational"  — operational funds; cannot read client_funds balances

    An attempt to read a ``client_funds`` account via a caller that has registered
    only as an ``operational`` accessor raises ``SegregationViolationError`` (E-1).
    """

    def __init__(self) -> None:
        self._accounts: dict[str, tuple[Decimal, str, AccountType]] = {}

    def register_account(
        self,
        account_id: str,
        balance: Decimal,
        currency: str,
        account_type: AccountType,
    ) -> None:
        """Register an account with its balance, currency and type."""
        if not isinstance(balance, Decimal):
            raise TypeError(f"balance must be Decimal (I-01), got {type(balance).__name__}")
        self._accounts[account_id] = (balance, currency, account_type)

    def get_balance(self, account_id: str, currency: str) -> Decimal:
        """Return balance for account_id/currency pair."""
        if account_id not in self._accounts:
            raise KeyError(f"account {account_id!r} not registered")
        balance, stored_currency, _account_type = self._accounts[account_id]
        if stored_currency != currency:
            raise ValueError(
                f"currency mismatch: account {account_id!r} holds {stored_currency}, "
                f"requested {currency}"
            )
        return balance

    def get_balance_as_type(
        self,
        account_id: str,
        currency: str,
        requester_type: AccountType,
    ) -> Decimal:
        """E-1 segregation check: raise if operational tries to draw on client_funds.

        Use this method when the caller's account_type is known (e.g. during
        a debit posting). Plain ``get_balance`` is used by D-recon engine (no
        cross-type access since D-recon reads each leg independently).
        """
        if account_id not in self._accounts:
            raise KeyError(f"account {account_id!r} not registered")
        balance, stored_currency, account_type = self._accounts[account_id]
        if stored_currency != currency:
            raise ValueError(
                f"currency mismatch: account {account_id!r} holds {stored_currency}, "
                f"requested {currency}"
            )
        if requester_type == "operational" and account_type == "client_funds":
            raise SegregationViolationError(
                f"E-1 violation: operational access to client_funds account {account_id!r} "
                "is prohibited (relevant_funds_fully_segregated)"
            )
        return balance

    @property
    def accounts(self) -> dict[str, tuple[Decimal, str, AccountType]]:
        return dict(self._accounts)
