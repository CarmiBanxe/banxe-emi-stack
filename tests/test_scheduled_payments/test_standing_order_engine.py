"""
tests/test_scheduled_payments/test_standing_order_engine.py — Unit tests for StandingOrderEngine
IL-SOD-01 | Phase 32 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.scheduled_payments.models import PaymentFrequency
from services.scheduled_payments.standing_order_engine import StandingOrderEngine


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture()
def engine() -> StandingOrderEngine:
    return StandingOrderEngine()


def _create(engine: StandingOrderEngine, amount: str = "100.00") -> str:
    result = engine.create_standing_order(
        customer_id="cust-1",
        from_account="acc-from",
        to_account="acc-to",
        amount=Decimal(amount),
        frequency=PaymentFrequency.MONTHLY,
        start_date=_now(),
    )
    return result["so_id"]


# ── create_standing_order ──────────────────────────────────────────────────────


def test_create_returns_so_id(engine: StandingOrderEngine) -> None:
    result = engine.create_standing_order(
        "c1", "fa", "ta", Decimal("100.00"), PaymentFrequency.MONTHLY, _now()
    )
    assert result["so_id"] != ""


def test_create_status_active(engine: StandingOrderEngine) -> None:
    result = engine.create_standing_order(
        "c1", "fa", "ta", Decimal("100.00"), PaymentFrequency.MONTHLY, _now()
    )
    assert result["status"] == "ACTIVE"


def test_create_returns_amount_as_string(engine: StandingOrderEngine) -> None:
    result = engine.create_standing_order(
        "c1", "fa", "ta", Decimal("250.00"), PaymentFrequency.WEEKLY, _now()
    )
    assert result["amount"] == "250.00"


def test_create_zero_amount_raises(engine: StandingOrderEngine) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        engine.create_standing_order(
            "c1", "fa", "ta", Decimal("0"), PaymentFrequency.MONTHLY, _now()
        )


def test_create_negative_amount_raises(engine: StandingOrderEngine) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        engine.create_standing_order(
            "c1", "fa", "ta", Decimal("-10"), PaymentFrequency.MONTHLY, _now()
        )


def test_create_returns_next_execution_date(engine: StandingOrderEngine) -> None:
    start = _now()
    result = engine.create_standing_order(
        "c1", "fa", "ta", Decimal("100.00"), PaymentFrequency.MONTHLY, start
    )
    assert result["next_execution_date"] == start.isoformat()


# ── cancel_standing_order ──────────────────────────────────────────────────────


def test_cancel_returns_cancelled_status(engine: StandingOrderEngine) -> None:
    so_id = _create(engine)
    result = engine.cancel_standing_order(so_id)
    assert result["status"] == "CANCELLED"


def test_cancel_not_found_raises(engine: StandingOrderEngine) -> None:
    with pytest.raises(ValueError, match="not found"):
        engine.cancel_standing_order("nonexistent")


def test_cancel_already_cancelled_raises(engine: StandingOrderEngine) -> None:
    so_id = _create(engine)
    engine.cancel_standing_order(so_id)
    with pytest.raises(ValueError, match="already cancelled"):
        engine.cancel_standing_order(so_id)


# ── pause / resume ─────────────────────────────────────────────────────────────


def test_pause_active_returns_paused(engine: StandingOrderEngine) -> None:
    so_id = _create(engine)
    result = engine.pause_standing_order(so_id)
    assert result["status"] == "PAUSED"


def test_pause_non_active_raises(engine: StandingOrderEngine) -> None:
    so_id = _create(engine)
    engine.cancel_standing_order(so_id)
    with pytest.raises(ValueError, match="ACTIVE"):
        engine.pause_standing_order(so_id)


def test_resume_paused_returns_active(engine: StandingOrderEngine) -> None:
    so_id = _create(engine)
    engine.pause_standing_order(so_id)
    result = engine.resume_standing_order(so_id)
    assert result["status"] == "ACTIVE"


def test_resume_non_paused_raises(engine: StandingOrderEngine) -> None:
    so_id = _create(engine)
    with pytest.raises(ValueError, match="PAUSED"):
        engine.resume_standing_order(so_id)


# ── advance_next_execution_date ────────────────────────────────────────────────


def test_advance_weekly_adds_7_days(engine: StandingOrderEngine) -> None:
    start = _now()
    result = engine.create_standing_order(
        "c1", "fa", "ta", Decimal("100.00"), PaymentFrequency.WEEKLY, start
    )
    so_id = result["so_id"]
    adv = engine.advance_next_execution_date(so_id)
    expected = start + timedelta(days=7)
    assert adv["next_execution_date"] == expected.isoformat()


def test_advance_monthly_adds_30_days(engine: StandingOrderEngine) -> None:
    start = _now()
    so_id = engine.create_standing_order(
        "c1", "fa", "ta", Decimal("100.00"), PaymentFrequency.MONTHLY, start
    )["so_id"]
    adv = engine.advance_next_execution_date(so_id)
    expected = start + timedelta(days=30)
    assert adv["next_execution_date"] == expected.isoformat()


def test_advance_past_end_date_completes(engine: StandingOrderEngine) -> None:
    start = _now()
    end = start + timedelta(days=5)
    so_id = engine.create_standing_order(
        "c1", "fa", "ta", Decimal("100.00"), PaymentFrequency.MONTHLY, start, end_date=end
    )["so_id"]
    adv = engine.advance_next_execution_date(so_id)
    assert adv["status"] == "COMPLETED"


# ── list_standing_orders ───────────────────────────────────────────────────────


def test_list_returns_correct_count(engine: StandingOrderEngine) -> None:
    engine.create_standing_order(
        "cust-list", "fa", "ta", Decimal("100.00"), PaymentFrequency.MONTHLY, _now()
    )
    engine.create_standing_order(
        "cust-list", "fa", "ta", Decimal("200.00"), PaymentFrequency.WEEKLY, _now()
    )
    result = engine.list_standing_orders("cust-list")
    assert result["count"] == 2


def test_list_returns_empty_for_new_customer(engine: StandingOrderEngine) -> None:
    result = engine.list_standing_orders("nobody")
    assert result["count"] == 0
