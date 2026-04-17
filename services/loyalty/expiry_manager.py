"""
services/loyalty/expiry_manager.py — Points expiry management
IL-LRE-01 | Phase 29 | banxe-emi-stack

Handles 12-month rolling expiry of earned points.
Expired points deducted from balance, EXPIRE transaction appended (I-24 append-only).
HITL gate (I-27): expiry extension >365 days requires Compliance Officer approval.
FCA: PS22/9 (fair value — expiry rules must be transparent).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.loyalty.models import (
    InMemoryPointsBalanceStore,
    InMemoryPointsTransactionStore,
    PointsBalanceStorePort,
    PointsTransaction,
    PointsTransactionStorePort,
    PointsTransactionType,
)

_HITL_EXTENSION_THRESHOLD = 365


class ExpiryManager:
    """Points expiry management — detection, processing, and extension."""

    def __init__(
        self,
        tx_store: PointsTransactionStorePort | None = None,
        balance_store: PointsBalanceStorePort | None = None,
    ) -> None:
        self._tx_store = tx_store or InMemoryPointsTransactionStore()
        self._balance_store = balance_store or InMemoryPointsBalanceStore()

    def get_expiring_soon(self, customer_id: str, days_ahead: int = 30) -> dict:
        """Find EARN transactions expiring within days_ahead days.

        Returns {"expiring_transactions": [...], "total_expiring_points": str}.
        """
        now = datetime.now(UTC)
        cutoff = now + timedelta(days=days_ahead)
        all_expiring = self._tx_store.list_expiring_before(cutoff)
        customer_expiring = [t for t in all_expiring if t.customer_id == customer_id]
        total = sum((t.points for t in customer_expiring), Decimal("0"))
        return {
            "customer_id": customer_id,
            "days_ahead": days_ahead,
            "expiring_transactions": [
                {
                    "tx_id": t.tx_id,
                    "points": str(t.points),
                    "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                    "description": t.description,
                }
                for t in customer_expiring
            ],
            "total_expiring_points": str(total),
        }

    def expire_points(self, customer_id: str) -> dict:
        """Expire all overdue EARN transactions.

        Creates EXPIRE transaction (I-24 append-only) and deducts from balance.
        Returns {"expired_points": str, "transactions_processed": int}.
        """
        now = datetime.now(UTC)
        overdue = self._tx_store.list_expiring_before(now)
        customer_overdue = [
            t
            for t in overdue
            if t.customer_id == customer_id and t.tx_type == PointsTransactionType.EARN
        ]

        if not customer_overdue:
            return {"expired_points": "0", "transactions_processed": 0}

        balance = self._balance_store.get(customer_id)
        if balance is None:
            return {"expired_points": "0", "transactions_processed": 0}

        total_expired = sum((t.points for t in customer_overdue), Decimal("0"))
        new_total = max(Decimal("0"), balance.total_points - total_expired)

        expire_tx = PointsTransaction(
            tx_id=str(uuid.uuid4()),
            customer_id=customer_id,
            tx_type=PointsTransactionType.EXPIRE,
            points=-total_expired,
            balance_after=new_total,
            reference_id="",
            description=f"Points expired: {len(customer_overdue)} earn transactions",
            created_at=now,
        )
        self._tx_store.append(expire_tx)

        updated = replace(balance, total_points=new_total, updated_at=now)
        self._balance_store.update(updated)

        return {
            "expired_points": str(total_expired),
            "transactions_processed": len(customer_overdue),
        }

    def extend_expiry(
        self,
        customer_id: str,
        tx_id: str,
        extension_days: int,
    ) -> dict:
        """Extend expiry of an EARN transaction.

        HITL_REQUIRED if extension_days > 365 (I-27).
        Creates ADJUST transaction to record extension (I-24 append-only).
        """
        if extension_days > _HITL_EXTENSION_THRESHOLD:
            return {
                "status": "HITL_REQUIRED",
                "tx_id": tx_id,
                "extension_days": extension_days,
                "reason": "Expiry extension >365 days requires Compliance Officer approval (I-27)",
            }

        txs = self._tx_store.list_by_customer(customer_id)
        matching = [t for t in txs if t.tx_id == tx_id]
        if not matching:
            raise ValueError(f"Transaction not found: {tx_id} for customer: {customer_id}")

        tx = matching[0]
        base_expires = tx.expires_at or datetime.now(UTC)
        new_expires = base_expires + timedelta(days=extension_days)

        balance = self._balance_store.get(customer_id)
        current_total = balance.total_points if balance else Decimal("0")

        now = datetime.now(UTC)
        extension_tx = PointsTransaction(
            tx_id=str(uuid.uuid4()),
            customer_id=customer_id,
            tx_type=PointsTransactionType.ADJUST,
            points=Decimal("0"),
            balance_after=current_total,
            reference_id=tx_id,
            description=f"Expiry extended by {extension_days} days",
            created_at=now,
            expires_at=new_expires,
        )
        self._tx_store.append(extension_tx)

        return {
            "tx_id": tx_id,
            "new_expires_at": new_expires.isoformat(),
            "extension_days": extension_days,
        }
