from __future__ import annotations

from typing import Protocol


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
    """Live API client stub — BT-002 BLOCKED in prod."""

    def __init__(self, api_key: str = "PLACEHOLDER_BT002") -> None:
        self._api_key = api_key

    def lookup_company(self, company_number: str) -> dict | None:
        raise NotImplementedError("BT-002: Companies House live API not yet integrated")

    def verify_officers(self, company_number: str) -> list[dict]:
        raise NotImplementedError("BT-002: Companies House live API not yet integrated")

    def get_filing_history(self, company_number: str) -> list[dict]:
        raise NotImplementedError("BT-002: Companies House live API not yet integrated")

    def check_company_status(self, company_number: str) -> str:
        raise NotImplementedError("BT-002: Companies House live API not yet integrated")
