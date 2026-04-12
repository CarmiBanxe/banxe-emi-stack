"""Safeguarding position calculator.

1. Query Midaz GL for total client e-money liabilities
2. Query each safeguarding bank account for current balance
3. Calculate: shortfall = client_funds - safeguarded_total
4. If shortfall > 0: trigger CRITICAL breach alert
5. Store position in PostgreSQL + audit event in ClickHouse
6. Run daily via Celery beat at 06:00 UTC
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SafeguardingPosition, PositionDetail, SafeguardingAccount
from app.schemas.safeguarding import PositionResponse, ShortfallResponse
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class PositionCalculator:
    """Calculate daily safeguarding position."""

    def __init__(self, db: AsyncSession, audit_logger: AuditLogger):
        self.db = db
        self.audit = audit_logger

    async def calculate_position(
        self, position_date: date = None
    ) -> PositionResponse:
        """Calculate safeguarding position for given date.

        Steps:
        1. Get total client e-money liabilities from Midaz GL
        2. Get balances from all safeguarding bank accounts
        3. Calculate shortfall
        4. Store position record
        5. Log audit event
        """
        if position_date is None:
            position_date = date.today()

        logger.info("Calculating safeguarding position for %s", position_date)
        # TODO: Implement position calculation
        raise NotImplementedError("Implement in Phase 3.6")

    async def get_client_fund_total(self) -> Decimal:
        """Query Midaz GL for total client e-money liabilities."""
        # TODO: Call Midaz client
        raise NotImplementedError("Implement in Phase 3.6")

    async def get_safeguarded_total(self) -> Decimal:
        """Sum balances across all active safeguarding accounts."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def check_shortfall(self) -> ShortfallResponse:
        """Calculate current shortfall and trigger breach if needed."""
        raise NotImplementedError("Implement in Phase 3.6")
