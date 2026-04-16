"""
services/multi_currency/conversion_tracker.py — Currency conversion recording and summary.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Conversion fee = 0.2% (Decimal("0.002") × from_amount).

Invariants:
  - I-01: All monetary amounts (fee, amounts, rate) are Decimal — never float.
  - I-24: All conversions logged via MCAuditPort.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.multi_currency.models import (
    ConversionRecord,
    ConversionStatus,
    ConversionStorePort,
    LedgerEntryPort,
    MCAuditPort,
    MCEventEntry,
)

_CONVERSION_FEE_RATE = Decimal("0.002")  # 0.2%


class ConversionTracker:
    """Records FX conversions, computes fees, and produces summaries."""

    def __init__(
        self,
        conversion_store: ConversionStorePort,
        ledger_store: LedgerEntryPort,
        audit: MCAuditPort,
    ) -> None:
        self._conversions = conversion_store
        self._ledger = ledger_store
        self._audit = audit

    async def record_conversion(
        self,
        account_id: str,
        from_currency: str,
        to_currency: str,
        from_amount: Decimal,
        to_amount: Decimal,
        rate: Decimal,
    ) -> ConversionRecord:
        """Record a completed FX conversion. Fee = 0.2% of from_amount.

        Returns the saved ConversionRecord with status=COMPLETED.
        """
        fee = from_amount * _CONVERSION_FEE_RATE
        record = ConversionRecord(
            conversion_id=f"conv-{uuid.uuid4().hex[:12]}",
            account_id=account_id,
            from_currency=from_currency,
            to_currency=to_currency,
            from_amount=from_amount,
            to_amount=to_amount,
            rate=rate,
            fee=fee,
            status=ConversionStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        await self._conversions.save(record)
        await self._audit.log(
            MCEventEntry(
                event_id=uuid.uuid4().hex,
                account_id=account_id,
                event_type="CONVERSION_COMPLETED",
                currency=from_currency,
                amount=from_amount,
                created_at=datetime.now(UTC),
            )
        )
        return record

    async def get_conversion(self, conversion_id: str) -> ConversionRecord | None:
        """Fetch a conversion record by ID."""
        return await self._conversions.get(conversion_id)

    async def list_conversions(self, account_id: str) -> list[ConversionRecord]:
        """List all conversion records for an account."""
        return await self._conversions.list_by_account(account_id)

    async def get_conversion_summary(self, account_id: str) -> dict:
        """Return aggregated summary: total conversions, total fees, currencies used.

        Returns:
            {
                "total_conversions": int,
                "total_fees": str (Decimal as string — I-05),
                "currencies_used": list[str],
            }
        """
        records = await self._conversions.list_by_account(account_id)
        total_fees = sum((r.fee for r in records), Decimal("0"))
        currencies: list[str] = []
        seen: set[str] = set()
        for r in records:
            for ccy in (r.from_currency, r.to_currency):
                if ccy not in seen:
                    seen.add(ccy)
                    currencies.append(ccy)
        return {
            "total_conversions": len(records),
            "total_fees": str(total_fees),
            "currencies_used": currencies,
        }
