"""
sandbox_service.py — InMemorySandboxService: in-memory sandbox implementation
GAP-042 M-sandbox: Sandbox Mock Rails Service
banxe-emi-stack

InMemory implementation of SandboxPort. Used for development and testing.
Stores all accounts and payment states in memory (no persistence).
Thread-safe dict operations. Resettable for test isolation.
"""

from __future__ import annotations

from decimal import Decimal
import logging

from services.sandbox.sandbox_port import SandboxAccount, SandboxPaymentTransition

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    "PENDING": {"PROCESSING"},
    "PROCESSING": {"COMPLETED", "FAILED"},
}


class InMemorySandboxService:
    """
    In-memory implementation of SandboxPort.

    Stores all accounts and payment states in instance dicts.
    Use for:
      - Development without external dependencies
      - Unit and integration tests
      - Sandbox/staging environment validation

    Thread-safe: all operations use dict access (GIL-protected in CPython).
    Resettable: call .reset() to clear state between tests.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, SandboxAccount] = {}
        self._payment_states: dict[str, str] = {}
        logger.info("InMemorySandboxService initialised")

    def seed_account(
        self,
        account_id: str,
        holder_name: str,
        currency: str,
        balance: Decimal,
    ) -> SandboxAccount:
        """Create or update a test account."""
        if balance < Decimal("0"):
            raise ValueError(f"balance must be >= 0, got {balance}")

        account = SandboxAccount(
            account_id=account_id,
            holder_name=holder_name,
            currency=currency,
            balance=balance,
        )
        self._accounts[account_id] = account
        logger.info(
            "InMemorySandboxService.seed_account: id=%s balance=%s%s",
            account_id,
            balance,
            currency,
        )
        return account

    def get_account(self, account_id: str) -> SandboxAccount | None:
        """Fetch a seeded account by ID."""
        return self._accounts.get(account_id)

    def list_accounts(self) -> list[SandboxAccount]:
        """List all seeded accounts."""
        return list(self._accounts.values())

    def register_payment(
        self,
        payment_id: str,
        initial_status: str = "PENDING",
    ) -> None:
        """Register a payment for state tracking."""
        self._payment_states[payment_id] = initial_status

    def advance_payment(
        self,
        payment_id: str,
        target_status: str,
    ) -> SandboxPaymentTransition:
        """Advance a tracked payment's status."""
        if payment_id not in self._payment_states:
            raise ValueError(f"payment {payment_id} not registered")

        from_status = self._payment_states[payment_id]
        if from_status not in VALID_TRANSITIONS:
            raise ValueError(f"status {from_status} has no valid transitions")

        if target_status not in VALID_TRANSITIONS[from_status]:
            raise ValueError(f"invalid transition: {from_status} → {target_status}")

        self._payment_states[payment_id] = target_status
        transition = SandboxPaymentTransition(
            payment_id=payment_id,
            from_status=from_status,
            to_status=target_status,
        )
        logger.info(
            "InMemorySandboxService.advance_payment: id=%s %s → %s",
            payment_id,
            from_status,
            target_status,
        )
        return transition

    def reset(self) -> None:
        """Clear all state (test isolation)."""
        self._accounts.clear()
        self._payment_states.clear()
        logger.info("InMemorySandboxService.reset: state cleared")

    def account_count(self) -> int:
        """Return the number of seeded accounts."""
        return len(self._accounts)
