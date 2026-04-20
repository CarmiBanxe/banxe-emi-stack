"""Tests for UBORegistry — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.kyb_onboarding.models import InMemoryUBOStore, UBOVerification
from services.kyb_onboarding.ubo_registry import (
    BLOCKED_JURISDICTIONS,
    UBO_THRESHOLD_PCT,
    UBORegistry,
)


def make_registry():
    return UBORegistry(InMemoryUBOStore())


# --- register_ubo ---


def test_register_ubo_creates_ubo():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "John Doe", "GB", "1990-01-01", Decimal("30"), False)
    assert ubo.ubo_id.startswith("ubo_")
    assert ubo.verification_status == UBOVerification.PENDING


def test_register_ubo_ownership_pct_is_decimal():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "Jane", "GB", "1985-01-01", Decimal("25.5"), False)
    assert isinstance(ubo.ownership_pct, Decimal)


def test_register_ubo_psc_requires_25_pct():
    reg = make_registry()
    with pytest.raises(ValueError, match="PSC requires"):
        reg.register_ubo("app_001", "John", "GB", "1990-01-01", Decimal("24.99"), True)


def test_register_ubo_psc_exactly_25_pct_ok():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "John", "GB", "1990-01-01", UBO_THRESHOLD_PCT, True)
    assert ubo.is_psc is True


def test_register_ubo_not_psc_below_25_ok():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "John", "GB", "1990-01-01", Decimal("10"), False)
    assert ubo.is_psc is False


def test_register_ubo_normalises_nationality():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "John", "gb", "1990-01-01", Decimal("30"), False)
    assert ubo.nationality == "GB"


# --- verify_identity ---


def test_verify_identity_sets_verified():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "John", "GB", "1990-01-01", Decimal("30"), False)
    verified = reg.verify_identity(ubo.ubo_id, "ref_123")
    assert verified.verification_status == UBOVerification.VERIFIED


def test_verify_identity_nonexistent_raises():
    reg = make_registry()
    with pytest.raises(ValueError):
        reg.verify_identity("nonexistent", "ref_123")


# --- screen_sanctions ---


def test_screen_sanctions_blocked_nationality_ru():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "Ivan", "RU", "1980-01-01", Decimal("30"), False)
    ok, reason = reg.screen_sanctions(ubo.ubo_id)
    assert not ok
    assert reason == "blocked_jurisdiction"


def test_screen_sanctions_blocked_nationality_ir():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "Ali", "IR", "1980-01-01", Decimal("30"), False)
    ok, reason = reg.screen_sanctions(ubo.ubo_id)
    assert not ok
    assert reason == "blocked_jurisdiction"


def test_screen_sanctions_all_blocked_jurisdictions():
    reg = make_registry()
    for jur in BLOCKED_JURISDICTIONS:
        ubo = reg.register_ubo("app_001", "Person", jur, "1980-01-01", Decimal("30"), False)
        ok, reason = reg.screen_sanctions(ubo.ubo_id)
        assert not ok
        assert reason == "blocked_jurisdiction"


def test_screen_sanctions_fatf_greylist_edd():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "Pak Person", "PK", "1980-01-01", Decimal("30"), False)
    ok, reason = reg.screen_sanctions(ubo.ubo_id)
    assert ok
    assert reason == "edd_required"


def test_screen_sanctions_clear():
    reg = make_registry()
    ubo = reg.register_ubo("app_001", "UK Person", "GB", "1980-01-01", Decimal("30"), False)
    ok, reason = reg.screen_sanctions(ubo.ubo_id)
    assert ok
    assert reason == "clear"


def test_screen_sanctions_nonexistent_ubo():
    reg = make_registry()
    ok, reason = reg.screen_sanctions("nonexistent")
    assert not ok
    assert reason == "ubo_not_found"


# --- get_ubos_for_business / calculate_control_percentage ---


def test_get_ubos_for_business_empty():
    reg = make_registry()
    ubos = reg.get_ubos_for_business("app_empty")
    assert ubos == []


def test_calculate_control_percentage_is_decimal():
    reg = make_registry()
    reg.register_ubo("app_001", "A", "GB", "1990-01-01", Decimal("30"), False)
    reg.register_ubo("app_001", "B", "GB", "1985-01-01", Decimal("20"), False)
    pct = reg.calculate_control_percentage("app_001")
    assert isinstance(pct, Decimal)
    assert pct == Decimal("50")
