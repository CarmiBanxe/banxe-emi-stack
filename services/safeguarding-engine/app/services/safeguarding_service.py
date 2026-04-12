"""Core safeguarding business logic service.

Handles safeguarding obligations, fund tracking, and compliance
with FCA CASS 15 requirements.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.safeguarding import (
    SafeguardingRequest,
    SafeguardingResponse,
    PositionResponse,
    ShortfallResponse,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    BalanceSnapshotCreate,
)
from app.services.audit_logger import AuditLogger
from app.services.breach_service import BreachService

logger = logging.getLogger(__name__)


class SafeguardingService:
    """Core safeguarding operations per CASS 15."""

    def __init__(
        self,
        db: AsyncSession,
        audit_logger: AuditLogger,
        breach_service: BreachService,
    ):
        self.db = db
        self.audit = audit_logger
        self.breach = breach_service

    async def record_obligation(self, request: SafeguardingRequest) -> SafeguardingResponse:
        """Record a new safeguarding obligation on e-money receipt."""
        logger.info(
            "Recording safeguarding obligation: %s %s",
            request.client_fund_amount,
            request.currency,
        )
        # TODO: Create obligation record, link to transaction
        # TODO: Trigger position recalculation
        # TODO: Log audit event to ClickHouse
        raise NotImplementedError("Implement in Phase 3.6")

    async def get_position(self, position_date: Optional[str] = None) -> PositionResponse:
        """Get safeguarding position for a given date."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def get_shortfall(self) -> ShortfallResponse:
        """Calculate current shortfall vs required safeguarding."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def create_account(self, data: AccountCreate) -> AccountResponse:
        """Register a new safeguarding bank account."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def update_account(self, account_id: uuid.UUID, data: AccountUpdate) -> AccountResponse:
        """Update safeguarding account metadata."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def record_balance_snapshot(self, account_id: uuid.UUID, data: BalanceSnapshotCreate) -> dict:
        """Record a balance snapshot from bank API or manual entry."""
        raise NotImplementedError("Implement in Phase 3.6")
