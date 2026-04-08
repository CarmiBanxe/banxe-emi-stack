"""
api/routers/notifications.py — Notification endpoints
IL-047 | S17-03 | banxe-emi-stack

POST /v1/notifications/send           — send notification (operator/internal)
GET  /v1/notifications/{id}/status    — get delivery status by notification_id
GET  /v1/notifications/preview        — preview rendered notification body
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from api.models.notifications import (
    NotificationResultResponse,
    RenderedNotificationResponse,
    SendNotificationRequest,
)
from services.notifications.mock_notification_adapter import MockNotificationAdapter
from services.notifications.notification_port import (
    NotificationRecipient,
    NotificationRequest,
)
from services.notifications.notification_service import NotificationService

router = APIRouter(tags=["Notifications"])


@lru_cache(maxsize=1)
def _get_notification_service() -> NotificationService:
    adapter = MockNotificationAdapter()
    return NotificationService(adapter=adapter)


@router.post(
    "/notifications/send",
    response_model=NotificationResultResponse,
    status_code=201,
    summary="Send a notification (operator)",
)
def send_notification(
    body: SendNotificationRequest,
) -> NotificationResultResponse:
    """
    Directly dispatch a notification to a customer or recipient.
    Operator-only endpoint — requires at least one recipient field.
    FCA COBS 2.2: content derived from approved templates.
    """
    if not any([
        body.recipient_email,
        body.recipient_phone,
        body.recipient_telegram_id,
    ]):
        raise HTTPException(
            status_code=422,
            detail="At least one recipient field required "
                   "(recipient_email, recipient_phone, or recipient_telegram_id)",
        )

    svc = _get_notification_service()
    recipient = NotificationRecipient(
        customer_id=body.customer_id,
        email=body.recipient_email,
        phone=body.recipient_phone,
        telegram_chat_id=body.recipient_telegram_id,
        marketing_consent=not body.transactional,
    )
    request = NotificationRequest.create(
        notification_type=body.notification_type,
        channel=body.channel,
        recipient=recipient,
        template_vars=body.template_vars,
        transactional=body.transactional,
        correlation_id=body.correlation_id,
    )
    result = svc.send(request)
    return NotificationResultResponse(
        notification_id=result.notification_id,
        notification_type=result.notification_type,
        channel=result.channel,
        status=result.status,
        provider_reference=result.provider_reference,
        error_message=result.error_message,
        sent_at=result.sent_at,
    )


@router.get(
    "/notifications/{notification_id}/status",
    response_model=NotificationResultResponse,
    summary="Get notification delivery status",
)
def get_notification_status(
    notification_id: str,
) -> NotificationResultResponse:
    svc = _get_notification_service()
    result = svc.get_delivery_status(notification_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Notification {notification_id} not found",
        )
    return NotificationResultResponse(
        notification_id=result.notification_id,
        notification_type=result.notification_type,
        channel=result.channel,
        status=result.status,
        provider_reference=result.provider_reference,
        error_message=result.error_message,
        sent_at=result.sent_at,
    )


@router.get(
    "/notifications/preview",
    response_model=RenderedNotificationResponse,
    summary="Preview notification body (template rendering)",
)
def preview_notification(
    notification_type: str,
    amount: str = "100.00",
    currency: str = "£",
    creditor_name: str = "Example Recipient",
    rail: str = "FPS",
    reference: str = "REF-001",
) -> RenderedNotificationResponse:
    """
    Render a notification template with sample variables.
    Useful for compliance review (FCA COBS 2.2 approval workflow).
    """
    from services.notifications.notification_port import NotificationType
    try:
        notif_type = NotificationType(notification_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown notification type: {notification_type}",
        )

    svc = _get_notification_service()
    vars_map = {
        "amount": amount,
        "currency": currency,
        "creditor_name": creditor_name,
        "rail": rail,
        "reference": reference,
    }
    return RenderedNotificationResponse(
        notification_type=notif_type,
        subject=svc.render_subject(notif_type, vars_map),
        body=svc.render_body(notif_type, vars_map),
    )
