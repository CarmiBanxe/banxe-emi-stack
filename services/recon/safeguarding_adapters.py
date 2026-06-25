"""Production port adapters for SafeguardingAgent (CASS 15 daily cron).

Bridges existing infrastructure (MidazLedgerAdapter, StatementFetcher) to the
three SafeguardingAgent port protocols, so cron_daily_recon.py can assemble a
production SafeguardingAgentPorts without changing the agent or core adapters.

Ports implemented:
  LedgerBalancePort  → MidazClientFundsPort  (client-fund total from Midaz CBS)
  BankStatementPort  → StatementBankPort     (safeguarding closing balance via CAMT.053)
  StreakCounterPort  → ZeroStreakCounter      (stateless stub; ClickHouse streak is P1)

All amounts: Decimal only (I-01). No float.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Midaz account constants (from reconciliation_engine.py) ───────────────────
_ORG_ID = "019d6301-32d7-70a1-bc77-0a05379ee510"
_LEDGER_ID = "019d632f-519e-7865-8a30-3c33991bba9c"
_CLIENT_FUNDS_ACCOUNT_ID = "019d6332-da7f-752f-b9fd-fa1c6fc777ec"


class MidazClientFundsPort:
    """LedgerBalancePort — total client-fund balance from Midaz CBS.

    Wraps MidazLedgerAdapter using the CASS 15 client-funds liability account.
    Env overrides: MIDAZ_ORG_ID, MIDAZ_LEDGER_ID, MIDAZ_CLIENT_FUNDS_ACCOUNT_ID.
    """

    def __init__(
        self,
        org_id: str | None = None,
        ledger_id: str | None = None,
        account_id: str | None = None,
    ) -> None:
        self._org_id = org_id or os.environ.get("MIDAZ_ORG_ID", _ORG_ID)
        self._ledger_id = ledger_id or os.environ.get("MIDAZ_LEDGER_ID", _LEDGER_ID)
        self._account_id = account_id or os.environ.get(
            "MIDAZ_CLIENT_FUNDS_ACCOUNT_ID", _CLIENT_FUNDS_ACCOUNT_ID
        )
        # Lazy import: avoids pulling httpx at module import time
        from services.ledger.midaz_adapter import MidazLedgerAdapter  # noqa: PLC0415

        self._midaz = MidazLedgerAdapter()

    def get_client_funds_gbp(self, as_of: date) -> Decimal:  # noqa: ARG002
        balance = self._midaz.get_balance(self._org_id, self._ledger_id, self._account_id)
        logger.debug(
            "MidazClientFundsPort: org=%s ledger=%s account=%s balance=%s",
            self._org_id,
            self._ledger_id,
            self._account_id,
            balance,
        )
        return balance


class StatementBankPort:
    """BankStatementPort — safeguarding closing balance via StatementFetcher (CAMT.053/CSV).

    Fetches all GBP balances for the date and sums them. Returns None (PENDING)
    if StatementFetcher returns no GBP rows (statement not yet received).
    Env override: STATEMENT_DIR.
    """

    def __init__(self, statement_dir: str | None = None) -> None:
        from services.recon.statement_fetcher import StatementFetcher  # noqa: PLC0415

        self._fetcher = StatementFetcher(
            statement_dir=statement_dir or os.environ.get("STATEMENT_DIR")
        )

    def get_closing_balance_gbp(self, statement_date: date) -> Decimal | None:
        balances = self._fetcher.fetch(statement_date)
        gbp = [b for b in balances if b.currency == "GBP"]
        if not gbp:
            logger.info("StatementBankPort: no GBP statement for %s → PENDING", statement_date)
            return None
        total = sum((b.balance for b in gbp), Decimal("0"))
        logger.debug("StatementBankPort: %d GBP account(s) total=%s", len(gbp), total)
        return total


class ZeroStreakCounter:
    """StreakCounterPort — stateless stub always returning streak=0.

    Used until a ClickHouse-backed streak counter is implemented (P1).
    Streak-based breach escalation is disabled; CRITICAL shortfall detection
    still works via BreachDetector (streak-independent path).
    """

    def get_streak(self, as_of: date) -> int:  # noqa: ARG002
        return 0

    def reset_streak(self, as_of: date) -> None:  # noqa: ARG002
        pass
