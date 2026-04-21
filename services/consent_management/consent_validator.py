"""
services/consent_management/consent_validator.py
Consent Validator
IL-CNS-01 | Phase 49 | Sprint 35

FCA: PSD2 Art.65-67, RTS on SCA Art.29-32
Trust Zone: RED

Validates consent scope coverage, transaction limits (Decimal, I-01),
expiry, and generates customer consent summaries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging

from services.consent_management.models import (
    ConsentScope,
    ConsentStatus,
    ConsentStorePort,
    InMemoryConsentStore,
)

logger = logging.getLogger(__name__)


class ConsentValidator:
    """Consent validation service.

    Protocol DI: ConsentStorePort.
    I-01: All amount comparisons use Decimal.
    """

    def __init__(self, consent_store: ConsentStorePort | None = None) -> None:
        """Initialise with injectable consent store (default: InMemory stub)."""
        self._store: ConsentStorePort = consent_store or InMemoryConsentStore()

    def check_scope_coverage(self, consent_id: str, requested_scopes: list[ConsentScope]) -> bool:
        """Check if consent covers all requested scopes.

        Args:
            consent_id: Consent to check.
            requested_scopes: Scopes required by the operation.

        Returns:
            True if all requested scopes are covered.
        """
        consent = self._store.get(consent_id)
        if consent is None:
            return False
        return all(scope in consent.scopes for scope in requested_scopes)

    def check_transaction_limit(self, consent_id: str, amount: Decimal) -> bool:
        """Check if amount is within consent transaction limit (I-01: Decimal).

        Args:
            consent_id: Consent to check.
            amount: Transaction amount as Decimal (I-01).

        Returns:
            True if no limit set, or amount <= limit.
        """
        consent = self._store.get(consent_id)
        if consent is None:
            return False
        if consent.transaction_limit is None:
            return True
        return amount <= consent.transaction_limit  # I-01: Decimal comparison

    def is_consent_valid(self, consent_id: str) -> bool:
        """Check if consent is ACTIVE and not expired.

        Args:
            consent_id: Consent to check.

        Returns:
            True if consent is ACTIVE and not yet expired.
        """
        consent = self._store.get(consent_id)
        if consent is None:
            return False
        if consent.status != ConsentStatus.ACTIVE:
            return False
        now = datetime.now(UTC).isoformat()
        return consent.expires_at > now

    def get_consent_summary(self, customer_id: str) -> dict[str, int]:
        """Get consent counts by status for a customer.

        Args:
            customer_id: Customer identifier.

        Returns:
            Dict with active_count, expired_count, revoked_count, pending_count.
        """
        consents = self._store.list_by_customer(customer_id)
        now = datetime.now(UTC).isoformat()

        summary: dict[str, int] = {
            "active_count": 0,
            "expired_count": 0,
            "revoked_count": 0,
            "pending_count": 0,
            "total_count": len(consents),
        }

        seen: dict[str, object] = {}
        for c in consents:
            seen[c.consent_id] = c

        for c in seen.values():
            if c.status == ConsentStatus.REVOKED:  # type: ignore[union-attr]
                summary["revoked_count"] += 1
            elif c.status == ConsentStatus.PENDING:  # type: ignore[union-attr]
                summary["pending_count"] += 1
            elif c.status == ConsentStatus.ACTIVE and c.expires_at > now:  # type: ignore[union-attr]
                summary["active_count"] += 1
            else:
                summary["expired_count"] += 1

        return summary
