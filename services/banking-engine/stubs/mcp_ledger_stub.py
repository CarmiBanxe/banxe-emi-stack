# SANDBOX STUB — no real MCP/ledger/CRM endpoints.
# Returns synthetic test data only. No network calls.
"""
MCP ledger + CRM stub adapter for Banking Engine B-2 sandbox.

Mirrors the interface of the real McpLedgerClient so the graph
can hot-swap to the real adapter in production without changing callers.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid

_STUB_ACCOUNT_ID = "TEST-ACC-0001"
_STUB_CUSTOMER_ID = "TEST-CUST-0001"


class McpLedgerStub:
    """Mock MCP tool adapter returning deterministic synthetic ledger data."""

    # ---------- ledger ------------------------------------------------

    def get_balance(self, account_id: str = _STUB_ACCOUNT_ID) -> dict[str, Any]:
        return {
            "account_id": account_id,
            "balance": str(Decimal("9750.00")),
            "currency": "GBP",
            "as_of": datetime.utcnow().isoformat() + "Z",
            "is_test_data": True,
        }

    def list_transactions(
        self,
        account_id: str = _STUB_ACCOUNT_ID,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return [
            {
                "tx_id": f"TEST-TX-{uuid.uuid4().hex[:8].upper()}",
                "account_id": account_id,
                "amount": str(Decimal("500.00")),
                "currency": "GBP",
                "direction": "credit",
                "narrative": "TEST INBOUND TRANSFER",
                "booked_at": datetime.utcnow().isoformat() + "Z",
                "is_test_data": True,
            },
            {
                "tx_id": f"TEST-TX-{uuid.uuid4().hex[:8].upper()}",
                "account_id": account_id,
                "amount": str(Decimal("750.00")),
                "currency": "GBP",
                "direction": "debit",
                "narrative": "TEST OUTBOUND PAYMENT",
                "booked_at": datetime.utcnow().isoformat() + "Z",
                "is_test_data": True,
            },
        ][:limit]

    def create_transaction(
        self,
        account_id: str,
        amount: Decimal,
        currency: str,
        direction: str,
        narrative: str,
    ) -> dict[str, Any]:
        return {
            "tx_id": f"TEST-TX-{uuid.uuid4().hex[:8].upper()}",
            "account_id": account_id,
            "amount": str(amount),
            "currency": currency,
            "direction": direction,
            "narrative": narrative,
            "status": "posted",
            "booked_at": datetime.utcnow().isoformat() + "Z",
            "is_test_data": True,
        }

    # ---------- CRM ---------------------------------------------------

    def get_customer(self, customer_id: str = _STUB_CUSTOMER_ID) -> dict[str, Any]:
        return {
            "customer_id": customer_id,
            "name": "Test Customer (Sandbox)",
            "kyc_status": "approved",
            "risk_tier": "low",
            "accounts": [_STUB_ACCOUNT_ID],
            "is_test_data": True,
        }
