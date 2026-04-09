"""
api/deps.py — FastAPI dependency injection
IL-046 | banxe-emi-stack

Provides service instances via FastAPI Depends().
In sandbox/test mode: InMemory adapters.
In production: real adapters selected via env vars.
"""

from __future__ import annotations

import os
from functools import lru_cache

from services.customer.customer_service import InMemoryCustomerService
from services.kyc.mock_kyc_workflow import MockKYCWorkflow
from services.payment.mock_payment_adapter import MockPaymentAdapter


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
