"""
sdk/python/banxe/sdk_port.py — Protocol DI port for Banxe SDK
GAP-044 M-sdk | banxe-emi-stack

Defines SdkPort Protocol and core value objects for the Banxe client SDK.
Enables dependency injection: real HttpBanxeClient (production) + InMemoryBanxeClient (tests).

All monetary values use Decimal (I-01: never float).
Amounts cross API boundaries as strings, parsed to Decimal in the client.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class AccountBalance:
    """
    Real-time account balance from Banxe ledger.
    All amounts are Decimal (I-01).
    """

    account_id: str
    currency: str
    available: Decimal  # I-01: Decimal only, never float
    ledger: Decimal  # I-01: Decimal only, never float


@dataclass(frozen=True)
class PaymentResult:
    """
    Result of a payment submission.
    Status values: PENDING | PROCESSING | COMPLETED | FAILED.
    """

    payment_id: str
    status: str  # PENDING | PROCESSING | COMPLETED | FAILED
    idempotency_key: str


class BanxeSdkPort(Protocol):
    """
    Protocol for Banxe client SDK adapters.
    Enables hexagonal architecture: real HTTP adapter vs in-memory test stub.
    """

    async def get_balance(self, account_id: str) -> AccountBalance:
        """
        Fetch real-time balance for an account.
        Raises KeyError if account not found.
        """
        ...

    async def submit_payment(
        self,
        from_account: str,
        to_account: str,
        amount: Decimal,  # I-01: Decimal only
        currency: str,
        idempotency_key: str,
    ) -> PaymentResult:
        """
        Submit a payment.
        Idempotency: same idempotency_key returns same payment_id.
        Raises ValueError if amount <= 0.
        """
        ...

    async def health_check(self) -> dict[str, str]:
        """
        Check API health.
        Returns dict with "status" key.
        """
        ...
