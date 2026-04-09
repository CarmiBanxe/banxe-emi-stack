"""
services/case_management/case_factory.py — Case management adapter factory
IL-059 | banxe-emi-stack

CASE_ADAPTER=mock    → MockCaseAdapter (default)
CASE_ADAPTER=marble  → MarbleAdapter (self-hosted GMKtec :5002)
"""

from __future__ import annotations

import os

from services.case_management.case_port import CaseManagementPort


def get_case_adapter() -> CaseManagementPort:
    """
    Factory: returns correct adapter based on CASE_ADAPTER env var.

    CASE_ADAPTER=mock   → MockCaseAdapter (default, always available)
    CASE_ADAPTER=marble → MarbleAdapter (requires MARBLE_URL + MARBLE_API_KEY + MARBLE_INBOX_ID)
    """
    adapter_name = os.environ.get("CASE_ADAPTER", "mock").lower()
    if adapter_name == "marble":
        from services.case_management.marble_adapter import MarbleAdapter

        return MarbleAdapter()
    from services.case_management.mock_case_adapter import MockCaseAdapter

    return MockCaseAdapter()
