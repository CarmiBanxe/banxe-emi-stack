"""Tests for CompaniesHouseAdapter — Phase 45 (IL-KYB-01)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

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


# --- CompaniesHouseAdapter live (BT-002 resolved) ---


def _ok_http_get(json_body: dict) -> MagicMock:
    """Return a mock http_get that returns a 200 response with the given body."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_body
    mock_resp.raise_for_status.return_value = None
    return MagicMock(return_value=mock_resp)


def _err_http_get(status_code: int) -> MagicMock:
    """Return a mock http_get that raises HTTPStatusError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    error = httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=httpx.Request("GET", "https://api.company-information.service.gov.uk/company/x"),
        response=mock_resp,
    )
    mock = MagicMock()
    mock.return_value.raise_for_status.side_effect = error
    return mock


def test_live_adapter_lookup_company_returns_dict():
    adapter = CompaniesHouseAdapter(
        api_key="test-key",
        http_get=_ok_http_get(
            {
                "company_name": "Banxe Ltd",
                "company_status": "active",
                "type": "ltd",
                "date_of_creation": "2021-03-10",
            }
        ),
    )
    result = adapter.lookup_company("12345678")
    assert result is not None
    assert result["name"] == "Banxe Ltd"
    assert result["status"] == "active"
    assert result["type"] == "ltd"
    assert result["incorporated"] == "2021-03-10"


def test_live_adapter_lookup_company_not_found_returns_none():
    adapter = CompaniesHouseAdapter(api_key="test-key", http_get=_err_http_get(404))
    assert adapter.lookup_company("NOTFOUND") is None


def test_live_adapter_verify_officers_returns_list():
    adapter = CompaniesHouseAdapter(
        api_key="test-key",
        http_get=_ok_http_get({"items": [{"name": "Jane Director", "officer_role": "director"}]}),
    )
    officers = adapter.verify_officers("12345678")
    assert len(officers) == 1
    assert officers[0]["name"] == "Jane Director"
    assert officers[0]["role"] == "director"


def test_live_adapter_verify_officers_empty_items():
    adapter = CompaniesHouseAdapter(api_key="test-key", http_get=_ok_http_get({"items": []}))
    assert adapter.verify_officers("12345678") == []


def test_live_adapter_filing_history_returns_list():
    adapter = CompaniesHouseAdapter(
        api_key="test-key",
        http_get=_ok_http_get(
            {
                "items": [
                    {"date": "2025-01-15", "type": "CS01", "description": "Confirmation statement"}
                ]
            }
        ),
    )
    history = adapter.get_filing_history("12345678")
    assert len(history) == 1
    assert history[0]["type"] == "CS01"
    assert history[0]["date"] == "2025-01-15"


def test_live_adapter_filing_history_empty():
    adapter = CompaniesHouseAdapter(api_key="test-key", http_get=_ok_http_get({"items": []}))
    assert adapter.get_filing_history("12345678") == []


def test_live_adapter_check_status_active():
    adapter = CompaniesHouseAdapter(
        api_key="test-key",
        http_get=_ok_http_get({"company_name": "X", "company_status": "active"}),
    )
    assert adapter.check_company_status("12345678") == "active"


def test_live_adapter_check_status_dissolved():
    adapter = CompaniesHouseAdapter(
        api_key="test-key",
        http_get=_ok_http_get({"company_name": "X", "company_status": "dissolved"}),
    )
    assert adapter.check_company_status("12345678") == "dissolved"


def test_live_adapter_check_status_not_found_returns_unknown():
    adapter = CompaniesHouseAdapter(api_key="test-key", http_get=_err_http_get(404))
    assert adapter.check_company_status("NOTFOUND") == "unknown"


def test_live_adapter_uses_auth_header():
    captured: list[dict] = []

    def capturing_http_get(url: str, **kwargs: object) -> MagicMock:
        captured.append({"url": url, "auth": kwargs.get("auth")})
        resp = MagicMock()
        resp.json.return_value = {"company_name": "X", "company_status": "active"}
        resp.raise_for_status.return_value = None
        return resp

    adapter = CompaniesHouseAdapter(api_key="my-secret-key", http_get=capturing_http_get)
    adapter.lookup_company("12345678")
    assert captured[0]["auth"] == ("my-secret-key", "")
    assert "12345678" in captured[0]["url"]
