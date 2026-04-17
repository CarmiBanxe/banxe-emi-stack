"""
services/savings/maturity_handler.py — Fixed-term maturity processing and early withdrawal penalties
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import uuid

from services.savings.interest_calculator import InterestCalculator
from services.savings.models import (
    AccountStatus,
    EarlyWithdrawalPenalty,
    InMemorySavingsAccountStore,
    InMemorySavingsProductStore,
    MaturityAction,
    MaturitySchedule,
    SavingsAccountPort,
    SavingsAccountType,
    SavingsProductPort,
)

_PENALTY_DAYS: dict[SavingsAccountType, int] = {
    SavingsAccountType.FIXED_TERM_3M: 30,
    SavingsAccountType.FIXED_TERM_6M: 60,
    SavingsAccountType.FIXED_TERM_12M: 90,
}


class MaturityHandler:
    def __init__(
        self,
        account_store: SavingsAccountPort | None = None,
        product_store: SavingsProductPort | None = None,
    ) -> None:
        self._account_store = account_store or InMemorySavingsAccountStore()
        self._product_store = product_store or InMemorySavingsProductStore()
        self._calc = InterestCalculator()
        self._schedules: dict[str, MaturitySchedule] = {}

    def set_maturity_preference(
        self,
        account_id: str,
        action: MaturityAction,
        payout_account_id: str | None = None,
    ) -> dict[str, str]:
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        if account.maturity_date is None:
            raise ValueError(f"Account {account_id} has no maturity date")
        schedule = MaturitySchedule(
            schedule_id=str(uuid.uuid4()),
            account_id=account_id,
            maturity_date=account.maturity_date,
            action=action,
            payout_account_id=payout_account_id,
            processed=False,
            processed_at=None,
        )
        self._schedules[account_id] = schedule
        updated = dataclasses.replace(
            account,
            auto_renew=(action == MaturityAction.AUTO_RENEW),
            payout_account_id=payout_account_id,
        )
        self._account_store.update(updated)
        return {
            "account_id": account_id,
            "action": action.value,
            "schedule_id": schedule.schedule_id,
        }

    def process_maturity(self, account_id: str) -> dict[str, object]:
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        if account.status != AccountStatus.ACTIVE:
            raise ValueError(f"Account {account_id} is not ACTIVE")
        if account.maturity_date is None:
            raise ValueError(f"Account {account_id} has no maturity date")
        schedule = self._schedules.get(account_id)
        action = schedule.action if schedule else MaturityAction.PAYOUT
        if action == MaturityAction.AUTO_RENEW:
            self._account_store.update(dataclasses.replace(account, status=AccountStatus.ACTIVE))
            return {
                "account_id": account_id,
                "action": "AUTO_RENEW",
                "balance": str(account.balance),
            }
        updated = dataclasses.replace(account, status=AccountStatus.MATURED)
        self._account_store.update(updated)
        return {
            "account_id": account_id,
            "action": "PAYOUT",
            "balance": str(account.balance),
            "payout_account_id": account.payout_account_id,
        }

    def calculate_early_withdrawal_penalty(self, account_id: str) -> EarlyWithdrawalPenalty:
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        product = self._product_store.get(account.product_id)
        if product is None:
            raise ValueError(f"Product not found: {account.product_id}")
        penalty_days = _PENALTY_DAYS.get(product.account_type, 0)
        penalty_amount = self._calc.calculate_penalty_amount(
            account.balance, product.gross_rate, penalty_days
        )
        return EarlyWithdrawalPenalty(
            penalty_id=str(uuid.uuid4()),
            account_id=account_id,
            penalty_days=penalty_days,
            penalty_amount=penalty_amount,
            calculated_at=datetime.now(UTC),
        )

    def get_maturity_schedule(self, account_id: str) -> dict[str, object]:
        schedule = self._schedules.get(account_id)
        if schedule is None:
            return {"account_id": account_id, "schedule": None}
        return {
            "account_id": account_id,
            "schedule_id": schedule.schedule_id,
            "maturity_date": schedule.maturity_date.isoformat(),
            "action": schedule.action.value,
            "payout_account_id": schedule.payout_account_id,
            "processed": schedule.processed,
        }
