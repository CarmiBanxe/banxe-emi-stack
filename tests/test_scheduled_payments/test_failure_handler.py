"""
tests/test_scheduled_payments/test_failure_handler.py — Unit tests for FailureHandler
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.scheduled_payments.failure_handler import FailureHandler
from services.scheduled_payments.models import FailureCode, PaymentType


@pytest.fixture()
def handler() -> FailureHandler:
    return FailureHandler()


# ── record_failure ─────────────────────────────────────────────────────────────


def test_record_failure_returns_failure_id(handler: FailureHandler) -> None:
    result = handler.record_failure(
        "so-1", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "No funds", "cust-1"
    )
    assert result["failure_id"] != ""


def test_record_failure_returns_retry_count(handler: FailureHandler) -> None:
    result = handler.record_failure(
        "so-1", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "No funds", "cust-1"
    )
    assert result["retry_count"] == 1


def test_record_failure_second_retry(handler: FailureHandler) -> None:
    handler.record_failure(
        "so-retry", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "No funds", "cust-1"
    )
    result = handler.record_failure(
        "so-retry",
        PaymentType.STANDING_ORDER,
        FailureCode.INSUFFICIENT_FUNDS,
        "Still no funds",
        "cust-1",
    )
    assert result["retry_count"] == 2


def test_record_failure_max_retries_flag(handler: FailureHandler) -> None:
    handler.record_failure(
        "so-max", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "r1", "c1"
    )
    handler.record_failure(
        "so-max", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "r2", "c1"
    )
    result = handler.record_failure(
        "so-max", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "r3", "c1"
    )
    assert result["max_retries_reached"] is True


def test_record_failure_first_has_next_retry_at(handler: FailureHandler) -> None:
    result = handler.record_failure(
        "so-next", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "Funds", "cust-1"
    )
    assert result["next_retry_at"] is not None


def test_record_failure_max_retries_no_next_retry(handler: FailureHandler) -> None:
    for i in range(3):
        result = handler.record_failure(
            "so-done", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, f"r{i}", "c1"
        )
    assert result["next_retry_at"] is None


def test_record_failure_returns_payment_id(handler: FailureHandler) -> None:
    result = handler.record_failure(
        "so-pid", PaymentType.DIRECT_DEBIT, FailureCode.ACCOUNT_CLOSED, "Closed", "c1"
    )
    assert result["payment_id"] == "so-pid"


def test_record_failure_append_only(handler: FailureHandler) -> None:
    for _ in range(3):
        handler.record_failure(
            "so-append",
            PaymentType.STANDING_ORDER,
            FailureCode.INSUFFICIENT_FUNDS,
            "No funds",
            "c1",
        )
    summary = handler.get_failure_summary("so-append")
    assert summary["total_failures"] == 3


# ── get_failure_summary ────────────────────────────────────────────────────────


def test_get_failure_summary_returns_payment_id(handler: FailureHandler) -> None:
    handler.record_failure(
        "so-sum", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "No funds", "c1"
    )
    result = handler.get_failure_summary("so-sum")
    assert result["payment_id"] == "so-sum"


def test_get_failure_summary_empty_for_new_payment(handler: FailureHandler) -> None:
    result = handler.get_failure_summary("nobody")
    assert result["total_failures"] == 0


def test_get_failure_summary_returns_last_failure_code(handler: FailureHandler) -> None:
    handler.record_failure(
        "so-code", PaymentType.STANDING_ORDER, FailureCode.ACCOUNT_BLOCKED, "Blocked", "c1"
    )
    result = handler.get_failure_summary("so-code")
    assert result["last_failure_code"] == "ACCOUNT_BLOCKED"


def test_get_failure_summary_max_retries_reached(handler: FailureHandler) -> None:
    for i in range(3):
        handler.record_failure(
            "so-mr", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, f"r{i}", "c1"
        )
    result = handler.get_failure_summary("so-mr")
    assert result["max_retries_reached"] is True


# ── get_customer_failures ──────────────────────────────────────────────────────


def test_get_customer_failures_empty_for_new_customer(handler: FailureHandler) -> None:
    result = handler.get_customer_failures("nobody")
    assert result["count"] == 0


def test_get_customer_failures_returns_count(handler: FailureHandler) -> None:
    handler.record_failure(
        "so-cf1", PaymentType.STANDING_ORDER, FailureCode.INSUFFICIENT_FUNDS, "No funds", "cust-cf"
    )
    handler.record_failure(
        "so-cf2", PaymentType.DIRECT_DEBIT, FailureCode.ACCOUNT_CLOSED, "Closed", "cust-cf"
    )
    result = handler.get_customer_failures("cust-cf")
    assert result["count"] == 2


def test_get_customer_failures_returns_customer_id(handler: FailureHandler) -> None:
    handler.record_failure(
        "so-cid", PaymentType.STANDING_ORDER, FailureCode.INVALID_ACCOUNT, "Invalid", "cust-id-test"
    )
    result = handler.get_customer_failures("cust-id-test")
    assert result["customer_id"] == "cust-id-test"
