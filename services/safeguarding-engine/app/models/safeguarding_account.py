"""SQLAlchemy model for safeguarding bank accounts."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models import Base


class SafeguardingAccount(Base):
    """Segregated safeguarding bank account per CASS 15."""
    __tablename__ = "accounts"
    __table_args__ = {"schema": "safeguarding"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_name = Column(String(255), nullable=False)
    account_number = Column(String(50), nullable=False)
    sort_code = Column(String(10))
    iban = Column(String(34))
    currency = Column(String(3), nullable=False, default="GBP")
    account_type = Column(String(20), nullable=False, default="segregated")
    status = Column(String(20), nullable=False, default="active")
    acknowledgement_letter_received = Column(Boolean, default=False)
    acknowledgement_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    position_details = relationship("PositionDetail", back_populates="account")
