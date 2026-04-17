"""
tests/test_lending/test_lending_agent.py — Unit tests for LendingAgent
IL-LCE-01 | Phase 25

16 tests covering the full apply flow, HITL_REQUIRED, schedule retrieval,
arrears checks, and provision reports.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.lending.lending_agent import LendingAgent


def _agent() -> LendingAgent:
    return LendingAgent()


# ── apply_for_loan ─────────────────────────────────────────────────────────


def test_apply_returns_hitl_required() -> None:
    agent = _agent()
    result = agent.apply_for_loan("cust-1", "product-001", "1000", 6)
    assert result["status"] == "HITL_REQUIRED"


def test_apply_returns_application_id() -> None:
    agent = _agent()
    result = agent.apply_for_loan("cust-1", "product-001", "1000", 6)
    assert "application_id" in result
    assert result["application_id"]


def test_apply_returns_credit_score_as_string() -> None:
    agent = _agent()
    result = agent.apply_for_loan("cust-1", "product-001", "1000", 6)
    assert isinstance(result["credit_score"], str)
    # Must be parseable as Decimal
    Decimal(result["credit_score"])


def test_apply_returns_outcome() -> None:
    agent = _agent()
    result = agent.apply_for_loan("cust-1", "product-001", "1000", 6)
    assert result["outcome"] in ("APPROVED", "DECLINED", "REFERRED")


def test_apply_invalid_product_raises() -> None:
    agent = _agent()
    with pytest.raises(ValueError):
        agent.apply_for_loan("cust-1", "product-999", "1000", 6)


def test_apply_amount_exceeds_max_raises() -> None:
    agent = _agent()
    with pytest.raises(ValueError):
        agent.apply_for_loan("cust-1", "product-001", "99999", 6)


# ── get_repayment_schedule ─────────────────────────────────────────────────


def test_get_schedule_for_valid_application() -> None:
    agent = _agent()
    result = agent.apply_for_loan("cust-1", "product-001", "1000", 6)
    app_id = result["application_id"]
    schedule = agent.get_repayment_schedule(app_id)
    assert "installments" in schedule
    assert len(schedule["installments"]) == 6


def test_get_schedule_unknown_application_returns_error() -> None:
    agent = _agent()
    result = agent.get_repayment_schedule("app-ghost")
    assert "error" in result


def test_get_schedule_amounts_are_strings() -> None:
    agent = _agent()
    result = agent.apply_for_loan("cust-1", "product-001", "1000", 6)
    app_id = result["application_id"]
    schedule = agent.get_repayment_schedule(app_id)
    assert isinstance(schedule["total_amount"], str)
    assert isinstance(schedule["monthly_payment"], str)


# ── check_arrears_status ───────────────────────────────────────────────────


def test_check_arrears_status_returns_stage() -> None:
    agent = _agent()
    result = agent.check_arrears_status("app-1", "cust-1", 0, "500")
    assert result["stage"] == "CURRENT"


def test_check_arrears_status_days_31_stage() -> None:
    agent = _agent()
    result = agent.check_arrears_status("app-1", "cust-1", 31, "500")
    assert result["stage"] == "DAYS_31_60"


def test_check_arrears_outstanding_is_string() -> None:
    agent = _agent()
    result = agent.check_arrears_status("app-1", "cust-1", 15, "1250.00")
    assert isinstance(result["outstanding_amount"], str)
    assert result["outstanding_amount"] == "1250.00"


# ── generate_provision_report ──────────────────────────────────────────────


def test_provision_report_stage_1_ecl() -> None:
    agent = _agent()
    result = agent.generate_provision_report("app-1", "STAGE_1", "10000")
    assert "ecl_amount" in result
    assert result["ifrs_stage"] == "STAGE_1"


def test_provision_report_amounts_are_strings() -> None:
    agent = _agent()
    result = agent.generate_provision_report("app-1", "STAGE_3", "5000")
    assert isinstance(result["ecl_amount"], str)
    assert isinstance(result["exposure_at_default"], str)
    # Must be valid Decimal strings
    Decimal(result["ecl_amount"])
    Decimal(result["exposure_at_default"])


def test_provision_report_invalid_stage_raises() -> None:
    agent = _agent()
    with pytest.raises(ValueError):
        agent.generate_provision_report("app-1", "STAGE_99", "10000")
