"""
services/scheduled_payments/notification_bridge.py — Bridge to notification_hub
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime


class NotificationBridge:
    """Stub notification bridge — integrates with notification_hub in production."""

    def send_upcoming_reminder(
        self,
        schedule_id: str,
        payment_id: str,
        amount: str,
        days_before: int,
    ) -> dict[str, object]:
        return {
            "status": "QUEUED",
            "schedule_id": schedule_id,
            "payment_id": payment_id,
            "notification_type": "PAYMENT_REMINDER",
            "days_before": days_before,
            "amount": amount,
            "queued_at": datetime.now(UTC).isoformat(),
        }

    def send_failure_alert(
        self,
        failure_id: str,
        payment_id: str,
        failure_code: str,
    ) -> dict[str, str]:
        return {
            "status": "QUEUED",
            "failure_id": failure_id,
            "payment_id": payment_id,
            "notification_type": "PAYMENT_FAILED",
            "failure_code": failure_code,
            "queued_at": datetime.now(UTC).isoformat(),
        }

    def send_mandate_change_notification(
        self,
        mandate_id: str,
        change_type: str,
    ) -> dict[str, str]:
        return {
            "status": "QUEUED",
            "mandate_id": mandate_id,
            "notification_type": "MANDATE_CHANGE",
            "change_type": change_type,
            "queued_at": datetime.now(UTC).isoformat(),
        }
