"""
tests/test_lending/test_repayment_engine.py — Unit tests for RepaymentEngine
IL-LCE-01 | Phase 25

22 tests covering annuity schedule, linear schedule, early repayment penalty,
process_payment, and no-float invariant.
"""

from __future__ import annotations

from decimal import Decimal

from services.lending.models import RepaymentType
from services.lending.repayment_engine import RepaymentEngine


def test_annuity_schedule_has_correct_installment_count() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 12, RepaymentType.ANNUITY
    )
    assert len(schedule.installments) == 12


def test_annuity_schedule_total_greater_than_principal() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 12, RepaymentType.ANNUITY
    )
    assert schedule.total_amount > Decimal("1200")


def test_annuity_schedule_total_is_decimal() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 12, RepaymentType.ANNUITY
    )
    assert isinstance(schedule.total_amount, Decimal)


def test_annuity_installments_payment_field_is_string() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1000"), Decimal("0.06"), 6, RepaymentType.ANNUITY
    )
    for inst in schedule.installments:
        assert isinstance(inst["payment"], str)
        # Must be parseable as Decimal, not float
        Decimal(inst["payment"])


def test_annuity_installments_balance_field_is_string() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1000"), Decimal("0.06"), 6, RepaymentType.ANNUITY
    )
    for inst in schedule.installments:
        assert isinstance(inst["balance"], str)


def test_annuity_installments_no_float_values() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1000"), Decimal("0.06"), 6, RepaymentType.ANNUITY
    )
    for inst in schedule.installments:
        for key in ("payment", "principal", "interest", "balance"):
            assert not isinstance(inst[key], float), f"{key} must not be float"


def test_annuity_last_balance_is_zero_or_near() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1000"), Decimal("0.05"), 12, RepaymentType.ANNUITY
    )
    last_balance = Decimal(schedule.installments[-1]["balance"])
    assert last_balance >= Decimal("0")
    assert last_balance < Decimal("1")  # should be effectively cleared


def test_annuity_monthly_payment_consistent() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("5000"), Decimal("0.0499"), 12, RepaymentType.ANNUITY
    )
    # All non-last monthly payments should be roughly equal
    payments = [Decimal(inst["payment"]) for inst in schedule.installments[:-1]]
    assert max(payments) - min(payments) < Decimal("1")


def test_annuity_installments_have_all_required_keys() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1000"), Decimal("0.05"), 6, RepaymentType.ANNUITY
    )
    required = {"month", "payment", "principal", "interest", "balance"}
    for inst in schedule.installments:
        assert required <= set(inst.keys())


def test_linear_schedule_has_correct_installment_count() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 12, RepaymentType.LINEAR
    )
    assert len(schedule.installments) == 12


def test_linear_schedule_total_is_decimal() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 12, RepaymentType.LINEAR
    )
    assert isinstance(schedule.total_amount, Decimal)


def test_linear_schedule_installments_are_strings() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 6, RepaymentType.LINEAR
    )
    for inst in schedule.installments:
        assert isinstance(inst["payment"], str)


def test_linear_schedule_payments_decrease() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 12, RepaymentType.LINEAR
    )
    payments = [Decimal(inst["payment"]) for inst in schedule.installments]
    # Linear: payments should decrease over time (each month less interest)
    assert payments[0] >= payments[-1]


def test_linear_schedule_total_greater_than_principal() -> None:
    engine = RepaymentEngine()
    schedule = engine.generate_schedule(
        "app-1", Decimal("1200"), Decimal("0.12"), 12, RepaymentType.LINEAR
    )
    assert schedule.total_amount > Decimal("1200")


def test_process_payment_returns_processed() -> None:
    engine = RepaymentEngine()
    result = engine.process_payment("app-1", Decimal("500"))
    assert result["status"] == "processed"


def test_process_payment_amount_is_string() -> None:
    engine = RepaymentEngine()
    result = engine.process_payment("app-1", Decimal("250.50"))
    assert isinstance(result["amount"], str)
    assert result["amount"] == "250.50"


def test_process_payment_application_id_in_result() -> None:
    engine = RepaymentEngine()
    result = engine.process_payment("app-99", Decimal("100"))
    assert result["application_id"] == "app-99"


def test_early_repayment_penalty_is_decimal() -> None:
    engine = RepaymentEngine()
    penalty = engine.calculate_early_repayment_penalty("app-1", 6, Decimal("10000"))
    assert isinstance(penalty, Decimal)


def test_early_repayment_penalty_1_percent_annualised() -> None:
    engine = RepaymentEngine()
    # 12 months remaining: penalty = 10000 * 0.01 * (12/12) = 100
    penalty = engine.calculate_early_repayment_penalty("app-1", 12, Decimal("10000"))
    assert penalty == Decimal("100.00")


def test_early_repayment_penalty_6_months() -> None:
    engine = RepaymentEngine()
    # 6 months: penalty = 10000 * 0.01 * (6/12) = 50
    penalty = engine.calculate_early_repayment_penalty("app-1", 6, Decimal("10000"))
    assert penalty == Decimal("50.00")


def test_get_schedule_returns_none_if_not_generated() -> None:
    engine = RepaymentEngine()
    assert engine.get_schedule("app-unknown") is None


def test_get_schedule_returns_stored_schedule() -> None:
    engine = RepaymentEngine()
    engine.generate_schedule("app-1", Decimal("1000"), Decimal("0.05"), 6, RepaymentType.ANNUITY)
    schedule = engine.get_schedule("app-1")
    assert schedule is not None
    assert schedule.application_id == "app-1"
