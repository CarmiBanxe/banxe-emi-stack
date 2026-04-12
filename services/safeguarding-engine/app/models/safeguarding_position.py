"""SQLAlchemy models for safeguarding positions."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Date, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models import Base


class SafeguardingPosition(Base):
    """Daily safeguarding position snapshot."""

    __tablename__ = "positions"
    __table_args__ = {"schema": "safeguarding"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_date = Column(Date, nullable=False, unique=True)
    total_client_funds = Column(Numeric(18, 2), nullable=False)
    total_safeguarded = Column(Numeric(18, 2), nullable=False)
    # shortfall and is_compliant are GENERATED columns in DB
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    details = relationship("PositionDetail", back_populates="position")


class PositionDetail(Base):
    """Per-account breakdown within a position."""

    __tablename__ = "position_details"
    __table_args__ = {"schema": "safeguarding"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id = Column(UUID(as_uuid=True), ForeignKey("safeguarding.positions.id"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("safeguarding.accounts.id"), nullable=False)
    balance = Column(Numeric(18, 2), nullable=False)
    balance_source = Column(String(20), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    position = relationship("SafeguardingPosition", back_populates="details")
    account = relationship("SafeguardingAccount", back_populates="position_details")
