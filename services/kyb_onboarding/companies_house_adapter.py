from __future__ import annotations

from collections.abc import Callable
import os
from typing import Any, Protocol

import httpx


class CompaniesHousePort(Protocol):
    def lookup_company(self, company_number: str) -> dict | None: ...
    def verify_officers(self, company_number: str) -> list[dict]: ...
    def get_filing_history(self, company_number: str) -> list[dict]: ...
    def check_company_status(self, company_number: str) -> str: ...


SEEDED: dict[str, dict] = {
    "12345678": {
        "name": "Acme Ltd",
        "status": "active",
        "type": "ltd",
        "incorporated": "2020-01-01",
    },
    "OC123456": {
        "name": "Beta LLP",
        "status": "active",
        "type": "llp",
        "incorporated": "2019-06-15",
    },
    "87654321": {
        "name": "Old Corp",
        "status": "dissolved",
        "type": "ltd",
        "incorporated": "2010-01-01",
    },
}

_STUB_FILINGS = [
    {"date": "2025-01-15", "type": "CS01", "description": "Confirmation statement"},
    {"date": "2024-09-30", "type": "AA", "description": "Annual accounts"},
    {"date": "2024-01-10", "type": "CS01", "description": "Confirmation statement"},
]


class InMemoryCompaniesHouseAdapter:
    def lookup_company(self, company_number: str) -> dict | None:
        return SEEDED.get(company_number)

    def verify_officers(self, company_number: str) -> list[dict]:
        if company_number not in SEEDED:
            return []
        return [{"name": "Director", "role": "director"}]

    def get_filing_history(self, company_number: str) -> list[dict]:
        if company_number not in SEEDED:
            return []
        return _STUB_FILINGS[:3]

    def check_company_status(self, company_number: str) -> str:
        entry = SEEDED.get(company_number)
        if entry is None:
            return "unknown"
        return entry["status"]


class CompaniesHouseAdapter:
    """Live Companies House REST API adapter — BT-002 resolved.

    Auth: HTTP Basic with COMPANIES_HOUSE_API_KEY env var (empty password).
    Base: https://api.company-information.service.gov.uk
    http_get is injectable for testing (defaults to httpx.get in production).
    """

    _BASE_URL = "https://api.company-information.service.gov.uk"

    def __init__(
        self,
        api_key: str | None = None,
        http_get: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("COMPANIES_HOUSE_API_KEY", "")
        self._http_get = http_get

    def _do_get(self, path: str) -> dict:
        fn: Callable[..., Any] = self._http_get or httpx.get  # pragma: no cover
        response = fn(
            f"{self._BASE_URL}{path}",
            auth=(self._api_key, ""),
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def lookup_company(self, company_number: str) -> dict | None:
        try:
            data = self._do_get(f"/company/{company_number}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return {
            "name": data.get("company_name"),
            "status": data.get("company_status"),
            "type": data.get("type"),
            "incorporated": data.get("date_of_creation"),
        }

    def verify_officers(self, company_number: str) -> list[dict]:
        data = self._do_get(f"/company/{company_number}/officers")
        return [
            {"name": item.get("name"), "role": item.get("officer_role")}
            for item in data.get("items", [])
        ]

    def get_filing_history(self, company_number: str) -> list[dict]:
        data = self._do_get(f"/company/{company_number}/filing-history")
        return [
            {
                "date": item.get("date"),
                "type": item.get("type"),
                "description": item.get("description"),
            }
            for item in data.get("items", [])
        ]

    def check_company_status(self, company_number: str) -> str:
        result = self.lookup_company(company_number)
        if result is None:
            return "unknown"
        return result.get("status") or "unknown"
