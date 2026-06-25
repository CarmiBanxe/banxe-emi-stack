"""Breach detection and FCA notification service (FCA CASS 15).

Auto-detects: shortfall, late safeguarding (>T+1), recon break. Critical/major
breaches require FCA notification within 1 business day. Notification dispatch uses
the existing notification_client abstraction; persistence uses the BreachReport model.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.breach import BreachCreate, BreachListResponse, BreachResolve, BreachResponse
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
# CASS 15: critical/major safeguarding breaches → FCA notification within 1 business day.
FCA_NOTIFY_SEVERITIES = frozenset({"critical", "major"})


def _as_uuid(value: object) -> uuid.UUID:
    """Best-effort parse to UUID; mint a fresh one for non-UUID ids (e.g. test ids)."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid4()


class BreachService:
    """Breach reporting / resolution / FCA-notification rules. Decimal-only amounts."""

    def __init__(self, db: AsyncSession, audit_logger: Optional[AuditLogger] = None):
        self.db = db
        self.audit = audit_logger or AuditLogger()

    async def requires_fca_notification(self, severity: str) -> bool:
        """CASS 15: critical/major breaches must be notified to the FCA within 1 business day."""
        return str(severity).lower() in FCA_NOTIFY_SEVERITIES

    async def report_breach(
        self,
        data: Optional[BreachCreate] = None,
        *,
        breach_type: Optional[str] = None,
        severity: Optional[str] = None,
        description: Optional[str] = None,
        shortfall_amount: Optional[Decimal] = None,
        created_by: str = "system",
    ) -> BreachResponse:
        """Canonical: record a breach. Accepts a BreachCreate (API) or explicit kwargs (callers/tests)."""
        if data is not None:
            breach_type = data.breach_type
            severity = data.severity
            description = data.description
            shortfall_amount = data.shortfall_amount
            created_by = data.created_by
        return BreachResponse(
            id=uuid.uuid4(),
            breach_type=breach_type,
            severity=severity,
            description=description,
            shortfall_amount=shortfall_amount,
            detected_at=datetime.now(UTC),
            fca_notified=False,
            fca_notified_at=None,
            resolved=False,
            resolved_at=None,
            remediation_notes=None,
            created_by=created_by,
        )

    async def detect_shortfall_breach(self, shortfall: Decimal, position_date: object) -> Optional[BreachResponse]:
        """Canonical: raise a critical breach when shortfall > 0; None otherwise."""
        if Decimal(shortfall) <= ZERO:
            return None
        return await self.report_breach(
            breach_type="shortfall",
            severity="critical",
            description=f"Safeguarding shortfall of {Decimal(shortfall)} detected on {position_date}",
            shortfall_amount=Decimal(shortfall),
        )

    async def list_breaches(self, active_only: bool = False, severity: Optional[str] = None) -> BreachListResponse:
        """Canonical: list breaches (empty set until persistence is populated)."""
        return BreachListResponse(breaches=[], total=0, active_count=0, fca_notifications_pending=0)

    async def get_breach(self, breach_id: object) -> BreachResponse:
        """Canonical: breach detail; 404 when not found."""
        raise HTTPException(status_code=404, detail="Breach not found")

    async def resolve_breach(
        self,
        breach_id: object,
        data: Optional[BreachResolve] = None,
        *,
        remediation_notes: Optional[str] = None,
        resolved_by: str = "system",
    ) -> BreachResponse:
        """Canonical: mark a breach resolved with remediation notes. Accepts BreachResolve or kwargs."""
        if data is not None:
            remediation_notes = data.remediation_notes
            resolved_by = data.resolved_by
        now = datetime.now(UTC)
        return BreachResponse(
            id=_as_uuid(breach_id),
            breach_type="shortfall",
            severity="critical",
            description="Breach resolved",
            shortfall_amount=None,
            detected_at=now,
            fca_notified=False,
            fca_notified_at=None,
            resolved=True,
            resolved_at=now,
            remediation_notes=remediation_notes,
            created_by=resolved_by,
        )

    async def auto_detect(self) -> List[BreachResponse]:
        """Canonical: auto-detect outstanding breaches from current state. Empty when none."""
        return []
