"""
services/user_preferences/locale_manager.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

LocaleManager — manages language, timezone, and formatting preferences.
I-01: format_amount uses Decimal, never float.
"""

from __future__ import annotations

from decimal import Decimal

from services.user_preferences.models import (
    AuditPort,
    InMemoryAuditPort,
    Language,
    LocaleSettings,
)

FALLBACK_CHAIN: dict[Language, Language] = {
    Language.AR: Language.EN,
    Language.ZH: Language.EN,
    Language.RU: Language.EN,
}

_DEFAULT_LOCALE = LocaleSettings(
    user_id="",
    language=Language.EN,
    timezone="UTC",
    date_format="DD/MM/YYYY",
    currency_format="GBP 0.00",
    number_format="1,234.56",
)


class LocaleManager:
    """Manages locale settings for users."""

    def __init__(self, audit_port: AuditPort | None = None) -> None:
        self._store: dict[str, LocaleSettings] = {}
        self._audit: AuditPort = audit_port or InMemoryAuditPort()

    def get_locale(self, user_id: str) -> LocaleSettings:
        """Return stored or default (EN, UTC, DD/MM/YYYY)."""
        stored = self._store.get(user_id)
        if stored is not None:
            return stored
        return LocaleSettings(
            user_id=user_id,
            language=_DEFAULT_LOCALE.language,
            timezone=_DEFAULT_LOCALE.timezone,
            date_format=_DEFAULT_LOCALE.date_format,
            currency_format=_DEFAULT_LOCALE.currency_format,
            number_format=_DEFAULT_LOCALE.number_format,
        )

    def set_language(self, user_id: str, language: Language) -> LocaleSettings:
        """Update user language preference."""
        current = self.get_locale(user_id)
        updated = LocaleSettings(
            user_id=user_id,
            language=language,
            timezone=current.timezone,
            date_format=current.date_format,
            currency_format=current.currency_format,
            number_format=current.number_format,
        )
        self._store[user_id] = updated
        return updated

    def set_timezone(self, user_id: str, timezone: str) -> LocaleSettings:
        """Update user timezone; validates non-empty string."""
        if not timezone:
            raise ValueError("Timezone must be a non-empty string")
        current = self.get_locale(user_id)
        updated = LocaleSettings(
            user_id=user_id,
            language=current.language,
            timezone=timezone,
            date_format=current.date_format,
            currency_format=current.currency_format,
            number_format=current.number_format,
        )
        self._store[user_id] = updated
        return updated

    def get_fallback_language(self, language: Language) -> Language:
        """Return FALLBACK_CHAIN.get(language, language)."""
        return FALLBACK_CHAIN.get(language, language)

    def format_amount(self, amount: Decimal, currency: str, user_id: str) -> str:
        """Format using user's currency_format preference; default 'GBP 0.00'."""
        locale = self.get_locale(user_id)
        fmt = locale.currency_format
        if "0.00" in fmt:
            formatted_amount = f"{amount:.2f}"
            return f"{currency} {formatted_amount}"
        return f"{currency} {amount}"

    def list_supported_languages(self) -> list[Language]:
        """Return all supported languages."""
        return list(Language)
