"""
services/user_preferences/notification_preferences.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

NotificationPreferences — manage per-channel notification settings.
Includes quiet hours and daily frequency cap enforcement.
"""

from __future__ import annotations

from services.user_preferences.models import (
    AuditPort,
    InMemoryAuditPort,
    InMemoryNotificationPort,
    NotificationChannel,
    NotificationPort,
    NotificationPrefs,
)

DAILY_FREQUENCY_CAPS: dict[NotificationChannel, int] = {
    NotificationChannel.EMAIL: 5,
    NotificationChannel.SMS: 3,
    NotificationChannel.PUSH: 20,
    NotificationChannel.TELEGRAM: 10,
    NotificationChannel.WEBHOOK: 100,
}


class NotificationPreferences:
    """Manages notification channel preferences with quiet hours and caps."""

    def __init__(
        self,
        notif_port: NotificationPort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._notifs: NotificationPort = notif_port or InMemoryNotificationPort()
        self._audit: AuditPort = audit_port or InMemoryAuditPort()

    def get_channel_prefs(
        self,
        user_id: str,
        channel: NotificationChannel,
    ) -> NotificationPrefs:
        """Return stored or default (enabled=True, no quiet hours, default cap)."""
        stored = self._notifs.get(user_id, channel)
        if stored is not None:
            return stored
        return NotificationPrefs(
            user_id=user_id,
            channel=channel,
            enabled=True,
            frequency_cap_per_day=DAILY_FREQUENCY_CAPS[channel],
            quiet_hours_start=None,
            quiet_hours_end=None,
        )

    def set_channel_enabled(
        self,
        user_id: str,
        channel: NotificationChannel,
        enabled: bool,
    ) -> NotificationPrefs:
        """Enable or disable a notification channel."""
        existing = self.get_channel_prefs(user_id, channel)
        updated = NotificationPrefs(
            user_id=user_id,
            channel=channel,
            enabled=enabled,
            frequency_cap_per_day=existing.frequency_cap_per_day,
            quiet_hours_start=existing.quiet_hours_start,
            quiet_hours_end=existing.quiet_hours_end,
        )
        self._notifs.save(updated)
        return updated

    def set_quiet_hours(
        self,
        user_id: str,
        channel: NotificationChannel,
        start: int,
        end: int,
    ) -> NotificationPrefs:
        """Set quiet hours; validates 0 <= start, end < 24."""
        if not (0 <= start < 24) or not (0 <= end < 24):
            raise ValueError("Quiet hours must be in range 0-23")
        existing = self.get_channel_prefs(user_id, channel)
        updated = NotificationPrefs(
            user_id=user_id,
            channel=channel,
            enabled=existing.enabled,
            frequency_cap_per_day=existing.frequency_cap_per_day,
            quiet_hours_start=start,
            quiet_hours_end=end,
        )
        self._notifs.save(updated)
        return updated

    def is_in_quiet_hours(
        self,
        user_id: str,
        channel: NotificationChannel,
        hour: int,
    ) -> bool:
        """Return True if current hour is within quiet hours."""
        prefs = self.get_channel_prefs(user_id, channel)
        if prefs.quiet_hours_start is None or prefs.quiet_hours_end is None:
            return False
        start = prefs.quiet_hours_start
        end = prefs.quiet_hours_end
        if start <= end:
            return start <= hour < end
        # Wraps midnight: e.g. start=22, end=6
        return hour >= start or hour < end

    def check_frequency_cap(
        self,
        user_id: str,
        channel: NotificationChannel,
        sent_today: int,
    ) -> bool:
        """True = ok to send; False = cap exceeded."""
        prefs = self.get_channel_prefs(user_id, channel)
        return sent_today < prefs.frequency_cap_per_day

    def list_channel_prefs(self, user_id: str) -> list[NotificationPrefs]:
        """Return all channel preferences for user."""
        return self._notifs.list_user(user_id)
