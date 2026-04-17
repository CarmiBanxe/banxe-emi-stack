"""
tests/test_lending/test_provisioning_engine.py — Unit tests for ProvisioningEngine
IL-LCE-01 | Phase 25

18 tests covering ECL for each IFRS stage, Decimal invariants, and ECL formula.
"""

from __future__ import annotations

from decimal import Decimal

from services.lending.models import IFRSStage
from services.lending.provisioning_engine import ProvisioningEngine

# ── Stage 1 ECL ────────────────────────────────────────────────────────────


def test_stage_1_pd_is_1_percent() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("10000"))
    assert record.probability_of_default == Decimal("0.01")


def test_stage_1_ecl_formula() -> None:
    engine = ProvisioningEngine()
    # ECL = 10000 * 0.01 * 0.45 = 45
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("10000"))
    assert record.ecl_amount == Decimal("45.0000")


def test_stage_1_ecl_is_decimal() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("10000"))
    assert isinstance(record.ecl_amount, Decimal)


# ── Stage 2 ECL ────────────────────────────────────────────────────────────


def test_stage_2_pd_is_15_percent() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_2, Decimal("10000"))
    assert record.probability_of_default == Decimal("0.15")


def test_stage_2_ecl_formula() -> None:
    engine = ProvisioningEngine()
    # ECL = 10000 * 0.15 * 0.45 = 675
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_2, Decimal("10000"))
    assert record.ecl_amount == Decimal("675.000")


def test_stage_2_ecl_is_decimal() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_2, Decimal("10000"))
    assert isinstance(record.ecl_amount, Decimal)


# ── Stage 3 ECL ────────────────────────────────────────────────────────────


def test_stage_3_pd_is_90_percent() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_3, Decimal("10000"))
    assert record.probability_of_default == Decimal("0.90")


def test_stage_3_ecl_formula() -> None:
    engine = ProvisioningEngine()
    # ECL = 10000 * 0.90 * 0.65 = 5850
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_3, Decimal("10000"))
    assert record.ecl_amount == Decimal("5850.000")


def test_stage_3_ecl_is_decimal() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_3, Decimal("10000"))
    assert isinstance(record.ecl_amount, Decimal)


def test_stage_3_lgd_is_65_percent() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_3, Decimal("1000"))
    expected = Decimal("1000") * Decimal("0.90") * Decimal("0.65")
    assert record.ecl_amount == expected


def test_exposure_at_default_stored_correctly() -> None:
    engine = ProvisioningEngine()
    record = engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("7500"))
    assert record.exposure_at_default == Decimal("7500")


def test_ecl_proportional_to_exposure() -> None:
    engine = ProvisioningEngine()
    r1 = engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("1000"))
    r2 = engine.compute_ecl("app-2", IFRSStage.STAGE_1, Decimal("2000"))
    assert r2.ecl_amount == r1.ecl_amount * 2


def test_stage_1_ecl_less_than_stage_2() -> None:
    engine = ProvisioningEngine()
    r1 = engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("10000"))
    r2 = engine.compute_ecl("app-2", IFRSStage.STAGE_2, Decimal("10000"))
    assert r1.ecl_amount < r2.ecl_amount


def test_stage_2_ecl_less_than_stage_3() -> None:
    engine = ProvisioningEngine()
    r2 = engine.compute_ecl("app-1", IFRSStage.STAGE_2, Decimal("10000"))
    r3 = engine.compute_ecl("app-2", IFRSStage.STAGE_3, Decimal("10000"))
    assert r2.ecl_amount < r3.ecl_amount


def test_provision_summary_returns_total_ecl() -> None:
    engine = ProvisioningEngine()
    engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("10000"))
    engine.compute_ecl("app-1", IFRSStage.STAGE_2, Decimal("5000"))
    summary = engine.get_provision_summary("app-1")
    assert "total_ecl" in summary
    assert isinstance(summary["total_ecl"], str)


def test_provision_summary_record_count() -> None:
    engine = ProvisioningEngine()
    engine.compute_ecl("app-1", IFRSStage.STAGE_1, Decimal("10000"))
    engine.compute_ecl("app-1", IFRSStage.STAGE_3, Decimal("5000"))
    summary = engine.get_provision_summary("app-1")
    assert summary["record_count"] == 2


def test_provision_summary_empty_application() -> None:
    engine = ProvisioningEngine()
    summary = engine.get_provision_summary("app-empty")
    assert summary["total_ecl"] == "0"
    assert summary["record_count"] == 0
