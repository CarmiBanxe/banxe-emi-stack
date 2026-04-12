"""Midaz GL ledger client for client fund balances."""
import logging
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

    async def get_client_fund_total(self, currency: str = "GBP") -> Decimal:
        """Get total client e-money liabilities from Midaz GL."""
        raise NotImplementedError("Implement Midaz GL integration")

    async def get_ledger_balances(self) -> Dict[str, Decimal]:
        """Get all safeguarding-relevant ledger balances."""
        raise NotImplementedError("Implement Midaz GL integration")

    async def close(self) -> None:
        await self._client.aclose()
