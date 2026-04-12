"""Reconciliation service for daily and monthly CASS 15 reconciliation.

Daily: Internal ledger vs safeguarding account balances (tolerance GBP 0.01)
Monthly: External bank statements vs internal records
"""

import logging
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.reconciliation import (
    DailyReconRequest,
    MonthlyReconRequest,
    ReconciliationResponse,
    ReconciliationDetailResponse,
)
from app.services.audit_logger import AuditLogger
from app.services.breach_service import BreachService

logger = logging.getLogger(__name__)

RECON_TOLERANCE = Decimal("0.01")  # Penny-exact matching


class ReconciliationService:
    """Daily + monthly reconciliation per CASS 15."""

    def __init__(
        self,
        db: AsyncSession,
        audit_logger: AuditLogger,
        breach_service: BreachService,
    ):
        self.db = db
        self.audit = audit_logger
        self.breach = breach_service

    async def run_daily_reconciliation(self, request: DailyReconRequest) -> ReconciliationResponse:
        """Run daily internal reconciliation.

        1. Compare Midaz ledger client fund total vs safeguarding balances
        2. Any difference > GBP 0.01 = reconciliation break
        3. Breaks auto-escalate via Telegram to MLRO + CEO
        4. Unresolved breaks after 24h trigger FCA breach report
        """
        logger.info("Running daily reconciliation for %s", request.recon_date)
        raise NotImplementedError("Implement in Phase 3.6")

    async def run_monthly_reconciliation(self, request: MonthlyReconRequest) -> ReconciliationResponse:
        """Run monthly external reconciliation.

        1. Match bank statements against internal records
        2. Produce FCA-producible reconciliation report
        3. Flag unmatched items for manual review
        4. Store audit trail in ClickHouse (7-year TTL)
        """
        logger.info("Running monthly reconciliation for %s/%s", request.month, request.year)
        raise NotImplementedError("Implement in Phase 3.6")

    async def get_history(
        self,
        recon_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[ReconciliationResponse]:
        """List reconciliation results with optional type filter."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def get_detail(self, recon_id: str) -> ReconciliationDetailResponse:
        """Get detailed reconciliation report with break items."""
        raise NotImplementedError("Implement in Phase 3.6")
