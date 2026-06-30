"""
sdk/python/banxe/client.py — In-memory test stub for Banxe SDK
GAP-044 M-sdk | banxe-emi-stack

InMemoryBanxeClient: fast unit testing without HTTP calls.
Implements BanxeSdkPort Protocol for dependency injection.
Enforces I-01 (Decimal only) at runtime.
"""

from __future__ import annotations

from decimal import Decimal

from sdk.python.banxe.sdk_port import AccountBalance, PaymentResult


class InMemoryBanxeClient:
    """
    In-memory stub for unit tests — no HTTP calls.
    Fast, deterministic, no network dependencies.
    Implements BanxeSdkPort Protocol structurally.
    """

    def __init__(self) -> None:
        self._balances: dict[str, AccountBalance] = {}
        self._payments: dict[str, PaymentResult] = {}

    def seed_balance(
        self,
        account_id: str,
        currency: str,
        available: Decimal,
        ledger: Decimal,
    ) -> None:
        """
        Seed a test account balance (used in test setup).
        Enforces Decimal type (I-01).
        """
        if not isinstance(available, Decimal):
            raise TypeError(f"available must be Decimal, got {type(available)}")
        if not isinstance(ledger, Decimal):
            raise TypeError(f"ledger must be Decimal, got {type(ledger)}")

        self._balances[account_id] = AccountBalance(
            account_id=account_id,
            currency=currency,
            available=available,
            ledger=ledger,
        )

    async def get_balance(self, account_id: str) -> AccountBalance:
        """
        Fetch balance for account.
        Raises KeyError if account not found.
        """
        if account_id not in self._balances:
            raise KeyError(f"Account {account_id!r} not found")
        return self._balances[account_id]

    async def submit_payment(
        self,
        from_account: str,
        to_account: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> PaymentResult:
        """
        Submit payment with idempotency.
        Same idempotency_key returns same payment_id (no double-spend).
        Raises ValueError if amount <= 0.
        Enforces Decimal type (I-01).
        """
        if not isinstance(amount, Decimal):
            raise TypeError(f"amount must be Decimal, got {type(amount)}")

        if amount <= Decimal("0"):
            raise ValueError(f"Amount must be positive, got {amount}")

        # Idempotency: return same result if key seen before
        if idempotency_key in self._payments:
            return self._payments[idempotency_key]

        # Create new payment
        result = PaymentResult(
            payment_id=f"pay-{idempotency_key[:8]}",
            status="COMPLETED",
            idempotency_key=idempotency_key,
        )
        self._payments[idempotency_key] = result
        return result

    async def health_check(self) -> dict[str, str]:
        """
        Health check — always returns ok for in-memory stub.
        """
        return {"status": "ok", "mode": "in-memory"}
