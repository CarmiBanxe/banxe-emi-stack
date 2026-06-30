"""
sandbox_port.py — SandboxPort: hexagonal interface for sandbox mock rails
GAP-042 M-sandbox: Sandbox Mock Rails Service
banxe-emi-stack

Protocol + domain types for sandbox service. Used in development/testing only.
All amounts are Decimal (I-01). Protocol DI pattern: SandboxPort (Protocol)
→ InMemorySandboxService (implementation).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class SandboxAccount:
    """Test account in sandbox service."""

    account_id: str
    holder_name: str
    currency: str  # ISO-4217 (GBP, EUR, etc.)
    balance: Decimal  # I-01: Decimal only, never float


@dataclass(frozen=True)
class SandboxPaymentTransition:
    """Records a state advance on a mock payment."""

    payment_id: str
    from_status: str
    to_status: str


class SandboxPort(Protocol):
    """
    Hexagonal port for sandbox service.

    Implementations:
      - InMemorySandboxService — in-memory mock (testing only)

    All amounts MUST be Decimal. All methods are synchronous.
    """

    def seed_account(
        self,
        account_id: str,
        holder_name: str,
        currency: str,
        balance: Decimal,
    ) -> SandboxAccount:
        """
        Create or update a test account with given balance.

        Args:
            account_id: Unique account ID
            holder_name: Account holder name
            currency: ISO-4217 currency code
            balance: Starting balance (must be >= 0)

        Returns:
            SandboxAccount with the new/updated balance

        Raises:
            ValueError: if balance < 0
        """
        ...

    def get_account(self, account_id: str) -> SandboxAccount | None:
        """
        Fetch a seeded account by ID.

        Args:
            account_id: Account ID to look up

        Returns:
            SandboxAccount if found, None otherwise
        """
        ...

    def list_accounts(self) -> list[SandboxAccount]:
        """
        List all seeded accounts.

        Returns:
            List of all SandboxAccount objects (empty if none seeded)
        """
        ...

    def advance_payment(
        self,
        payment_id: str,
        target_status: str,
    ) -> SandboxPaymentTransition:
        """
        Advance a tracked payment's status.

        Valid transitions:
          - PENDING → PROCESSING
          - PROCESSING → COMPLETED
          - PROCESSING → FAILED

        Args:
            payment_id: Payment ID to advance
            target_status: Target status (PROCESSING, COMPLETED, FAILED)

        Returns:
            SandboxPaymentTransition recording the state change

        Raises:
            ValueError: if transition is invalid or payment not found
        """
        ...

    def reset(self) -> None:
        """
        Clear all accounts and payment states (test isolation).
        """
        ...

    def account_count(self) -> int:
        """
        Return the number of seeded accounts.

        Returns:
            Count of accounts
        """
        ...
