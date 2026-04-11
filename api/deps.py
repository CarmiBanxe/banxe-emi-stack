"""
api/deps.py — FastAPI dependency injection
IL-046 | banxe-emi-stack

Provides service instances via FastAPI Depends().
In sandbox/test mode: InMemory adapters.
In production: real adapters selected via env vars.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from services.customer.customer_service import InMemoryCustomerService
from services.database import AsyncSessionLocal
from services.kyc.mock_kyc_workflow import MockKYCWorkflow
from services.payment.mock_payment_adapter import MockPaymentAdapter
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
def get_payment_service() -> MockPaymentAdapter:
    return MockPaymentAdapter()


def get_ledger_base_url() -> str:
    """Midaz ledger base URL from env (falls back to sandbox)."""
    return os.environ.get("MIDAZ_BASE_URL", "http://localhost:8095")


@lru_cache(maxsize=1)
def get_statement_service() -> AccountStatementService:
    """Account statement service — InMemory repo (sandbox/test).
    In production: swap InMemoryTransactionRepository for ClickHouseTransactionRepository.
    """
    return AccountStatementService(repo=InMemoryTransactionRepository())
