"""
tests/test_user_preferences/test_locale_manager.py
IL-UPS-01 | Phase 39 | banxe-emi-stack — 14 tests
"""

from __future__ import annotations

from decimal import Decimal

from services.user_preferences.locale_manager import FALLBACK_CHAIN, LocaleManager
from services.user_preferences.models import Language


def _mgr() -> LocaleManager:
    return LocaleManager()


class TestGetLocale:
    def test_default_language_en(self) -> None:
        mgr = _mgr()
        locale = mgr.get_locale("new-user")
        assert locale.language == Language.EN

    def test_default_timezone_utc(self) -> None:
        mgr = _mgr()
        locale = mgr.get_locale("new-user")
        assert locale.timezone == "UTC"

    def test_default_date_format(self) -> None:
        mgr = _mgr()
        locale = mgr.get_locale("new-user")
        assert locale.date_format == "DD/MM/YYYY"

    def test_stored_locale_returned(self) -> None:
        mgr = _mgr()
        mgr.set_language("u1", Language.FR)
        locale = mgr.get_locale("u1")
        assert locale.language == Language.FR


class TestSetLanguage:
    def test_set_language_stores(self) -> None:
        mgr = _mgr()
        locale = mgr.set_language("u1", Language.DE)
        assert locale.language == Language.DE

    def test_set_language_preserves_timezone(self) -> None:
        mgr = _mgr()
        mgr.set_timezone("u1", "Europe/Berlin")
        locale = mgr.set_language("u1", Language.DE)
        assert locale.timezone == "Europe/Berlin"


class TestSetTimezone:
    def test_set_timezone_stores(self) -> None:
        mgr = _mgr()
        locale = mgr.set_timezone("u1", "Europe/London")
        assert locale.timezone == "Europe/London"

    def test_empty_timezone_raises(self) -> None:
        mgr = _mgr()
        import pytest

        with pytest.raises(ValueError, match="non-empty"):
            mgr.set_timezone("u1", "")


class TestFallbackChain:
    def test_arabic_falls_back_to_en(self) -> None:
        mgr = _mgr()
        fb = mgr.get_fallback_language(Language.AR)
        assert fb == Language.EN

    def test_chinese_falls_back_to_en(self) -> None:
        mgr = _mgr()
        fb = mgr.get_fallback_language(Language.ZH)
        assert fb == Language.EN

    def test_russian_falls_back_to_en(self) -> None:
        mgr = _mgr()
        fb = mgr.get_fallback_language(Language.RU)
        assert fb == Language.EN

    def test_english_no_fallback(self) -> None:
        mgr = _mgr()
        fb = mgr.get_fallback_language(Language.EN)
        assert fb == Language.EN

    def test_fallback_chain_has_three_entries(self) -> None:
        assert len(FALLBACK_CHAIN) == 3


class TestFormatAmount:
    def test_format_gbp_amount(self) -> None:
        mgr = _mgr()
        result = mgr.format_amount(Decimal("123.45"), "GBP", "u1")
        assert "GBP" in result
        assert "123.45" in result

    def test_format_uses_decimal_not_float(self) -> None:
        mgr = _mgr()
        result = mgr.format_amount(Decimal("0.01"), "EUR", "u1")
        assert "0.01" in result

    def test_list_supported_languages(self) -> None:
        mgr = _mgr()
        langs = mgr.list_supported_languages()
        assert Language.EN in langs
        assert Language.AR in langs
        assert len(langs) == 7
