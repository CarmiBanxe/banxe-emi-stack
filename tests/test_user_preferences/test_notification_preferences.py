"""
tests/test_user_preferences/test_notification_preferences.py
IL-UPS-01 | Phase 39 | banxe-emi-stack — 14 tests
"""

from __future__ import annotations

import pytest

from services.user_preferences.models import (
    InMemoryAuditPort,
    InMemoryNotificationPort,
    NotificationChannel,
)
from services.user_preferences.notification_preferences import (
    DAILY_FREQUENCY_CAPS,
    NotificationPreferences,
)


def _prefs() -> NotificationPreferences:
    return NotificationPreferences(InMemoryNotificationPort(), InMemoryAuditPort())


class TestGetChannelPrefs:
    def test_default_enabled_true(self) -> None:
        prefs = _prefs()
        p = prefs.get_channel_prefs("u1", NotificationChannel.EMAIL)
        assert p.enabled is True

    def test_default_no_quiet_hours(self) -> None:
        prefs = _prefs()
        p = prefs.get_channel_prefs("u1", NotificationChannel.SMS)
        assert p.quiet_hours_start is None
        assert p.quiet_hours_end is None

    def test_default_frequency_cap(self) -> None:
        prefs = _prefs()
        p = prefs.get_channel_prefs("u1", NotificationChannel.EMAIL)
        assert p.frequency_cap_per_day == DAILY_FREQUENCY_CAPS[NotificationChannel.EMAIL]

    def test_webhook_high_cap(self) -> None:
        prefs = _prefs()
        p = prefs.get_channel_prefs("u1", NotificationChannel.WEBHOOK)
        assert p.frequency_cap_per_day == 100


class TestSetChannelEnabled:
    def test_disable_channel(self) -> None:
        prefs = _prefs()
        p = prefs.set_channel_enabled("u1", NotificationChannel.SMS, False)
        assert p.enabled is False

    def test_enable_channel(self) -> None:
        prefs = _prefs()
        prefs.set_channel_enabled("u1", NotificationChannel.SMS, False)
        p = prefs.set_channel_enabled("u1", NotificationChannel.SMS, True)
        assert p.enabled is True

    def test_stored_after_set(self) -> None:
        prefs = _prefs()
        prefs.set_channel_enabled("u1", NotificationChannel.TELEGRAM, False)
        p = prefs.get_channel_prefs("u1", NotificationChannel.TELEGRAM)
        assert p.enabled is False


class TestSetQuietHours:
    def test_set_quiet_hours(self) -> None:
        prefs = _prefs()
        p = prefs.set_quiet_hours("u1", NotificationChannel.EMAIL, 22, 8)
        assert p.quiet_hours_start == 22
        assert p.quiet_hours_end == 8

    def test_invalid_start_raises(self) -> None:
        prefs = _prefs()
        with pytest.raises(ValueError, match="range 0-23"):
            prefs.set_quiet_hours("u1", NotificationChannel.EMAIL, 24, 6)

    def test_invalid_end_raises(self) -> None:
        prefs = _prefs()
        with pytest.raises(ValueError, match="range 0-23"):
            prefs.set_quiet_hours("u1", NotificationChannel.EMAIL, 22, -1)


class TestIsInQuietHours:
    def test_no_quiet_hours_always_false(self) -> None:
        prefs = _prefs()
        assert prefs.is_in_quiet_hours("u1", NotificationChannel.EMAIL, 14) is False

    def test_in_quiet_hours(self) -> None:
        prefs = _prefs()
        prefs.set_quiet_hours("u1", NotificationChannel.EMAIL, 22, 8)
        assert prefs.is_in_quiet_hours("u1", NotificationChannel.EMAIL, 23) is True

    def test_outside_quiet_hours(self) -> None:
        prefs = _prefs()
        prefs.set_quiet_hours("u1", NotificationChannel.EMAIL, 22, 8)
        assert prefs.is_in_quiet_hours("u1", NotificationChannel.EMAIL, 14) is False


class TestFrequencyCap:
    def test_under_cap_ok(self) -> None:
        prefs = _prefs()
        assert prefs.check_frequency_cap("u1", NotificationChannel.EMAIL, 3) is True

    def test_at_cap_blocked(self) -> None:
        prefs = _prefs()
        cap = DAILY_FREQUENCY_CAPS[NotificationChannel.EMAIL]
        assert prefs.check_frequency_cap("u1", NotificationChannel.EMAIL, cap) is False

    def test_list_channel_prefs(self) -> None:
        prefs = _prefs()
        prefs.set_channel_enabled("u1", NotificationChannel.EMAIL, False)
        prefs.set_channel_enabled("u1", NotificationChannel.SMS, True)
        result = prefs.list_channel_prefs("u1")
        assert len(result) == 2
