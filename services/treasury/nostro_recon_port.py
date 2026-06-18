"""ADR-078 D2 — NOSTROReconPort (read-only). Frozen value objects, async, no transfers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

_TOLERANCE = Decimal("0.01")


class NostroReconPortError(Exception):
    """Raised on NOSTRO recon read failures."""


@dataclass(frozen=True)
class NostroBalance:
    account_id: str
    internal_gbp: Decimal
    external_gbp: Decimal
    as_of: str


@dataclass(frozen=True)
class ReconciliationResult:
    matched: bool
    difference_gbp: Decimal
    as_of: str


class NOSTROReconPort(ABC):
    @abstractmethod
    async def get_nostro_balances(self, account_id: str, as_of: str) -> NostroBalance: ...
    @abstractmethod
    async def reconcile(self, account_id: str, as_of: str) -> ReconciliationResult: ...


class InMemoryNOSTROReconPort(NOSTROReconPort):
    def __init__(self) -> None:
        self._balances: dict[tuple[str, str], NostroBalance] = {}

    def seed(self, balance: NostroBalance) -> None:
        self._balances[(balance.account_id, balance.as_of)] = balance

    async def get_nostro_balances(self, account_id: str, as_of: str) -> NostroBalance:
        key = (account_id, as_of)
        if key not in self._balances:
            raise NostroReconPortError(f"unknown account: {account_id} @ {as_of}")
        return self._balances[key]

    async def reconcile(self, account_id: str, as_of: str) -> ReconciliationResult:
        bal = await self.get_nostro_balances(account_id, as_of)
        diff = bal.internal_gbp - bal.external_gbp
        return ReconciliationResult(
            matched=abs(diff) <= _TOLERANCE, difference_gbp=diff, as_of=bal.as_of
        )
