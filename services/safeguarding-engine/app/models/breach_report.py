"""SQLAlchemy model for breach reports."""

import uuid
from datetime import UTC, datetime
from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class BreachReport(Base):
    """Safeguarding breach report for FCA notification."""

    __tablename__ = "breaches"
    __table_args__ = {"schema": "safeguarding"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breach_type = Column(String(50), nullable=False)
    severity = Column(String(10), nullable=False)  # 'critical', 'major', 'minor'
    description = Column(Text, nullable=False)
    shortfall_amount = Column(Numeric(18, 2))
    detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    fca_notified = Column(Boolean, default=False)
    fca_notified_at = Column(DateTime(timezone=True))
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True))
    remediation_notes = Column(Text)
    created_by = Column(String(100), nullable=False, default="system")
