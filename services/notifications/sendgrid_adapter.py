"""
services/notifications/sendgrid_adapter.py — SendGrid email adapter (production stub)
IL-047 | S17-03 | banxe-emi-stack

STATUS: STUB — requires SENDGRID_API_KEY env var.
FCA COBS 2.2: all emails must use approved templates.

To activate:
  1. Register on sendgrid.com → get API key
  2. Set SENDGRID_API_KEY in /data/banxe/.env
  3. Set SENDGRID_FROM_EMAIL=noreply@banxe.co.uk
  4. Replace InMemoryNotificationAdapter with SendGridAdapter in deps.py
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.notifications.notification_port import (
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
    NotificationStatus,
)

logger = logging.getLogger(__name__)


class SendGridAdapter:  # pragma: no cover
    """
    Production email adapter via SendGrid API v3.

    Only handles EMAIL channel. For SMS/Telegram use separate adapters.
    """

    def __init__(self) -> None:
        self._api_key = os.environ.get("SENDGRID_API_KEY", "")
        self._from_email = os.environ.get(
            "SENDGRID_FROM_EMAIL", "noreply@banxe.co.uk"
        )
        if not self._api_key:
            raise EnvironmentError(
                "SENDGRID_API_KEY not set. "
                "Register at sendgrid.com → create API key → set in .env"
            )

    def send(self, request: NotificationRequest) -> NotificationResult:
        if request.channel != NotificationChannel.EMAIL:
            return NotificationResult(
                notification_id=request.notification_id,
                notification_type=request.notification_type,
                channel=request.channel,
                status=NotificationStatus.FAILED,
                error_message=(
                    f"SendGridAdapter only handles EMAIL, got {request.channel}"
                ),
            )

        if not request.recipient.email:
            return NotificationResult(
                notification_id=request.notification_id,
                notification_type=request.notification_type,
                channel=request.channel,
                status=NotificationStatus.FAILED,
                error_message="No email address provided",
            )

        try:
            import sendgrid  # type: ignore[import]
            from sendgrid.helpers.mail import Mail  # type: ignore[import]

            subject = request.template_vars.get(
                "subject", request.notification_type.value
            )
            body = request.template_vars.get("body", "")

            message = Mail(
                from_email=self._from_email,
                to_emails=request.recipient.email,
                subject=subject,
                plain_text_content=body,
            )
            sg = sendgrid.SendGridAPIClient(api_key=self._api_key)
            response = sg.send(message)

            if response.status_code in (200, 202):
                return NotificationResult(
                    notification_id=request.notification_id,
                    notification_type=request.notification_type,
                    channel=request.channel,
                    status=NotificationStatus.SENT,
                    provider_reference=response.headers.get("X-Message-Id"),
                    sent_at=datetime.now(timezone.utc),
                )
            return NotificationResult(
                notification_id=request.notification_id,
                notification_type=request.notification_type,
                channel=request.channel,
                status=NotificationStatus.FAILED,
                error_message=f"SendGrid HTTP {response.status_code}",
            )

        except ImportError:
            raise ImportError(
                "sendgrid package not installed. "
                "Add sendgrid>=6.0 to requirements.txt"
            )
        except Exception as exc:
            logger.error("SendGrid send failed: %s", exc)
            return NotificationResult(
                notification_id=request.notification_id,
                notification_type=request.notification_type,
                channel=request.channel,
                status=NotificationStatus.FAILED,
                error_message=str(exc),
            )

    def get_delivery_status(
        self, notification_id: str
    ) -> Optional[NotificationResult]:
        # SendGrid webhooks handle delivery status asynchronously.
        # Track via webhook_router.py WebhookProvider.SENDGRID (future).
        return None

    def health(self) -> bool:
        try:
            import sendgrid  # type: ignore[import]
            sg = sendgrid.SendGridAPIClient(api_key=self._api_key)
            resp = sg.client.user.get()
            return resp.status_code == 200
        except Exception:
            return False
