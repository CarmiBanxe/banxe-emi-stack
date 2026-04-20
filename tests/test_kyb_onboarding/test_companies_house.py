"""Tests for CompaniesHouseAdapter — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

import pytest

from services.kyb_onboarding.companies_house_adapter import (
    SEEDED,
    CompaniesHouseAdapter,
    InMemoryCompaniesHouseAdapter,
)

# --- InMemoryCompaniesHouseAdapter ---


def test_lookup_company_active_ltd():
    adapter = InMemoryCompaniesHouseAdapter()
    result = adapter.lookup_company("12345678")
    assert result is not None
    assert result["name"] == "Acme Ltd"
    assert result["status"] == "active"


def test_lookup_company_active_llp():
    adapter = InMemoryCompaniesHouseAdapter()
    result = adapter.lookup_company("OC123456")
    assert result is not None
    assert result["type"] == "llp"


def test_lookup_company_dissolved():
    adapter = InMemoryCompaniesHouseAdapter()
    result = adapter.lookup_company("87654321")
    assert result is not None
    assert result["status"] == "dissolved"


def test_lookup_company_unknown_returns_none():
    adapter = InMemoryCompaniesHouseAdapter()
    assert adapter.lookup_company("UNKNOWN") is None


def test_verify_officers_seeded_company():
    adapter = InMemoryCompaniesHouseAdapter()
    officers = adapter.verify_officers("12345678")
    assert len(officers) >= 1
    assert officers[0]["role"] == "director"


def test_verify_officers_unknown_company():
    adapter = InMemoryCompaniesHouseAdapter()
    officers = adapter.verify_officers("UNKNOWN")
    assert officers == []


def test_get_filing_history_seeded():
    adapter = InMemoryCompaniesHouseAdapter()
    history = adapter.get_filing_history("12345678")
    assert len(history) == 3


def test_get_filing_history_unknown():
    adapter = InMemoryCompaniesHouseAdapter()
    history = adapter.get_filing_history("UNKNOWN")
    assert history == []


def test_check_company_status_active():
    adapter = InMemoryCompaniesHouseAdapter()
    assert adapter.check_company_status("12345678") == "active"


def test_check_company_status_dissolved():
    adapter = InMemoryCompaniesHouseAdapter()
    assert adapter.check_company_status("87654321") == "dissolved"


def test_check_company_status_unknown():
    adapter = InMemoryCompaniesHouseAdapter()
    assert adapter.check_company_status("UNKNOWN") == "unknown"


# --- SEEDED data integrity ---


def test_seeded_has_three_companies():
    assert len(SEEDED) == 3


# --- CompaniesHouseAdapter live stub (BT-002) ---


def test_live_adapter_lookup_raises_not_implemented():
    adapter = CompaniesHouseAdapter()
    with pytest.raises(NotImplementedError, match="BT-002"):
        adapter.lookup_company("12345678")


def test_live_adapter_verify_officers_raises():
    adapter = CompaniesHouseAdapter()
    with pytest.raises(NotImplementedError, match="BT-002"):
        adapter.verify_officers("12345678")


def test_live_adapter_filing_history_raises():
    adapter = CompaniesHouseAdapter()
    with pytest.raises(NotImplementedError, match="BT-002"):
        adapter.get_filing_history("12345678")


def test_live_adapter_check_status_raises():
    adapter = CompaniesHouseAdapter()
    with pytest.raises(NotImplementedError, match="BT-002"):
        adapter.check_company_status("12345678")
