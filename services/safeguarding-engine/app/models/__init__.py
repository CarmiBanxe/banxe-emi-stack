"""SQLAlchemy ORM models for safeguarding engine."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class SafeguardingAccount(Base):
    """Segregated safeguarding bank accounts (CASS 15)."""
    __tablename__ = "accounts"
    __table_args__ = {"schema": "safeguarding"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_code: Mapped[str | None] = mapped_column(String(10))
    iban: Mapped[str | None] = mapped_column(String(34))
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    account_type: Mapped[str] = mapped_column(String(20), default="segregated")
    status: Mapped[str] = mapped_column(String(20), default="active")
    acknowledgement_letter_received: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledgement_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    position_details = relationship("PositionDetail", back_populates="account")


class SafeguardingPosition(Base):
    """Daily safeguarding position snapshots."""
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("position_date"), {"schema": "safeguarding"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_client_funds: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_safeguarded: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    shortfall: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    is_compliant: Mapped[bool] = mapped_column(Boolean, default=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    details = relationship("PositionDetail", back_populates="position")


class PositionDetail(Base):
    """Per-account breakdown within a position."""
    __tablename__ = "position_details"
    __table_args__ = {"schema": "safeguarding"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("safeguarding.positions.id"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("safeguarding.accounts.id"), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_source: Mapped[str] = mapped_column(String(20), nullable=False)  # bank_api, manual, statement
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    position = relationship("SafeguardingPosition", back_populates="details")
    account = relationship("SafeguardingAccount", back_populates="position_details")


class ReconciliationRecord(Base):
    """Daily/monthly reconciliation records."""
    __tablename__ = "reconciliations"
    __table_args__ = {"schema": "safeguarding"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recon_type: Mapped[str] = mapped_column(String(10), nullable=False)  # daily, monthly
    recon_date: Mapped[date] = mapped_column(Date, nullable=False)
    ledger_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    bank_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # matched, break, pending
    break_items: Mapped[dict | None] = mapped_column(JSONB, default=list)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BreachReport(Base):
    """Safeguarding breach reports for FCA notification."""
    __tablename__ = "breaches"
    __table_args__ = {"schema": "safeguarding"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breach_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # critical, major, minor
    description: Mapped[str] = mapped_column(Text, nullable=False)
    shortfall_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fca_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    fca_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remediation_notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100), default="system")


__all__ = [
    "Base",
    "SafeguardingAccount",
    "SafeguardingPosition",
    "PositionDetail",
    "ReconciliationRecord",
    "BreachReport",
]
