"""Unit tests for the shared recon_core mechanics (regime-agnostic)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from src.recon_core import (
    BreachDecision,
    BreachEvaluator,
    CoreReconResult,
    ReconAuditEvent,
    absolute_difference,
    emit_recon_audit,
    evaluate_balances,
    signed_difference,
    within_tolerance,
)

# ── compare ──────────────────────────────────────────────────────────────────


class TestCompare:
    def test_signed_difference(self):
        assert signed_difference(Decimal("100"), Decimal("40")) == Decimal("60")
        assert signed_difference(Decimal("40"), Decimal("100")) == Decimal("-60")

    def test_absolute_difference_non_negative(self):
        assert absolute_difference(Decimal("40"), Decimal("100")) == Decimal("60")

    def test_within_tolerance_boundary(self):
        assert within_tolerance(Decimal("100.00"), Decimal("99.99"), Decimal("0.01")) is True
        assert within_tolerance(Decimal("100.00"), Decimal("99.98"), Decimal("0.01")) is False

    def test_within_tolerance_equal(self):
        assert within_tolerance(Decimal("5"), Decimal("5"), Decimal("0")) is True

    def test_float_rejected(self):
        with pytest.raises(TypeError, match="I-01"):
            signed_difference(100.0, Decimal("1"))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="I-01"):
            within_tolerance(Decimal("1"), Decimal("1"), 0.01)  # type: ignore[arg-type]


# ── BreachEvaluator ──────────────────────────────────────────────────────────


class TestBreachEvaluator:
    def test_cass15_path_breaks_above_one_penny(self):
        ev = BreachEvaluator(Decimal("0.01"), "BREAK")
        assert ev.evaluate(Decimal("0.005")).is_breach is False
        assert ev.evaluate(Decimal("0.01")).is_breach is False  # boundary: == is clear
        breach = ev.evaluate(Decimal("0.02"))
        assert breach.is_breach is True
        assert breach.breach_kind == "BREAK"

    def test_cass715_path_escalates_above_100(self):
        ev = BreachEvaluator(Decimal("100"), "HITL")
        assert ev.evaluate(Decimal("100")).is_breach is False  # boundary: == is clear
        breach = ev.evaluate(Decimal("100.01"))
        assert breach.is_breach is True
        assert breach.breach_kind == "HITL"

    def test_clear_decision_has_no_kind(self):
        ev = BreachEvaluator(Decimal("0.01"), "BREAK")
        d = ev.evaluate(Decimal("0.00"))
        assert isinstance(d, BreachDecision)
        assert d.breach_kind is None
        assert d.threshold == Decimal("0.01")

    def test_properties_exposed(self):
        ev = BreachEvaluator(Decimal("100"), "HITL")
        assert ev.threshold == Decimal("100")
        assert ev.breach_kind == "HITL"

    def test_float_threshold_rejected(self):
        with pytest.raises(TypeError, match="I-01"):
            BreachEvaluator(0.01, "BREAK")  # type: ignore[arg-type]

    def test_empty_kind_rejected(self):
        with pytest.raises(ValueError):
            BreachEvaluator(Decimal("0.01"), "")

    def test_float_amount_rejected(self):
        ev = BreachEvaluator(Decimal("0.01"), "BREAK")
        with pytest.raises(TypeError, match="I-01"):
            ev.evaluate(0.02)  # type: ignore[arg-type]


# ── evaluate_balances / CoreReconResult ──────────────────────────────────────


class TestEvaluateBalances:
    def test_signed_difference_preserved_on_shortfall(self):
        ev = BreachEvaluator(Decimal("0.01"), "BREAK")
        res = evaluate_balances(Decimal("49000"), Decimal("50000"), ev)
        assert isinstance(res, CoreReconResult)
        assert res.difference == Decimal("-1000")  # signed: internal < external
        assert res.abs_difference == Decimal("1000")
        assert res.is_breach is True
        assert res.breach_kind == "BREAK"

    def test_within_tolerance_no_breach(self):
        ev = BreachEvaluator(Decimal("0.01"), "BREAK")
        res = evaluate_balances(Decimal("50000.00"), Decimal("49999.99"), ev)
        assert res.is_breach is False
        assert res.breach_kind is None
        assert res.threshold == Decimal("0.01")


# ── audit ────────────────────────────────────────────────────────────────────


class TestAudit:
    def test_from_magnitude_serialises_money_to_string(self):
        ev = ReconAuditEvent.from_magnitude(
            regime="CASS15",
            recon_ref="2026-04-13",
            is_breach=True,
            breach_kind="BREAK",
            amount=Decimal("0.02"),
            threshold=Decimal("0.01"),
        )
        assert ev.amount_gbp == "0.02"
        assert ev.threshold_gbp == "0.01"
        assert isinstance(ev.amount_gbp, str)
        # R-SEC: no raw balances on the event, only magnitude + ref
        assert ev.recon_ref == "2026-04-13"

    def test_emit_without_sink_returns_event(self):
        ev = ReconAuditEvent.from_magnitude(
            regime="CASS7.15",
            recon_ref="r1",
            is_breach=False,
            breach_kind=None,
            amount=Decimal("0"),
            threshold=Decimal("100"),
        )
        assert emit_recon_audit(ev) is ev

    def test_emit_routes_to_sink(self):
        captured: list[ReconAuditEvent] = []

        class _Sink:
            def emit(self, event: ReconAuditEvent) -> None:
                captured.append(event)

        ev = ReconAuditEvent.from_magnitude(
            regime="CASS15",
            recon_ref="r2",
            is_breach=True,
            breach_kind="BREAK",
            amount=Decimal("5"),
            threshold=Decimal("0.01"),
        )
        emit_recon_audit(ev, sink=_Sink())
        assert captured == [ev]

    def test_emit_fail_open_on_sink_error(self):
        class _BadSink:
            def emit(self, event: ReconAuditEvent) -> None:
                raise RuntimeError("clickhouse down")

        ev = ReconAuditEvent.from_magnitude(
            regime="CASS15",
            recon_ref="r3",
            is_breach=True,
            breach_kind="BREAK",
            amount=Decimal("5"),
            threshold=Decimal("0.01"),
        )
        # must not raise — audit emission is fail-open
        assert emit_recon_audit(ev, sink=_BadSink()) is ev
