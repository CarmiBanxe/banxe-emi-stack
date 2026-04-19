"""
tests/test_user_preferences/test_preference_store.py
IL-UPS-01 | Phase 39 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

import pytest

from services.user_preferences.models import (
    InMemoryAuditPort,
    InMemoryPreferencePort,
    PreferenceCategory,
    Theme,
)
from services.user_preferences.preference_store import DEFAULT_PREFERENCES, PreferenceStore


def _store() -> PreferenceStore:
    return PreferenceStore(InMemoryPreferencePort(), InMemoryAuditPort())


class TestGetPreference:
    def test_returns_stored_value(self) -> None:
        store = _store()
        store.set_preference("u1", PreferenceCategory.DISPLAY, "theme", "LIGHT")
        assert store.get_preference("u1", PreferenceCategory.DISPLAY, "theme") == "LIGHT"

    def test_returns_default_when_not_set(self) -> None:
        store = _store()
        val = store.get_preference("new-user", PreferenceCategory.DISPLAY, "theme")
        assert val == Theme.DARK.value

    def test_returns_empty_for_unknown_key(self) -> None:
        store = _store()
        val = store.get_preference("u1", PreferenceCategory.DISPLAY, "nonexistent_key")
        assert val == ""

    def test_seeded_user_has_stored_value(self) -> None:
        store = _store()
        val = store.get_preference("USR-001", PreferenceCategory.DISPLAY, "theme")
        assert val == Theme.DARK.value


class TestSetPreference:
    def test_set_updates_value(self) -> None:
        store = _store()
        pref = store.set_preference("u1", PreferenceCategory.DISPLAY, "theme", "LIGHT")
        assert pref.value == "LIGHT"

    def test_set_returns_user_preference(self) -> None:
        store = _store()
        pref = store.set_preference("u1", PreferenceCategory.SECURITY, "mfa_required", "false")
        assert pref.user_id == "u1"
        assert pref.category == PreferenceCategory.SECURITY
        assert pref.key == "mfa_required"

    def test_set_invalid_key_raises(self) -> None:
        store = _store()
        with pytest.raises(ValueError, match="Unknown preference key"):
            store.set_preference("u1", PreferenceCategory.DISPLAY, "invalid_key", "value")

    def test_set_logs_to_audit(self) -> None:
        audit = InMemoryAuditPort()
        store = PreferenceStore(InMemoryPreferencePort(), audit)
        store.set_preference("u1", PreferenceCategory.PRIVACY, "analytics", "true")
        assert len(audit.entries()) == 1
        assert audit.entries()[0]["action"] == "set_preference"

    def test_set_notifications_sms(self) -> None:
        store = _store()
        pref = store.set_preference("u2", PreferenceCategory.NOTIFICATIONS, "sms_enabled", "true")
        assert pref.value == "true"


class TestResetToDefaults:
    def test_reset_restores_defaults(self) -> None:
        store = _store()
        store.set_preference("u1", PreferenceCategory.DISPLAY, "theme", "LIGHT")
        store.reset_to_defaults("u1", PreferenceCategory.DISPLAY)
        val = store.get_preference("u1", PreferenceCategory.DISPLAY, "theme")
        assert val == Theme.DARK.value

    def test_reset_returns_list_of_prefs(self) -> None:
        store = _store()
        prefs = store.reset_to_defaults("u1", PreferenceCategory.DISPLAY)
        defaults = DEFAULT_PREFERENCES[PreferenceCategory.DISPLAY]
        assert len(prefs) == len(defaults)

    def test_reset_all_categories_have_defaults(self) -> None:
        store = _store()
        for cat in PreferenceCategory:
            prefs = store.reset_to_defaults("u-reset", cat)
            assert len(prefs) >= 1


class TestListPreferences:
    def test_returns_dict_with_categories(self) -> None:
        store = _store()
        result = store.list_preferences("u1")
        assert "DISPLAY" in result
        assert "NOTIFICATIONS" in result
        assert "PRIVACY" in result

    def test_stored_values_override_defaults(self) -> None:
        store = _store()
        store.set_preference("u1", PreferenceCategory.DISPLAY, "theme", "LIGHT")
        result = store.list_preferences("u1")
        assert result["DISPLAY"]["theme"] == "LIGHT"

    def test_get_all_user_prefs_returns_stored(self) -> None:
        store = _store()
        store.set_preference("u5", PreferenceCategory.SECURITY, "mfa_required", "true")
        all_prefs = store.get_all_user_prefs("u5")
        assert any(p.key == "mfa_required" for p in all_prefs)

    def test_seeded_user_prefs_in_list(self) -> None:
        store = _store()
        all_prefs = store.get_all_user_prefs("USR-001")
        assert len(all_prefs) >= 3
