"""ADR-078 D2 — NOSTROReconPort (read-only contract). No transfer initiation."""
from __future__ import annotations
from abc import ABC, abstractmethod
from decimal import Decimal


class NOSTROReconPortError(Exception):
    """Raised on NOSTRO recon read failures."""


class NOSTROReconPort(ABC):
    @abstractmethod
    def get_nostro_balances(self, account: str) -> dict[str, Decimal]:
        """Return {'internal': Decimal, 'external': Decimal} for an account."""

    @abstractmethod
    def reconcile(self, account: str) -> Decimal:
        """Return internal-minus-external delta (read-only comparison)."""


class InMemoryNOSTROReconPort(NOSTROReconPort):
    def __init__(self, balances: dict[str, dict[str, Decimal]] | None = None) -> None:
        self._balances = dict(balances or {})

    def get_nostro_balances(self, account: str) -> dict[str, Decimal]:
        if account not in self._balances:
            raise NOSTROReconPortError(f"unknown account: {account}")
        return dict(self._balances[account])

    def reconcile(self, account: str) -> Decimal:
        b = self.get_nostro_balances(account)
        return b["internal"] - b["external"]
