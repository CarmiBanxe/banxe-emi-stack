"""
services/card_issuing/spend_control.py
IL-CIM-01 | Phase 19

Per-card spend limits: daily/monthly/per-txn, MCC blocking, geo-restrictions.
All amounts use Decimal (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from services.card_issuing.models import (
    CardAuditPort,
    SpendLimit,
    SpendLimitStorePort,
    SpendPeriod,
    TransactionStorePort,
    TransactionType,
)


class SpendControl:
    """Per-card spend limit enforcement and velocity tracking."""

    def __init__(
        self,
        limit_store: SpendLimitStorePort,
        txn_store: TransactionStorePort,
        audit: CardAuditPort,
    ) -> None:
        self._limit_store = limit_store
        self._txn_store = txn_store
        self._audit = audit

    async def set_limits(
        self,
        card_id: str,
        period: SpendPeriod,
        limit_amount_str: str,
        currency: str,
        blocked_mccs: list[str] | None = None,
        geo_restrictions: list[str] | None = None,
        actor: str = "system",
    ) -> SpendLimit:
        """Create or replace spend limits for a card."""
        limit_amount = Decimal(limit_amount_str)
        limit = SpendLimit(
            card_id=card_id,
            period=period,
            limit_amount=limit_amount,
            currency=currency,
            blocked_mccs=list(blocked_mccs or []),
            geo_restrictions=list(geo_restrictions or []),
        )
        await self._limit_store.save(limit)
        await self._audit.log(
            event_type="card.limits_set",
            card_id=card_id,
            entity_id="",
            actor=actor,
            details={
                "period": period.value,
                "limit_amount": str(limit_amount),
                "currency": currency,
                "blocked_mccs": list(blocked_mccs or []),
                "geo_restrictions": list(geo_restrictions or []),
            },
        )
        return limit

    async def get_limits(self, card_id: str) -> SpendLimit | None:
        """Return current spend limits for a card, or None if not set."""
        return await self._limit_store.get(card_id)

    async def check_authorisation(
        self,
        card_id: str,
        amount: Decimal,
        currency: str,
        mcc: str,
        country: str,
    ) -> tuple[bool, str]:
        """
        Check if a transaction is allowed under spend limits.
        Returns (True, "") if allowed, or (False, reason) if declined.
        Permissive (allowed) when no limits are configured.
        """
        limit = await self._limit_store.get(card_id)
        if limit is None:
            return True, ""

        if mcc in limit.blocked_mccs:
            return False, f"MCC {mcc} is blocked"

        if country in limit.geo_restrictions:
            return False, f"Country {country} is geo-restricted"

        if limit.period == SpendPeriod.PER_TRANSACTION:
            if amount > limit.limit_amount:
                return False, f"Amount {amount} exceeds per-transaction limit {limit.limit_amount}"

        return True, ""

    async def get_daily_spent(self, card_id: str, currency: str) -> Decimal:
        """Sum of today's PURCHASE transactions for the card."""
        txns = await self._txn_store.list_txns(card_id)
        today = datetime.now(UTC).date()
        total = Decimal("0")
        for txn in txns:
            if (
                txn.transaction_type == TransactionType.PURCHASE
                and txn.currency == currency
                and txn.posted_at.date() == today
            ):
                total += txn.amount
        return total

    async def get_monthly_spent(self, card_id: str, currency: str) -> Decimal:
        """Sum of this month's PURCHASE transactions for the card."""
        txns = await self._txn_store.list_txns(card_id)
        now = datetime.now(UTC)
        total = Decimal("0")
        for txn in txns:
            if (
                txn.transaction_type == TransactionType.PURCHASE
                and txn.currency == currency
                and txn.posted_at.year == now.year
                and txn.posted_at.month == now.month
            ):
                total += txn.amount
        return total
