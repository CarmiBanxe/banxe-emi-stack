"""
services/savings/accrual_engine.py — Daily interest accrual batch (I-24 append-only)
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.savings.interest_calculator import InterestCalculator
from services.savings.models import (
    AccountStatus,
    InMemoryInterestAccrualStore,
    InMemorySavingsAccountStore,
    InMemorySavingsProductStore,
    InterestAccrual,
    InterestAccrualPort,
    SavingsAccountPort,
    SavingsProductPort,
)


class AccrualEngine:
    def __init__(
        self,
        account_store: SavingsAccountPort | None = None,
        accrual_store: InterestAccrualPort | None = None,
        product_store: SavingsProductPort | None = None,
    ) -> None:
        self._account_store = account_store or InMemorySavingsAccountStore()
        self._accrual_store = accrual_store or InMemoryInterestAccrualStore()
        self._product_store = product_store or InMemorySavingsProductStore()
        self._calc = InterestCalculator()

    def accrue_daily(self, account_id: str) -> dict[str, str]:
        """Accrue one day of interest — appended to store (I-24)."""
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        if account.status != AccountStatus.ACTIVE:
            raise ValueError(f"Account {account_id} is not ACTIVE")
        product = self._product_store.get(account.product_id)
        if product is None:
            raise ValueError(f"Product not found: {account.product_id}")
        now = datetime.now(UTC)
        daily = self._calc.calculate_daily_interest(account.balance, product.gross_rate)
        accrual = InterestAccrual(
            accrual_id=str(uuid.uuid4()),
            account_id=account_id,
            amount=daily,
            period_start=now,
            period_end=now,
            capitalized=False,
            created_at=now,
        )
        self._accrual_store.save(accrual)
        updated = dataclasses.replace(account, accrued_interest=account.accrued_interest + daily)
        self._account_store.update(updated)
        return {
            "account_id": account_id,
            "accrual_id": accrual.accrual_id,
            "amount": str(daily),
            "total_accrued": str(updated.accrued_interest),
        }

    def capitalize_monthly(self, account_id: str) -> dict[str, object]:
        """Move all uncapitalized accruals into the account balance."""
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        uncapitalized = self._accrual_store.list_uncapitalized(account_id)
        if not uncapitalized:
            return {"account_id": account_id, "capitalized_amount": "0", "count": 0}
        total = sum((a.amount for a in uncapitalized), Decimal("0"))
        # Append capitalized copies (cannot mutate existing — I-24)
        for a in uncapitalized:
            self._accrual_store.save(dataclasses.replace(a, capitalized=True))
        updated = dataclasses.replace(
            account,
            balance=account.balance + total,
            accrued_interest=Decimal("0"),
        )
        self._account_store.update(updated)
        return {
            "account_id": account_id,
            "capitalized_amount": str(total),
            "count": len(uncapitalized),
            "new_balance": str(updated.balance),
        }

    def get_accrual_history(self, account_id: str) -> dict[str, object]:
        accruals = self._accrual_store.list_by_account(account_id)
        return {
            "account_id": account_id,
            "accruals": [
                {
                    "accrual_id": a.accrual_id,
                    "amount": str(a.amount),
                    "period_start": a.period_start.isoformat(),
                    "capitalized": a.capitalized,
                }
                for a in accruals
            ],
            "total_records": len(accruals),
        }
