"""Safeguarding bank account balance API client."""
import logging
from decimal import Decimal
from typing import Dict, List

import httpx

logger = logging.getLogger(__name__)


class BankApiClient:
    """Client for safeguarding bank account balance feeds."""

    def __init__(self, config: Dict = None):
        self.config = config or {}

    async def get_account_balance(self, account_id: str) -> Decimal:
        """Get current balance for a safeguarding bank account."""
        raise NotImplementedError("Implement bank API integration")

    async def get_all_balances(self) -> List[Dict]:
        """Get balances for all safeguarding accounts."""
        raise NotImplementedError("Implement bank API integration")

    async def import_statement(self, account_id: str, statement_data: bytes) -> Dict:
        """Import bank statement for monthly reconciliation."""
        raise NotImplementedError("Implement bank statement import")
