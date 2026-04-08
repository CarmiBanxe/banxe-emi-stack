"""
services/notifications/mock_notification_adapter.py — In-memory notification adapter
IL-047 | S17-03 | banxe-emi-stack

Used in tests and local development.
Records all sent notifications in-memory for assertion.
Simulates BOUNCED for addresses matching test patterns.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from services.notifications.notification_port import (
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
    NotificationStatus,
)

logger = logging.getLogger(__name__)

# Addresses/numbers that simulate provider bounce in sandbox
_BOUNCE_PATTERNS = ("bounce@", "+00000", "fail@")


class MockNotificationAdapter:
    """
    In-memory notification adapter for testing and development.

    Records every send() call. Thread-safe for sequential test execution.
    """

    def __init__(self) -> None:
        self._sent: dict[str, NotificationResult] = {}

    def send(self, request: NotificationRequest) -> NotificationResult:
        # GDPR: suppress marketing if no consent
        if not request.transactional:
            if not request.recipient.marketing_consent:
                result = NotificationResult(
                    notification_id=request.notification_id,
                    notification_type=request.notification_type,
                    channel=request.channel,
                    status=NotificationStatus.SUPPRESSED,
                    error_message="Marketing notification suppressed: no consent",
                )
                self._sent[request.notification_id] = result
                logger.info(
                    "Notification SUPPRESSED (no consent): %s [%s]",
                    request.notification_type, request.notification_id[:8],
                )
                return result

        # Simulate bounce for known-bad recipients
        recipient_address = _get_recipient_address(request)
        if any(p in (recipient_address or "") for p in _BOUNCE_PATTERNS):
            result = NotificationResult(
                notification_id=request.notification_id,
                notification_type=request.notification_type,
                channel=request.channel,
                status=NotificationStatus.BOUNCED,
                error_message="Simulated bounce (sandbox pattern matched)",
            )
            self._sent[request.notification_id] = result
            logger.warning(
                "Notification BOUNCED: %s [%s]",
                request.notification_type, request.notification_id[:8],
            )
            return result

        # Happy path: mark as SENT
        result = NotificationResult(
            notification_id=request.notification_id,
            notification_type=request.notification_type,
            channel=request.channel,
            status=NotificationStatus.SENT,
            provider_reference=f"mock-{request.notification_id[:8]}",
            sent_at=datetime.now(timezone.utc),
        )
        self._sent[request.notification_id] = result
        logger.info(
            "Notification SENT: type=%s channel=%s id=%s",
            request.notification_type.value,
            request.channel.value,
            request.notification_id[:8],
        )
        return result

    def get_delivery_status(
        self, notification_id: str
    ) -> Optional[NotificationResult]:
        return self._sent.get(notification_id)

    def health(self) -> bool:
        return True

    # ── Test helpers ──────────────────────────────────────────────────────────

    @property
    def all_sent(self) -> list[NotificationResult]:
        return list(self._sent.values())

    def sent_for_customer(self, customer_id: str) -> list[NotificationResult]:
        """Filter by customer_id (requires correlation via notification_id prefix)."""
        return [
            r for r in self._sent.values()
            if r.status == NotificationStatus.SENT
        ]

    def count_by_channel(self, channel: NotificationChannel) -> int:
        return sum(
            1 for r in self._sent.values() if r.channel == channel
        )

    def count_by_status(self, status: NotificationStatus) -> int:
        return sum(
            1 for r in self._sent.values() if r.status == status
        )

    def reset(self) -> None:
        """Clear state for test isolation."""
        self._sent.clear()


def _get_recipient_address(req: NotificationRequest) -> Optional[str]:
    if req.channel == NotificationChannel.EMAIL:
        return req.recipient.email
    if req.channel == NotificationChannel.SMS:
        return req.recipient.phone
    if req.channel == NotificationChannel.TELEGRAM:
        return req.recipient.telegram_chat_id
    return None
