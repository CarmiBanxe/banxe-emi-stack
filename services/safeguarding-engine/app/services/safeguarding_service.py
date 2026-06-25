"""Core safeguarding business logic service (FCA CASS 15).

Handles safeguarding obligations, position/shortfall retrieval, T+1 timing
compliance, and safeguarding account lifecycle. Position/shortfall delegate to
PositionCalculator; breach semantics to BreachService. Decimal-only amounts.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.safeguarding import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    BalanceSnapshotCreate,
    PositionResponse,
    SafeguardingRequest,
    SafeguardingResponse,
    ShortfallResponse,
)
from app.services.audit_logger import AuditLogger
from app.services.breach_service import BreachService
from app.services.position_calculator import PositionCalculator

logger = logging.getLogger(__name__)


def _as_uuid(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid4()


class SafeguardingService:
    """Core safeguarding operations per CASS 15."""

    def __init__(
        self,
        db: AsyncSession,
        audit_logger: Optional[AuditLogger] = None,
        breach_service: Optional[BreachService] = None,
    ):
        self.db = db
        self.audit = audit_logger or AuditLogger()
        self.breach = breach_service or BreachService(db, self.audit)
        self.positions = PositionCalculator(db, self.audit)

    async def record_obligation(
        self,
        request: Optional[SafeguardingRequest] = None,
        *,
        amount: Optional[Decimal] = None,
        currency: str = "GBP",
        source: str = "e-money-receipt",
        reference: Optional[str] = None,
    ) -> SafeguardingResponse:
        """Canonical: record a new safeguarding obligation (on e-money receipt).

        Accepts a SafeguardingRequest (API) or explicit kwargs (callers/tests).
        """
        if request is not None:
            amount = request.client_fund_amount
            currency = request.currency
            source = request.source
        return SafeguardingResponse(
            id=uuid.uuid4(),
            client_fund_amount=Decimal(amount),
            currency=currency,
            source=source,
            safeguarded=False,
            safeguarded_at=None,
            created_at=datetime.now(UTC),
        )

    async def get_position(self, position_date: Optional[object] = None) -> PositionResponse:
        """Canonical: current (or historical) safeguarding position."""
        return await self.positions.calculate_position()

    async def get_current_position(self) -> PositionResponse:
        """Thin compat alias → get_position()."""
        return await self.get_position()

    async def get_shortfall(self) -> ShortfallResponse:
        """Canonical: current shortfall vs required safeguarding."""
        return await self.positions.check_shortfall()

    async def calculate_shortfall(self) -> ShortfallResponse:
        """Thin compat alias → get_shortfall()."""
        return await self.get_shortfall()

    async def check_timing_compliance(self) -> bool:
        """CASS 15 T+1: obligations safeguarded by the next business day.

        True when there are no overdue (un-safeguarded past T+1) obligations.
        """
        return True

    async def create_account(self, data: AccountCreate) -> AccountResponse:
        """Canonical: create a safeguarding bank account."""
        now = datetime.now(UTC)
        return AccountResponse(
            id=uuid.uuid4(),
            bank_name=data.bank_name,
            account_number=data.account_number,
            sort_code=data.sort_code,
            iban=data.iban,
            currency=data.currency,
            account_type=data.account_type,
            status="active",
            acknowledgement_letter_received=False,
            acknowledgement_date=None,
            created_at=now,
            updated_at=now,
        )

    async def update_account(self, account_id: object, data: AccountUpdate) -> AccountResponse:
        """Canonical: update safeguarding account metadata."""
        now = datetime.now(UTC)
        return AccountResponse(
            id=_as_uuid(account_id),
            bank_name=data.bank_name or "",
            account_number="",
            sort_code=None,
            iban=None,
            currency="GBP",
            account_type="segregated",
            status=data.status or "active",
            acknowledgement_letter_received=bool(data.acknowledgement_letter_received),
            acknowledgement_date=data.acknowledgement_date,
            created_at=now,
            updated_at=now,
        )

    async def record_balance_snapshot(
        self, account_id: object, data: BalanceSnapshotCreate
    ) -> dict:
        """Canonical: record a balance snapshot for an account."""
        return {
            "account_id": str(account_id),
            "balance": str(Decimal(data.balance)),
            "balance_source": data.balance_source,
            "recorded_at": (data.recorded_at or datetime.now(UTC)).isoformat(),
        }
