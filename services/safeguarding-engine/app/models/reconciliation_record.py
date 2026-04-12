"""SQLAlchemy model for reconciliation records."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Date, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models import Base


class ReconciliationRecord(Base):
    """Daily/monthly reconciliation results per CASS 15."""
    __tablename__ = "reconciliations"
    __table_args__ = {"schema": "safeguarding"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recon_type = Column(String(10), nullable=False)  # 'daily', 'monthly'
    recon_date = Column(Date, nullable=False)
    ledger_total = Column(Numeric(18, 2), nullable=False)
    bank_total = Column(Numeric(18, 2), nullable=False)
    # difference is GENERATED column in DB
    status = Column(String(20), nullable=False)  # 'matched', 'break', 'pending'
    break_items = Column(JSONB, default=[])
    resolved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
