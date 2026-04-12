"""Breach detection and FCA notification service.

Auto-detects: shortfall, late safeguarding (>T+1), recon break >24h.
Severity: critical (shortfall), major (timing), minor (recon break).
FCA notification within 1 business day for critical/major.
Chain: Telegram -> Email -> n8n workflow -> FCA Gabriel upload.
"""

import logging
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BreachReport
from app.schemas.breach import (
    BreachCreate,
    BreachResponse,
    BreachResolve,
    BreachListResponse,
)
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class BreachService:
    """Breach detection, reporting, and FCA notification."""

    def __init__(self, db: AsyncSession, audit_logger: AuditLogger):
        self.db = db
        self.audit = audit_logger

    async def detect_shortfall_breach(self, shortfall: Decimal, position_date: str) -> Optional[BreachResponse]:
        """Auto-detect shortfall breach (CRITICAL severity)."""
        if shortfall > Decimal("0"):
            logger.critical(
                "SAFEGUARDING SHORTFALL DETECTED: GBP %s on %s",
                shortfall,
                position_date,
            )
            # TODO: Create breach, notify FCA chain
        raise NotImplementedError("Implement in Phase 3.6")

    async def report_breach(self, data: BreachCreate) -> BreachResponse:
        """Manually report a safeguarding breach."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def list_breaches(self, active_only: bool = False, severity: Optional[str] = None) -> BreachListResponse:
        """List breaches with optional filters."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def get_breach(self, breach_id: uuid.UUID) -> BreachResponse:
        """Get breach detail with remediation timeline."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def resolve_breach(self, breach_id: uuid.UUID, data: BreachResolve) -> BreachResponse:
        """Mark breach as resolved."""
        raise NotImplementedError("Implement in Phase 3.6")

    async def _notify_fca_chain(self, breach: BreachReport) -> None:
        """Notification chain: Telegram -> Email -> n8n -> FCA Gabriel."""
        # TODO: Implement notification chain
        raise NotImplementedError("Implement in Phase 3.6")
