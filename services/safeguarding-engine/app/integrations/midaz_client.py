"""Midaz GL ledger client for client fund balances."""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Dict

import httpx

logger = logging.getLogger(__name__)


class MidazClient:
    """Client for Midaz General Ledger API."""

    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url
        self.api_key = api_key
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self._call_log: list[dict] = []  # I-24 append-only

    async def get_client_fund_total(self, currency: str = "GBP") -> Decimal:
        """Get total client e-money liabilities from Midaz GL.

        BT-015: Returns Decimal("0") until Midaz GL integration is provisioned (P1).
        I-24: logs every call.
        """
        self._call_log.append(
            {
                "method": "get_client_fund_total",
                "currency": currency,
                "queued_at": datetime.now(UTC).isoformat(),
                "provisioned": False,
            }
        )
        logger.warning("MidazClient.get_client_fund_total: not provisioned (P1). currency=%s", currency)
        return Decimal("0")

    async def get_ledger_balances(self) -> Dict[str, Decimal]:
        """Get all safeguarding-relevant ledger balances.

        BT-015: Returns {} until Midaz GL integration is provisioned (P1).
        I-24: logs every call.
        """
        self._call_log.append(
            {
                "method": "get_ledger_balances",
                "queued_at": datetime.now(UTC).isoformat(),
                "provisioned": False,
            }
        )
        logger.warning("MidazClient.get_ledger_balances: not provisioned (P1).")
        return {}

    async def close(self) -> None:
        await self._client.aclose()
