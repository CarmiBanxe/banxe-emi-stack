"""
services/savings/savings_agent.py — Savings Agent L2 orchestration facade (IL-SIE-01)
IL-SIE-01 | Phase 31 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

from services.savings.accrual_engine import AccrualEngine
from services.savings.interest_calculator import InterestCalculator
from services.savings.maturity_handler import MaturityHandler
from services.savings.models import (
    AccountStatus,
    InMemorySavingsAccountStore,
    InMemorySavingsProductStore,
    SavingsAccount,
    SavingsAccountPort,
    SavingsAccountType,
    SavingsProductPort,
)
from services.savings.product_catalog import ProductCatalog
from services.savings.rate_manager import RateManager

_EARLY_WITHDRAWAL_HITL_THRESHOLD = Decimal("50000.00")
_FIXED_TERM_TYPES = {
    SavingsAccountType.FIXED_TERM_3M,
    SavingsAccountType.FIXED_TERM_6M,
    SavingsAccountType.FIXED_TERM_12M,
}


class SavingsAgent:
    def __init__(
        self,
        account_store: SavingsAccountPort | None = None,
        product_store: SavingsProductPort | None = None,
    ) -> None:
        self._account_store = account_store or InMemorySavingsAccountStore()
        self._product_store = product_store or InMemorySavingsProductStore()
        self._catalog = ProductCatalog(product_store=self._product_store)
        self._calc = InterestCalculator()
        self._accrual = AccrualEngine(
            account_store=self._account_store,
            product_store=self._product_store,
        )
        self._maturity = MaturityHandler(
            account_store=self._account_store,
            product_store=self._product_store,
        )
        self._rate_mgr = RateManager(product_store=self._product_store)

    def open_account(
        self, customer_id: str, product_id: str, initial_deposit: Decimal
    ) -> dict[str, object]:
        product = self._product_store.get(product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        if not product.is_active:
            raise ValueError(f"Product {product_id} is not active")
        if initial_deposit < product.min_deposit:
            raise ValueError(f"Deposit {initial_deposit} below minimum {product.min_deposit}")
        if initial_deposit > product.max_deposit:
            raise ValueError(f"Deposit {initial_deposit} above maximum {product.max_deposit}")
        now = datetime.now(UTC)
        maturity_date = now + timedelta(days=product.term_days) if product.term_days > 0 else None
        account = SavingsAccount(
            account_id=str(uuid.uuid4()),
            customer_id=customer_id,
            product_id=product_id,
            balance=initial_deposit,
            accrued_interest=Decimal("0"),
            status=AccountStatus.ACTIVE,
            opened_at=now,
            maturity_date=maturity_date,
        )
        self._account_store.save(account)
        return {
            "account_id": account.account_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "balance": str(initial_deposit),
            "status": AccountStatus.ACTIVE.value,
            "maturity_date": maturity_date.isoformat() if maturity_date else None,
        }

    def deposit(self, account_id: str, amount: Decimal) -> dict[str, str]:
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        if account.status != AccountStatus.ACTIVE:
            raise ValueError(f"Account {account_id} is not ACTIVE")
        if amount <= Decimal("0"):
            raise ValueError("Deposit amount must be positive")
        product = self._product_store.get(account.product_id)
        if product and account.balance + amount > product.max_deposit:
            raise ValueError(f"Deposit would exceed maximum balance {product.max_deposit}")
        updated = dataclasses.replace(account, balance=account.balance + amount)
        self._account_store.update(updated)
        return {
            "account_id": account_id,
            "deposited": str(amount),
            "new_balance": str(updated.balance),
            "status": "DEPOSITED",
        }

    def withdraw(self, account_id: str, amount: Decimal) -> dict[str, object]:
        """Early withdrawal from fixed-term >= £50k → HITL_REQUIRED (I-27)."""
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        if account.status != AccountStatus.ACTIVE:
            raise ValueError(f"Account {account_id} is not ACTIVE")
        if amount <= Decimal("0"):
            raise ValueError("Withdrawal amount must be positive")
        if amount > account.balance:
            raise ValueError(f"Insufficient balance: {account.balance}")
        product = self._product_store.get(account.product_id)
        is_fixed = product is not None and product.account_type in _FIXED_TERM_TYPES
        if is_fixed and amount >= _EARLY_WITHDRAWAL_HITL_THRESHOLD:
            return {
                "status": "HITL_REQUIRED",
                "account_id": account_id,
                "amount": str(amount),
                "reason": "early_withdrawal_exceeds_threshold",
                "threshold": str(_EARLY_WITHDRAWAL_HITL_THRESHOLD),
            }
        updated = dataclasses.replace(account, balance=account.balance - amount)
        self._account_store.update(updated)
        return {
            "account_id": account_id,
            "withdrawn": str(amount),
            "new_balance": str(updated.balance),
            "status": "WITHDRAWN",
        }

    def get_interest_summary(self, account_id: str) -> dict[str, object]:
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        product = self._product_store.get(account.product_id)
        gross = product.gross_rate if product else Decimal("0")
        aer = product.aer if product else Decimal("0")
        daily = self._calc.calculate_daily_interest(account.balance, gross)
        tax_info = self._calc.apply_tax_withholding(account.accrued_interest)
        return {
            "account_id": account_id,
            "balance": str(account.balance),
            "accrued_interest": str(account.accrued_interest),
            "gross_rate": str(gross),
            "aer": str(aer),
            "daily_interest": str(daily),
            "tax_info": tax_info,
        }

    def get_account(self, account_id: str) -> dict[str, object]:
        account = self._account_store.get(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")
        return {
            "account_id": account.account_id,
            "customer_id": account.customer_id,
            "product_id": account.product_id,
            "balance": str(account.balance),
            "accrued_interest": str(account.accrued_interest),
            "status": account.status.value,
            "opened_at": account.opened_at.isoformat(),
            "maturity_date": account.maturity_date.isoformat() if account.maturity_date else None,
        }

    def list_accounts(self, customer_id: str) -> dict[str, object]:
        accounts = self._account_store.list_by_customer(customer_id)
        return {
            "customer_id": customer_id,
            "accounts": [
                {
                    "account_id": a.account_id,
                    "product_id": a.product_id,
                    "balance": str(a.balance),
                    "status": a.status.value,
                }
                for a in accounts
            ],
            "count": len(accounts),
        }
