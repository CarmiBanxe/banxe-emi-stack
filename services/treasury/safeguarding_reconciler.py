"""
services/treasury/safeguarding_reconciler.py
IL-TLM-01 | Phase 17

Automated CASS 15.3 safeguarding reconciliation.
Compares book records vs external bank statements.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.treasury.models import (
    ReconciliationRecord,
    ReconciliationStatus,
    ReconciliationStorePort,
    SafeguardingAccount,
    TreasuryAuditPort,
)

_MATCH_TOLERANCE = Decimal("0.01")  # variance below 1p treated as MATCHED


class SafeguardingReconciler:
    """CASS 15.3 automated safeguarding reconciliation.

    Compares book balance (SafeguardingAccount.balance) against the
    bank-confirmed balance and flags discrepancies above tolerance.
    """

    def __init__(
        self,
        recon_store: ReconciliationStorePort,
        audit: TreasuryAuditPort,
    ) -> None:
        self._store = recon_store
        self._audit = audit

    async def reconcile(
        self,
        account: SafeguardingAccount,
        bank_balance: Decimal,
        actor: str,
    ) -> ReconciliationRecord:
        """Run reconciliation for a safeguarding account against bank balance."""
        variance = account.balance - bank_balance
        abs_variance = abs(variance)
        status = (
            ReconciliationStatus.MATCHED
            if abs_variance < _MATCH_TOLERANCE
            else ReconciliationStatus.DISCREPANCY
        )
        notes = (
            "Balances within tolerance."
            if status == ReconciliationStatus.MATCHED
            else f"Variance of {variance} detected — requires investigation."
        )
        now = datetime.now(UTC)
        record = ReconciliationRecord(
            id=str(uuid.uuid4()),
            account_id=account.id,
            period_date=now,
            book_balance=account.balance,
            bank_balance=bank_balance,
            variance=variance,
            status=status,
            reconciled_at=now,
            notes=notes,
        )
        await self._store.save_record(record)

        event_type = (
            "reconciliation.completed"
            if status == ReconciliationStatus.MATCHED
            else "reconciliation.discrepancy"
        )
        await self._audit.log(
            event_type=event_type,
            entity_id=account.id,
            details={
                "record_id": record.id,
                "book_balance": str(account.balance),
                "bank_balance": str(bank_balance),
                "variance": str(variance),
                "status": status.value,
            },
            actor=actor,
        )
        return record

    async def get_latest_reconciliation(self, account_id: str) -> ReconciliationRecord | None:
        """Return the most recent reconciliation record for an account."""
        return await self._store.get_latest(account_id)

    async def list_reconciliations(
        self, account_id: str | None = None
    ) -> list[ReconciliationRecord]:
        """List reconciliation records, optionally filtered by account."""
        return await self._store.list_records(account_id)

    async def check_all_compliant(self, accounts: list[SafeguardingAccount]) -> bool:
        """Return True if all accounts have a most-recent MATCHED reconciliation."""
        for account in accounts:
            latest = await self._store.get_latest(account.id)
            if latest is None or latest.status != ReconciliationStatus.MATCHED:
                return False
        return True
