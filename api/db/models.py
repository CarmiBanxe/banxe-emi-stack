"""
api/db/models.py — SQLAlchemy ORM models
IL-046 | banxe-emi-stack

Tables:
  customers      — persisted customer records (email, display info)
  auth_sessions  — issued JWT sessions (for revocation / audit)

These are persistence-layer models, separate from the domain dataclasses
in services/customer/customer_port.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.database import Base


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="INDIVIDUAL")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="ONBOARDING")
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    sessions: Mapped[list[AuthSession]] = relationship(
        "AuthSession", back_populates="customer", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Store first 16 chars of token for lookup; full token in JWT (self-contained)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    customer: Mapped[Customer] = relationship("Customer", back_populates="sessions")
