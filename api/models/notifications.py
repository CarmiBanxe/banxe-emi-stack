"""
api/models/notifications.py — Pydantic v2 schemas for Notifications API
IL-047 | S17-03 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from services.notifications.notification_port import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)

# ── Request schemas ───────────────────────────────────────────────────────────


class SendNotificationRequest(BaseModel):
    """Direct send (internal API — operator use only)."""

    customer_id: str | None = None
    notification_type: NotificationType
    channel: NotificationChannel
    recipient_email: str | None = None
    recipient_phone: str | None = None
    recipient_telegram_id: str | None = None
    template_vars: dict = {}
    transactional: bool = True
    correlation_id: str | None = None

    @field_validator("recipient_email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v and "@" not in v:
            raise ValueError("Invalid email address")
        return v


# ── Response schemas ──────────────────────────────────────────────────────────


class NotificationResultResponse(BaseModel):
    notification_id: str
    notification_type: NotificationType
    channel: NotificationChannel
    status: NotificationStatus
    provider_reference: str | None = None
    error_message: str | None = None
    sent_at: datetime | None = None

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResultResponse]
    total: int


class RenderedNotificationResponse(BaseModel):
    notification_type: NotificationType
    subject: str
    body: str
