"""
services/multi_currency/nostro_reconciler.py — Nostro/vostro reconciliation engine.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Nostro reconciliation tolerance is £1.00 (broader than internal 1p due to
correspondent banking settlement timing).

Invariants:
  - I-01: All monetary amounts are Decimal — never float.
  - I-24: All reconciliation events logged via MCAuditPort.
  - MATCHED if abs(variance) <= Decimal("1.00"), else DISCREPANCY.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.multi_currency.models import (
    MCAuditPort,
    MCEventEntry,
    NostroAccount,
    NostroStorePort,
    ReconciliationResult,
    ReconciliationStatus,
)

_TOLERANCE = Decimal("1.00")


class NostroReconciler:
    """Reconciles our nostro balance against the correspondent bank's reported balance."""

    def __init__(
        self,
        nostro_store: NostroStorePort,
        audit: MCAuditPort,
    ) -> None:
        self._store = nostro_store
        self._audit = audit

    async def reconcile(
        self,
        nostro_id: str,
        their_balance: Decimal,
    ) -> ReconciliationResult:
        """Compare our_balance vs their_balance; MATCHED if abs(variance) <= £1.00.

        Raises:
            ValueError: if nostro account not found.
        """
        account = await self._store.get(nostro_id)
        if account is None:
            raise ValueError(f"Nostro account not found: {nostro_id}")

        variance = account.our_balance - their_balance
        status = (
            ReconciliationStatus.MATCHED
            if abs(variance) <= _TOLERANCE
            else ReconciliationStatus.DISCREPANCY
        )
        reconciled_at = datetime.now(UTC)
        updated = dataclasses.replace(
            account,
            their_balance=their_balance,
            last_reconciled=reconciled_at,
        )
        await self._store.save(updated)
        await self._audit.log(
            MCEventEntry(
                event_id=uuid.uuid4().hex,
                account_id=nostro_id,
                event_type=f"NOSTRO_RECONCILED_{status.value}",
                currency=account.currency,
                amount=abs(variance),
                created_at=reconciled_at,
            )
        )
        return ReconciliationResult(
            nostro_id=nostro_id,
            our_balance=account.our_balance,
            their_balance=their_balance,
            variance=variance,
            status=status,
            reconciled_at=reconciled_at,
        )

    async def get_nostro(self, nostro_id: str) -> NostroAccount | None:
        """Fetch a nostro account by ID."""
        return await self._store.get(nostro_id)

    async def list_nostros(self) -> list[NostroAccount]:
        """List all nostro accounts."""
        return await self._store.list_all()

    async def update_our_balance(self, nostro_id: str, balance: Decimal) -> NostroAccount:
        """Update our recorded balance on a nostro account.

        Raises:
            ValueError: if nostro account not found.
        """
        account = await self._store.get(nostro_id)
        if account is None:
            raise ValueError(f"Nostro account not found: {nostro_id}")
        updated = dataclasses.replace(account, our_balance=balance)
        await self._store.save(updated)
        await self._audit.log(
            MCEventEntry(
                event_id=uuid.uuid4().hex,
                account_id=nostro_id,
                event_type="NOSTRO_BALANCE_UPDATED",
                currency=account.currency,
                amount=balance,
                created_at=datetime.now(UTC),
            )
        )
        return updated
