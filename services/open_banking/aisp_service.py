"""
services/open_banking/aisp_service.py
IL-OBK-01 | Phase 15

Account Information Service Provider (PSD2 Art.67)
Balances, transactions, beneficiaries access.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    AccountAccessType,
    AccountDataPort,
    AccountInfo,
    ConsentStatus,
    ConsentType,
    OBAuditTrailPort,
    Transaction,
    _new_event,
)


class AISPService:
    """Account Information Service Provider — PSD2 Art.67."""

    def __init__(
        self,
        consent_manager: ConsentManager,
        account_data: AccountDataPort,
        audit: OBAuditTrailPort,
    ) -> None:
        self._consent_manager = consent_manager
        self._account_data = account_data
        self._audit = audit

    async def _validate_aisp_consent(
        self,
        consent_id: str,
        required_permission: AccountAccessType,
    ) -> str:
        """Validate consent is AUTHORISED AISP with required permission.

        Returns aspsp_id. Raises ValueError on any failure.
        """
        consent = await self._consent_manager.get_consent(consent_id)
        if consent is None:
            raise ValueError(f"Consent not found: {consent_id}")

        if consent.type != ConsentType.AISP:
            raise ValueError(
                f"Consent {consent_id} is not an AISP consent (type={consent.type.value})"
            )

        if consent.status != ConsentStatus.AUTHORISED:
            raise ValueError(
                f"Consent {consent_id} is not authorised (status={consent.status.value})"
            )

        if required_permission not in consent.permissions:
            raise ValueError(
                f"Consent {consent_id} does not include permission {required_permission.value}"
            )

        return consent.aspsp_id

    async def get_accounts(
        self,
        consent_id: str,
        actor: str,
    ) -> list[AccountInfo]:
        """Fetch accounts for a given AISP consent."""
        aspsp_id = await self._validate_aisp_consent(consent_id, AccountAccessType.ACCOUNTS)
        consent = await self._consent_manager.get_consent(consent_id)
        accounts = await self._account_data.get_accounts(consent_id, aspsp_id)
        await self._audit.append(
            _new_event(
                event_type="aisp.accounts_fetched",
                entity_id=consent.entity_id,  # type: ignore[union-attr]
                actor=actor,
                consent_id=consent_id,
                details={"account_count": len(accounts)},
            )
        )
        return accounts

    async def get_balance(
        self,
        consent_id: str,
        account_id: str,
        actor: str,
    ) -> Decimal:
        """Fetch balance for a specific account."""
        aspsp_id = await self._validate_aisp_consent(consent_id, AccountAccessType.BALANCES)
        consent = await self._consent_manager.get_consent(consent_id)
        balance = await self._account_data.get_balance(consent_id, account_id, aspsp_id)
        await self._audit.append(
            _new_event(
                event_type="aisp.balance_fetched",
                entity_id=consent.entity_id,  # type: ignore[union-attr]
                actor=actor,
                consent_id=consent_id,
                details={"account_id": account_id},
            )
        )
        return balance

    async def get_transactions(
        self,
        consent_id: str,
        account_id: str,
        actor: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Transaction]:
        """Fetch transactions for a specific account."""
        aspsp_id = await self._validate_aisp_consent(consent_id, AccountAccessType.TRANSACTIONS)
        consent = await self._consent_manager.get_consent(consent_id)
        transactions = await self._account_data.get_transactions(
            consent_id, account_id, aspsp_id, from_date, to_date
        )
        await self._audit.append(
            _new_event(
                event_type="aisp.transactions_fetched",
                entity_id=consent.entity_id,  # type: ignore[union-attr]
                actor=actor,
                consent_id=consent_id,
                details={
                    "account_id": account_id,
                    "transaction_count": len(transactions),
                    "from_date": from_date.isoformat() if from_date else None,
                    "to_date": to_date.isoformat() if to_date else None,
                },
            )
        )
        return transactions
