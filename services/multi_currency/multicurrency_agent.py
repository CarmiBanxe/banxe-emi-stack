"""
services/multi_currency/multicurrency_agent.py — Orchestrator for multi-currency operations.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Coordinates AccountManager, BalanceEngine, NostroReconciler, CurrencyRouter,
and ConversionTracker into high-level use-case flows.

Invariants:
  - I-01: rates/amounts always Decimal internally.
  - I-05: amounts returned as strings to API layer.
"""

from __future__ import annotations

from decimal import Decimal

from services.multi_currency.account_manager import AccountManager
from services.multi_currency.balance_engine import BalanceEngine
from services.multi_currency.conversion_tracker import ConversionTracker
from services.multi_currency.currency_router import CurrencyRouter
from services.multi_currency.nostro_reconciler import NostroReconciler


class MultiCurrencyAgent:
    """High-level orchestrator for multi-currency EMI operations."""

    def __init__(
        self,
        account_manager: AccountManager,
        balance_engine: BalanceEngine,
        nostro_reconciler: NostroReconciler,
        currency_router: CurrencyRouter,
        conversion_tracker: ConversionTracker,
    ) -> None:
        self._account_manager = account_manager
        self._balance_engine = balance_engine
        self._nostro_reconciler = nostro_reconciler
        self._currency_router = currency_router
        self._conversion_tracker = conversion_tracker

    async def create_multi_currency_account(
        self,
        entity_id: str,
        base_currency: str,
        currencies: list[str],
    ) -> dict:
        """Create a new multi-currency account and return serialised dict."""
        account = await self._account_manager.create_account(entity_id, base_currency, currencies)
        return {
            "account_id": account.account_id,
            "entity_id": account.entity_id,
            "base_currency": account.base_currency,
            "currencies": [b.currency for b in account.balances],
            "created_at": account.created_at.isoformat(),
        }

    async def get_account_balances(self, account_id: str) -> dict:
        """Return all balances for an account as {currency: str(amount)}."""
        balances = await self._balance_engine.get_all_balances(account_id)
        return {b.currency: str(b.amount) for b in balances}

    async def convert_currency(
        self,
        account_id: str,
        from_currency: str,
        to_currency: str,
        amount: str,
        rate: str,
    ) -> dict:
        """Debit from_currency → record conversion → credit to_currency.

        Args:
            amount: Decimal string — amount to convert in from_currency.
            rate: Decimal string — FX rate (from_currency per to_currency unit).

        Returns serialised ConversionRecord dict.
        """
        from_amount = Decimal(amount)
        fx_rate = Decimal(rate)
        to_amount = from_amount * fx_rate

        await self._balance_engine.debit(
            account_id,
            from_currency,
            from_amount,
            f"FX debit {from_currency} → {to_currency}",
        )
        record = await self._conversion_tracker.record_conversion(
            account_id,
            from_currency,
            to_currency,
            from_amount,
            to_amount,
            fx_rate,
        )
        await self._balance_engine.credit(
            account_id,
            to_currency,
            to_amount,
            f"FX credit {from_currency} → {to_currency}",
        )
        return {
            "conversion_id": record.conversion_id,
            "account_id": record.account_id,
            "from_currency": record.from_currency,
            "to_currency": record.to_currency,
            "from_amount": str(record.from_amount),
            "to_amount": str(record.to_amount),
            "rate": str(record.rate),
            "fee": str(record.fee),
            "status": record.status.value,
            "created_at": record.created_at.isoformat(),
        }

    async def reconcile_nostro(
        self,
        nostro_id: str,
        their_balance: str,
    ) -> dict:
        """Run nostro reconciliation and return serialised ReconciliationResult."""
        result = await self._nostro_reconciler.reconcile(nostro_id, Decimal(their_balance))
        return {
            "nostro_id": result.nostro_id,
            "our_balance": str(result.our_balance),
            "their_balance": str(result.their_balance),
            "variance": str(result.variance),
            "status": result.status.value,
            "reconciled_at": result.reconciled_at.isoformat(),
        }

    async def get_currency_report(
        self,
        account_id: str,
        rates: dict[str, str],
    ) -> dict:
        """Return consolidated balance + per-currency breakdown.

        Args:
            rates: dict mapping currency → rate-to-base as strings; converted to Decimal.

        Returns:
            {
                "account_id": str,
                "base_currency": str,
                "consolidated_balance": str,
                "breakdown": {currency: str(amount)},
            }
        """
        decimal_rates = {k: Decimal(v) for k, v in rates.items()}
        consolidated = await self._balance_engine.get_consolidated_balance(
            account_id, decimal_rates
        )
        balances = await self._balance_engine.get_all_balances(account_id)
        account = await self._account_manager.get_account(account_id)
        base_currency = account.base_currency if account else "GBP"
        return {
            "account_id": account_id,
            "base_currency": base_currency,
            "consolidated_balance": str(consolidated),
            "breakdown": {b.currency: str(b.amount) for b in balances},
        }
