"""
api/models/notifications.py — Pydantic v2 schemas for Notifications API
IL-047 | S17-03 | banxe-emi-stack
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from services.notifications.notification_port import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)


# ── Request schemas ───────────────────────────────────────────────────────────

class SendNotificationRequest(BaseModel):
    """Direct send (internal API — operator use only)."""
    customer_id: Optional[str] = None
    notification_type: NotificationType
    channel: NotificationChannel
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_telegram_id: Optional[str] = None
    template_vars: dict = {}
    transactional: bool = True
    correlation_id: Optional[str] = None

    @field_validator("recipient_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v and "@" not in v:
            raise ValueError("Invalid email address")
        return v


# ── Response schemas ──────────────────────────────────────────────────────────

class NotificationResultResponse(BaseModel):
    notification_id: str
    notification_type: NotificationType
    channel: NotificationChannel
    status: NotificationStatus
    provider_reference: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResultResponse]
    total: int


class RenderedNotificationResponse(BaseModel):
    notification_type: NotificationType
    subject: str
    body: str
