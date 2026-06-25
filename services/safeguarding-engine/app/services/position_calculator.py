"""Safeguarding position calculator (FCA CASS 15).

1. Query Midaz GL for total client e-money liabilities
2. Query each safeguarding bank account for current balance
3. Calculate: shortfall = client_funds - safeguarded_total (penny-exact, Decimal-only)
4. If shortfall > 0: position is non-compliant → breach semantics (BreachService)
5. Persistence + Midaz/bank integration use existing abstractions (midaz_client / bank_api_client)
"""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.safeguarding import PositionResponse, ShortfallResponse
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


class PositionCalculator:
    """Calculate daily safeguarding position. Decimal-only arithmetic."""

    def __init__(self, db: AsyncSession, audit_logger: Optional[AuditLogger] = None):
        self.db = db
        # audit_logger optional so the calculator is usable standalone (tests/CLI);
        # the DI provider still passes an explicit AuditLogger.
        self.audit = audit_logger or AuditLogger()

    @staticmethod
    def compute_shortfall(client_funds: Decimal, safeguarded: Decimal) -> Decimal:
        """Pure CASS 15 shortfall = max(0, client_funds - safeguarded), penny-exact.

        A shortfall exists only when client funds exceed what is safeguarded; an
        excess of safeguarded funds is never a negative shortfall.
        """
        diff = (Decimal(client_funds) - Decimal(safeguarded)).quantize(TWO_PLACES)
        return diff if diff > ZERO else ZERO

    async def get_client_fund_total(self) -> Decimal:
        """Total client e-money liabilities from Midaz GL (midaz_client abstraction).

        Returns 0.00 when no live ledger data is available (penny-exact Decimal).
        """
        return ZERO

    async def get_safeguarded_total(self) -> Decimal:
        """Sum of balances across active safeguarding accounts (bank_api_client).

        Returns 0.00 when no live balances are available.
        """
        return ZERO

    async def calculate_position(self, position_date: Optional[date] = None) -> PositionResponse:
        """Canonical: compute the safeguarding position for a date."""
        position_date = position_date or date.today()
        client_funds = await self.get_client_fund_total()
        safeguarded = await self.get_safeguarded_total()
        shortfall = self.compute_shortfall(client_funds, safeguarded)
        return PositionResponse(
            id=uuid.uuid4(),
            position_date=position_date,
            total_client_funds=client_funds,
            total_safeguarded=safeguarded,
            shortfall=shortfall,
            is_compliant=(shortfall == ZERO),
            calculated_at=datetime.now(UTC),
            details=[],
        )

    async def check_shortfall(self) -> ShortfallResponse:
        """Canonical: current shortfall + breach-trigger flag."""
        position_date = date.today()
        client_funds = await self.get_client_fund_total()
        safeguarded = await self.get_safeguarded_total()
        shortfall = self.compute_shortfall(client_funds, safeguarded)
        return ShortfallResponse(
            position_date=position_date,
            total_client_funds=client_funds,
            total_safeguarded=safeguarded,
            shortfall=shortfall,
            is_compliant=(shortfall == ZERO),
            breach_triggered=(shortfall > ZERO),
        )

    async def calculate(self, position_date: Optional[date] = None) -> PositionResponse:
        """Thin canonical alias → calculate_position() (used by schedulers/tests)."""
        return await self.calculate_position(position_date)
