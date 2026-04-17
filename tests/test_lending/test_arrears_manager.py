"""
tests/test_lending/test_arrears_manager.py — Unit tests for ArrearsManager
IL-LCE-01 | Phase 25

18 tests covering each stage boundary, get_arrears_history, and Decimal invariants.
"""

from __future__ import annotations

from decimal import Decimal

from services.lending.arrears_manager import ArrearsManager
from services.lending.models import ArrearStage

# ── get_stage boundaries ───────────────────────────────────────────────────


def test_stage_0_days_is_current() -> None:
    assert ArrearsManager.get_stage(0) == ArrearStage.CURRENT


def test_stage_1_day_is_days_1_30() -> None:
    assert ArrearsManager.get_stage(1) == ArrearStage.DAYS_1_30


def test_stage_30_days_is_days_1_30() -> None:
    assert ArrearsManager.get_stage(30) == ArrearStage.DAYS_1_30


def test_stage_31_days_is_days_31_60() -> None:
    assert ArrearsManager.get_stage(31) == ArrearStage.DAYS_31_60


def test_stage_60_days_is_days_31_60() -> None:
    assert ArrearsManager.get_stage(60) == ArrearStage.DAYS_31_60


def test_stage_61_days_is_days_61_90() -> None:
    assert ArrearsManager.get_stage(61) == ArrearStage.DAYS_61_90


def test_stage_90_days_is_days_61_90() -> None:
    assert ArrearsManager.get_stage(90) == ArrearStage.DAYS_61_90


def test_stage_91_days_is_default_90_plus() -> None:
    assert ArrearsManager.get_stage(91) == ArrearStage.DEFAULT_90_PLUS


def test_stage_200_days_is_default_90_plus() -> None:
    assert ArrearsManager.get_stage(200) == ArrearStage.DEFAULT_90_PLUS


# ── check_arrears ──────────────────────────────────────────────────────────


def test_check_arrears_creates_record() -> None:
    mgr = ArrearsManager()
    record = mgr.check_arrears("app-1", "cust-1", 0, Decimal("500"))
    assert record.application_id == "app-1"
    assert record.customer_id == "cust-1"


def test_check_arrears_outstanding_amount_is_decimal() -> None:
    mgr = ArrearsManager()
    record = mgr.check_arrears("app-1", "cust-1", 45, Decimal("1250.00"))
    assert isinstance(record.outstanding_amount, Decimal)
    assert record.outstanding_amount == Decimal("1250.00")


def test_check_arrears_stage_classification_correct() -> None:
    mgr = ArrearsManager()
    record = mgr.check_arrears("app-1", "cust-1", 35, Decimal("500"))
    assert record.stage == ArrearStage.DAYS_31_60


def test_check_arrears_days_overdue_stored() -> None:
    mgr = ArrearsManager()
    record = mgr.check_arrears("app-1", "cust-1", 75, Decimal("300"))
    assert record.days_overdue == 75


def test_check_arrears_default_stage_for_91_days() -> None:
    mgr = ArrearsManager()
    record = mgr.check_arrears("app-1", "cust-1", 91, Decimal("2000"))
    assert record.stage == ArrearStage.DEFAULT_90_PLUS


# ── get_arrears_history ────────────────────────────────────────────────────


def test_get_arrears_history_empty_for_new_application() -> None:
    mgr = ArrearsManager()
    history = mgr.get_arrears_history("app-new")
    assert history == []


def test_get_arrears_history_returns_all_records() -> None:
    mgr = ArrearsManager()
    for days in [0, 15, 45, 75, 95]:
        mgr.check_arrears("app-1", "cust-1", days, Decimal("500"))
    history = mgr.get_arrears_history("app-1")
    assert len(history) == 5


def test_get_arrears_history_filters_by_application() -> None:
    mgr = ArrearsManager()
    mgr.check_arrears("app-1", "cust-1", 30, Decimal("500"))
    mgr.check_arrears("app-2", "cust-2", 30, Decimal("500"))
    history_1 = mgr.get_arrears_history("app-1")
    assert len(history_1) == 1
    assert history_1[0].application_id == "app-1"
