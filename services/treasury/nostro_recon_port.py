from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal


class NostroReconPortError(Exception):
    """Raised when NOSTROReconPort cannot fulfil a request."""


@dataclass(frozen=True)
class NostroBalance:
    account_id: str
    internal_gbp: Decimal
    external_gbp: Decimal
    as_of: str


@dataclass(frozen=True)
class NostroReconResult:
    account_id: str
    internal_gbp: Decimal
    external_gbp: Decimal
    difference_gbp: Decimal
    matched: bool
    as_of: str


class NOSTROReconPort(abc.ABC):
    """Read and compare internal vs external NOSTRO balances.

    DOES: read balances; surface discrepancies.
    DOES NOT: mutate balances or initiate bank transfers.
    soul: cash-position — NEVER initiate any bank transfers.
    """

    @abc.abstractmethod
    async def get_nostro_balances(self, account_id: str, as_of: str) -> NostroBalance:
        """Return internal and external NOSTRO balances for an account."""
        ...  # pragma: no cover

    @abc.abstractmethod
    async def reconcile(self, account_id: str, as_of: str) -> NostroReconResult:
        """Compare internal vs external; matched = abs(difference_gbp) <= £0.01."""
        ...  # pragma: no cover


class InMemoryNOSTROReconPort(NOSTROReconPort):
    """Configurable in-memory stub for unit tests."""

    def __init__(self) -> None:
        self._accounts: dict[str, NostroBalance] = {}

    def seed(self, balance: NostroBalance) -> None:
        self._accounts[balance.account_id] = balance

    async def get_nostro_balances(self, account_id: str, as_of: str) -> NostroBalance:
        if account_id not in self._accounts:
            raise NostroReconPortError(f"Unknown NOSTRO account: {account_id!r}")
        return self._accounts[account_id]

    async def reconcile(self, account_id: str, as_of: str) -> NostroReconResult:
        balance = await self.get_nostro_balances(account_id, as_of)
        diff = balance.internal_gbp - balance.external_gbp
        return NostroReconResult(
            account_id=account_id,
            internal_gbp=balance.internal_gbp,
            external_gbp=balance.external_gbp,
            difference_gbp=diff,
            matched=abs(diff) <= Decimal("0.01"),
            as_of=balance.as_of,
        )
