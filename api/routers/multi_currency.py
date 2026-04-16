"""
api/routers/multi_currency.py — Multi-Currency Ledger Enhancement REST API.

Phase 22 | IL-MCL-01 | banxe-emi-stack

Routes use /v1/mc-accounts/* prefix to avoid conflicts with existing
/v1/accounts/{account_id}/statement (statements.py).

Endpoints:
  POST /v1/mc-accounts/create                         — create multi-currency account
  GET  /v1/mc-accounts/{account_id}/balances          — all currency balances
  GET  /v1/mc-accounts/{account_id}/currencies        — list currencies in account
  POST /v1/mc-accounts/{account_id}/convert           — convert currency
  POST /v1/mc-accounts/{account_id}/currency-report   — consolidated balance report
  GET  /v1/nostro                                     — list all nostro accounts
  GET  /v1/nostro/{nostro_id}                         — get single nostro account
  POST /v1/nostro/{nostro_id}/reconcile               — reconcile nostro

FCA compliance:
  - Amounts always as strings (I-05 — never float)
  - Decimal only internally (I-01)
  - Audit trail on all mutations (I-24)
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.multi_currency.account_manager import AccountManager
from services.multi_currency.balance_engine import BalanceEngine
from services.multi_currency.conversion_tracker import ConversionTracker
from services.multi_currency.currency_router import CurrencyRouter
from services.multi_currency.models import (
    InMemoryAccountStore,
    InMemoryConversionStore,
    InMemoryLedgerEntryStore,
    InMemoryMCAudit,
    InMemoryNostroStore,
)
from services.multi_currency.multicurrency_agent import MultiCurrencyAgent
from services.multi_currency.nostro_reconciler import NostroReconciler

router = APIRouter(tags=["multi-currency"])


# ── Agent factory ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> MultiCurrencyAgent:
    """Build and cache the MultiCurrencyAgent with InMemory stubs."""
    account_store = InMemoryAccountStore()
    ledger_store = InMemoryLedgerEntryStore()
    conversion_store = InMemoryConversionStore()
    nostro_store = InMemoryNostroStore()
    audit = InMemoryMCAudit()

    account_manager = AccountManager(account_store, ledger_store, audit)
    balance_engine = BalanceEngine(account_store, ledger_store)
    nostro_reconciler = NostroReconciler(nostro_store, audit)
    currency_router = CurrencyRouter()
    conversion_tracker = ConversionTracker(conversion_store, ledger_store, audit)

    return MultiCurrencyAgent(
        account_manager=account_manager,
        balance_engine=balance_engine,
        nostro_reconciler=nostro_reconciler,
        currency_router=currency_router,
        conversion_tracker=conversion_tracker,
    )


# ── Pydantic request models ────────────────────────────────────────────────────


class CreateAccountRequest(BaseModel):
    entity_id: str
    base_currency: str
    currencies: list[str]


class ConvertRequest(BaseModel):
    from_currency: str
    to_currency: str
    amount: str
    rate: str


class ReconcileRequest(BaseModel):
    their_balance: str


class CurrencyReportRequest(BaseModel):
    rates: dict[str, str]


# ── Endpoints: mc-accounts ─────────────────────────────────────────────────────


@router.post(
    "/mc-accounts/create",
    summary="Create multi-currency account",
)
async def create_multi_currency_account(body: CreateAccountRequest) -> dict:
    """Create a new multi-currency account for an entity.

    - Validates all currencies are supported (GBP, EUR, USD, CHF, PLN, CZK, SEK, NOK, DKK, HUF).
    - Hard limit: max 10 currencies per account.
    - Returns account_id, entity_id, base_currency, currencies, created_at.
    """
    try:
        return await _get_agent().create_multi_currency_account(
            body.entity_id, body.base_currency, body.currencies
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/mc-accounts/{account_id}/balances",
    summary="Get all currency balances",
)
async def get_account_balances(account_id: str) -> dict:
    """Return all currency balances as {currency: str(amount)} (I-05)."""
    balances = await _get_agent().get_account_balances(account_id)
    if not balances:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return balances


@router.get(
    "/mc-accounts/{account_id}/currencies",
    summary="List currencies in account",
)
async def list_account_currencies(account_id: str) -> dict:
    """Return list of currency codes held in a multi-currency account."""
    agent = _get_agent()
    account = await agent._account_manager.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return {"account_id": account_id, "currencies": [b.currency for b in account.balances]}


@router.post(
    "/mc-accounts/{account_id}/convert",
    summary="Convert between currencies",
)
async def convert_currency(account_id: str, body: ConvertRequest) -> dict:
    """Debit from_currency, credit to_currency, record conversion at given rate.

    - amount and rate are Decimal strings (I-05).
    - Fee = 0.2% of from_amount.
    - Returns conversion record with fee, status, timestamps.
    """
    try:
        return await _get_agent().convert_currency(
            account_id,
            body.from_currency,
            body.to_currency,
            body.amount,
            body.rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/mc-accounts/{account_id}/currency-report",
    summary="Consolidated currency balance report",
)
async def get_currency_report(account_id: str, body: CurrencyReportRequest) -> dict:
    """Return consolidated balance in base currency + per-currency breakdown.

    - rates: dict of {currency: rate-to-base} as strings.
    - consolidated_balance: sum of all balances converted to base_currency.
    """
    try:
        return await _get_agent().get_currency_report(account_id, body.rates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Endpoints: nostro ──────────────────────────────────────────────────────────


@router.get(
    "/nostro",
    summary="List all nostro accounts",
)
async def list_nostros() -> dict:
    """Return all nostro/vostro/loro correspondent banking accounts."""
    agent = _get_agent()
    nostros = await agent._nostro_reconciler.list_nostros()
    return {
        "nostros": [
            {
                "account_id": n.account_id,
                "bank_name": n.bank_name,
                "currency": n.currency,
                "our_balance": str(n.our_balance),
                "their_balance": str(n.their_balance),
                "account_type": n.account_type.value,
                "last_reconciled": (n.last_reconciled.isoformat() if n.last_reconciled else None),
            }
            for n in nostros
        ]
    }


@router.get(
    "/nostro/{nostro_id}",
    summary="Get single nostro account",
)
async def get_nostro(nostro_id: str) -> dict:
    """Return details for a single nostro account."""
    agent = _get_agent()
    nostro = await agent._nostro_reconciler.get_nostro(nostro_id)
    if nostro is None:
        raise HTTPException(status_code=404, detail=f"Nostro {nostro_id} not found")
    return {
        "account_id": nostro.account_id,
        "bank_name": nostro.bank_name,
        "currency": nostro.currency,
        "our_balance": str(nostro.our_balance),
        "their_balance": str(nostro.their_balance),
        "account_type": nostro.account_type.value,
        "last_reconciled": (nostro.last_reconciled.isoformat() if nostro.last_reconciled else None),
    }


@router.post(
    "/nostro/{nostro_id}/reconcile",
    summary="Reconcile nostro account",
)
async def reconcile_nostro(nostro_id: str, body: ReconcileRequest) -> dict:
    """Compare our nostro balance vs correspondent bank's reported balance.

    - Tolerance: £1.00 (broader than internal 1p due to settlement timing).
    - MATCHED if abs(variance) <= 1.00, else DISCREPANCY.
    - their_balance is a Decimal string (I-05).
    """
    try:
        return await _get_agent().reconcile_nostro(nostro_id, body.their_balance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
