"""Safeguarding bank account balance API client."""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Dict, List


logger = logging.getLogger(__name__)


class BankApiClient:
    """Client for safeguarding bank account balance feeds."""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self._call_log: list[dict] = []  # I-24 append-only

    async def get_account_balance(self, account_id: str) -> Decimal:
        """Get current balance for a safeguarding bank account.

        BT-015: Returns Decimal("0") until bank API integration is provisioned (P1).
        I-24: logs every call attempt for traceability.
        """
        self._call_log.append(
            {
                "method": "get_account_balance",
                "account_id": account_id,
                "queued_at": datetime.now(UTC).isoformat(),
                "provisioned": False,
            }
        )
        logger.warning("BankApiClient.get_account_balance: not provisioned (P1). account_id=%s", account_id)
        return Decimal("0")

    async def get_all_balances(self) -> List[Dict]:
        """Get balances for all safeguarding accounts.

        BT-015: Returns [] until bank API integration is provisioned (P1).
        I-24: logs every call attempt.
        """
        self._call_log.append(
            {
                "method": "get_all_balances",
                "queued_at": datetime.now(UTC).isoformat(),
                "provisioned": False,
            }
        )
        logger.warning("BankApiClient.get_all_balances: not provisioned (P1).")
        return []

    async def import_statement(self, account_id: str, statement_data: bytes) -> Dict:
        """Import bank statement for monthly reconciliation.

        BT-015: Returns {} until bank statement import is provisioned (P1).
        I-24: logs import attempt with account_id.
        """
        self._call_log.append(
            {
                "method": "import_statement",
                "account_id": account_id,
                "bytes_received": len(statement_data),
                "queued_at": datetime.now(UTC).isoformat(),
                "provisioned": False,
            }
        )
        logger.warning("BankApiClient.import_statement: not provisioned (P1). account_id=%s", account_id)
        return {}
