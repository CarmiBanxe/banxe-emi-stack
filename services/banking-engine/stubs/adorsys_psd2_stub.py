# SANDBOX STUB — no real Adorsys/bank connection.
# Returns synthetic CAMT.053-shaped test data only.
# DO NOT wire to any live PSD2/XS2A endpoint or real credentials.
"""
Adorsys PSD2 / XS2A stub for Banking Engine B-2 sandbox.

Returns a fake CAMT.053 bank statement with clearly-labelled TEST data.
No real IBAN, no real credentials, no live network calls.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import os
from typing import Any
import uuid

_STUB_IBAN = "TEST00000000000000"  # synthetic; never a real IBAN
_STUB_BIC = "TESTBIC0XXX"
_STUB_CURRENCY = "GBP"


def _fake_entry(
    amount: Decimal,
    credit_debit: str,
    narrative: str,
) -> dict[str, Any]:
    return {
        "entry_reference": f"TEST-{uuid.uuid4().hex[:8].upper()}",
        "amount": str(amount),
        "currency": _STUB_CURRENCY,
        "credit_debit_indicator": credit_debit,  # "CRDT" | "DBIT"
        "booking_date": date.today().isoformat(),
        "value_date": date.today().isoformat(),
        "remittance_info": narrative,
        "is_test_data": True,
    }


class AdorsysPsd2Stub:
    """
    Mock PSD2/XS2A adapter.

    Implements the same interface as the future real AdorsysPsd2Client
    so the graph can swap in the real client without changing callers.
    """

    def __init__(self) -> None:
        # api_key intentionally unused in stub; real client reads from env
        self._api_key: str = os.getenv("ADORSYS_API_KEY", "STUB_KEY_NOT_REAL")

    def get_camt053_statement(
        self,
        account_id: str = _STUB_IBAN,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> dict[str, Any]:
        """Return a synthetic CAMT.053-shaped dict (sandbox only)."""
        from_date = from_date or date.today()
        to_date = to_date or date.today()

        return {
            "document_type": "CAMT.053",
            "schema_version": "pain.002.003.03",
            "is_test_data": True,
            "group_header": {
                "message_id": f"TEST-MSG-{uuid.uuid4().hex[:12].upper()}",
                "creation_date_time": datetime.utcnow().isoformat() + "Z",
            },
            "statement": {
                "identification": f"STMT-{uuid.uuid4().hex[:8].upper()}",
                "electronic_sequence_number": 1,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "account": {
                    "iban": _STUB_IBAN,
                    "bic": _STUB_BIC,
                    "currency": _STUB_CURRENCY,
                    "name": "TEST ACCOUNT — SANDBOX ONLY",
                },
                "opening_balance": {
                    "type": "OPBD",
                    "amount": str(Decimal("10000.00")),
                    "currency": _STUB_CURRENCY,
                    "credit_debit_indicator": "CRDT",
                    "date": from_date.isoformat(),
                },
                "closing_balance": {
                    "type": "CLBD",
                    "amount": str(Decimal("9750.00")),
                    "currency": _STUB_CURRENCY,
                    "credit_debit_indicator": "CRDT",
                    "date": to_date.isoformat(),
                },
                "entries": [
                    _fake_entry(Decimal("500.00"), "CRDT", "TEST INBOUND TRANSFER"),
                    _fake_entry(Decimal("750.00"), "DBIT", "TEST OUTBOUND PAYMENT"),
                ],
            },
        }
