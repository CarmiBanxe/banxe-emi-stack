"""
tests/test_beneficiary_management/test_beneficiary_agent.py — facade
IL-BPM-01 | Phase 34 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.beneficiary_management.beneficiary_agent import BeneficiaryAgent
from services.beneficiary_management.models import BeneficiaryStatus, BeneficiaryType


def _agent() -> BeneficiaryAgent:
    return BeneficiaryAgent()


class TestAddBeneficiary:
    def test_returns_beneficiary_id(self) -> None:
        agent = _agent()
        result = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John Smith")
        assert result["beneficiary_id"] != ""

    def test_status_pending(self) -> None:
        agent = _agent()
        result = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John Smith")
        assert result["status"] == BeneficiaryStatus.PENDING.value

    def test_blocked_jurisdiction_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="blocked jurisdiction"):
            agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Test", country_code="RU")

    def test_name_preserved(self) -> None:
        agent = _agent()
        result = agent.add_beneficiary("c-1", BeneficiaryType.BUSINESS, "Acme Corp")
        assert result["name"] == "Acme Corp"


class TestScreenBeneficiary:
    def test_no_match_for_clean(self) -> None:
        agent = _agent()
        r = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Jane Doe")
        result = agent.screen_beneficiary(r["beneficiary_id"])
        assert result["result"] == "NO_MATCH"

    def test_partial_match_for_high_risk_name(self) -> None:
        agent = _agent()
        r = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "test_sanctioned")
        result = agent.screen_beneficiary(r["beneficiary_id"])
        assert result["result"] == "PARTIAL_MATCH"

    def test_unknown_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="not found"):
            agent.screen_beneficiary("nonexistent")


class TestDeleteBeneficiary:
    def test_always_hitl_required(self) -> None:
        agent = _agent()
        r = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John")
        result = agent.delete_beneficiary(r["beneficiary_id"])
        assert result["status"] == "HITL_REQUIRED"

    def test_unknown_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="not found"):
            agent.delete_beneficiary("nonexistent")


class TestRoutePayment:
    def test_fps_for_gbp_gb(self) -> None:
        agent = _agent()
        r = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John", country_code="GB")
        result = agent.route_payment(r["beneficiary_id"], Decimal("100.00"), "GBP")
        assert result["rail"] == "FPS"

    def test_swift_for_usd(self) -> None:
        agent = _agent()
        r = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "US Person", country_code="US")
        result = agent.route_payment(r["beneficiary_id"], Decimal("100.00"), "USD")
        assert result["rail"] == "SWIFT"

    def test_unknown_beneficiary_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="not found"):
            agent.route_payment("nonexistent", Decimal("100.00"), "GBP")


class TestCheckPayee:
    def test_match_for_exact_name(self) -> None:
        agent = _agent()
        r = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John Smith")
        result = agent.check_payee(r["beneficiary_id"], "John Smith")
        assert result["result"] == "MATCH"

    def test_no_match_for_different_name(self) -> None:
        agent = _agent()
        r = agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "John Smith")
        result = agent.check_payee(r["beneficiary_id"], "Alice Brown")
        assert result["result"] == "NO_MATCH"

    def test_unknown_raises(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="not found"):
            agent.check_payee("nonexistent", "name")


class TestListBeneficiaries:
    def test_empty_for_unknown_customer(self) -> None:
        agent = _agent()
        result = agent.list_beneficiaries("c-unknown")
        assert result["count"] == 0

    def test_count_matches_added(self) -> None:
        agent = _agent()
        agent.add_beneficiary("c-1", BeneficiaryType.INDIVIDUAL, "Alice")
        agent.add_beneficiary("c-1", BeneficiaryType.BUSINESS, "Acme")
        result = agent.list_beneficiaries("c-1")
        assert result["count"] == 2
