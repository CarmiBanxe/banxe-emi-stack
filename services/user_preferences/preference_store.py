"""
services/user_preferences/preference_store.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

PreferenceStore — get/set/reset user preferences with defaults fallback.
I-24: All changes audit-logged.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.user_preferences.models import (
    AuditPort,
    InMemoryAuditPort,
    InMemoryPreferencePort,
    Language,
    PreferenceCategory,
    PreferencePort,
    Theme,
    UserPreference,
)

DEFAULT_PREFERENCES: dict[PreferenceCategory, dict[str, str]] = {
    PreferenceCategory.DISPLAY: {
        "theme": Theme.DARK.value,
        "language": Language.EN.value,
    },
    PreferenceCategory.NOTIFICATIONS: {
        "email_enabled": "true",
        "sms_enabled": "false",
    },
    PreferenceCategory.PRIVACY: {
        "analytics": "false",
        "marketing": "false",
    },
    PreferenceCategory.SECURITY: {
        "mfa_required": "true",
        "session_timeout_mins": "30",
    },
    PreferenceCategory.ACCESSIBILITY: {
        "font_size": "medium",
        "high_contrast": "false",
    },
}


class PreferenceStore:
    """Manages user preference storage with defaults fallback."""

    def __init__(
        self,
        pref_port: PreferencePort | None = None,
        audit_port: AuditPort | None = None,
    ) -> None:
        self._prefs: PreferencePort = pref_port or InMemoryPreferencePort()
        self._audit: AuditPort = audit_port or InMemoryAuditPort()

    def get_preference(self, user_id: str, category: PreferenceCategory, key: str) -> str:
        """Return stored value or DEFAULT_PREFERENCES fallback."""
        stored = self._prefs.get(user_id, category, key)
        if stored is not None:
            return stored
        return DEFAULT_PREFERENCES.get(category, {}).get(key, "")

    def set_preference(
        self,
        user_id: str,
        category: PreferenceCategory,
        key: str,
        value: str,
    ) -> UserPreference:
        """Validate key exists in defaults; save; log to AuditPort (I-24)."""
        defaults = DEFAULT_PREFERENCES.get(category, {})
        if key not in defaults:
            raise ValueError(f"Unknown preference key '{key}' for category {category.value}")
        self._prefs.set(user_id, category, key, value)
        self._audit.log(
            action="set_preference",
            resource_id=f"{user_id}:{category.value}:{key}",
            details={"user_id": user_id, "category": category.value, "key": key, "value": value},
            outcome="OK",
        )
        return UserPreference(
            user_id=user_id,
            category=category,
            key=key,
            value=value,
            updated_at=datetime.now(UTC),
            updated_by="system",
        )

    def reset_to_defaults(
        self,
        user_id: str,
        category: PreferenceCategory,
    ) -> list[UserPreference]:
        """Reset all keys in category to defaults."""
        defaults = DEFAULT_PREFERENCES.get(category, {})
        results: list[UserPreference] = []
        for key, value in defaults.items():
            pref = self.set_preference(user_id, category, key, value)
            results.append(pref)
        return results

    def list_preferences(self, user_id: str) -> dict[str, dict]:
        """Return {category: {key: value}} merged with defaults."""
        merged: dict[str, dict] = {}
        for cat, defaults in DEFAULT_PREFERENCES.items():
            cat_dict: dict[str, str] = dict(defaults)
            for key in defaults:
                stored = self._prefs.get(user_id, cat, key)
                if stored is not None:
                    cat_dict[key] = stored
            merged[cat.value] = cat_dict
        return merged

    def get_all_user_prefs(self, user_id: str) -> list[UserPreference]:
        """Return all stored preferences for user."""
        return self._prefs.list_user(user_id)
