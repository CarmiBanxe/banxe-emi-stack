"""
api/deps.py — FastAPI dependency injection
IL-046 | banxe-emi-stack

Provides service instances via FastAPI Depends().
In sandbox/test mode: InMemory/Stub adapters.
In production: real adapters selected via env vars.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
import os

from sqlalchemy.ext.asyncio import AsyncSession

from services.customer.customer_service import InMemoryCustomerService
from services.database import AsyncSessionLocal
from services.kyc.mock_kyc_workflow import MockKYCWorkflow
from services.payment.mock_payment_adapter import MockPaymentAdapter
from services.payment.payment_service import PaymentService
from services.ledger.midaz_adapter import MidazLedgerAdapter, StubLedgerAdapter
from services.statements.statement_service import (
    AccountStatementService,
    InMemoryTransactionRepository,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session per request — commit on success, rollback on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache(maxsize=1)
def get_customer_service() -> InMemoryCustomerService:
    return InMemoryCustomerService()


@lru_cache(maxsize=1)
def get_kyc_service() -> MockKYCWorkflow:
    return MockKYCWorkflow()


@lru_cache(maxsize=1)
def get_payment_service() -> PaymentService:
    """Payment service with ledger integration.

    PAYMENT_ADAPTER env var controls rail adapter:
      "mock"   -> MockPaymentAdapter (default, no API key needed)
      "modulr" -> ModulrPaymentAdapter (requires MODULR_API_KEY)

    LEDGER_ADAPTER env var controls ledger:
      "stub"  -> StubLedgerAdapter (default, in-memory)
      "midaz" -> MidazLedgerAdapter (requires MIDAZ_BASE_URL)
    """
    adapter_name = os.environ.get("PAYMENT_ADAPTER", "mock")
    if adapter_name == "mock":
        rail = MockPaymentAdapter()
    else:
        from services.payment.modulr_client import ModulrPaymentAdapter
        rail = ModulrPaymentAdapter()

    ledger_name = os.environ.get("LEDGER_ADAPTER", "stub")
    if ledger_name == "midaz":
        ledger = MidazLedgerAdapter()
    else:
        ledger = StubLedgerAdapter()

    return PaymentService(rail=rail, ch_client=None, ledger_port=ledger)


def get_ledger_base_url() -> str:
    """Midaz ledger base URL from env (falls back to sandbox)."""
    return os.environ.get("MIDAZ_BASE_URL", "http://localhost:8095")


@lru_cache(maxsize=1)
def get_statement_service() -> AccountStatementService:
    """Account statement service — InMemory repo (sandbox/test).
    In production: swap InMemoryTransactionRepository for ClickHouseTransactionRepository.
    """
    return AccountStatementService(repo=InMemoryTransactionRepository())
