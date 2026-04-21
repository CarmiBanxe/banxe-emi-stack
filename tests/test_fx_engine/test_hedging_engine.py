"""
Tests for FX Hedging Engine.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: net_exposure Decimal (I-22), HITL threshold (I-27), I-24 append, EOD snapshot
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fx_engine.hedging_engine import HEDGE_ALERT_THRESHOLD_GBP, HedgingEngine
from services.fx_engine.models import HITLProposal, InMemoryHedgeStore


@pytest.fixture
def engine():
    return HedgingEngine(store=InMemoryHedgeStore())


class TestRecordPosition:
    def test_record_position_basic(self, engine):
        pos = engine.record_position("GBP/EUR", Decimal("100000"), Decimal("80000"))
        assert pos.currency_pair == "GBP/EUR"
        assert pos.net_exposure == Decimal("20000")

    def test_record_position_net_exposure_decimal(self, engine):
        pos = engine.record_position("GBP/EUR", Decimal("100000"), Decimal("80000"))
        assert isinstance(pos.net_exposure, Decimal)

    def test_record_position_long_short_decimal(self, engine):
        pos = engine.record_position("GBP/USD", Decimal("50000"), Decimal("30000"))
        assert isinstance(pos.net_long, Decimal)
        assert isinstance(pos.net_short, Decimal)

    def test_record_position_negative_exposure(self, engine):
        pos = engine.record_position("GBP/EUR", Decimal("50000"), Decimal("100000"))
        assert pos.net_exposure == Decimal("-50000")

    def test_record_position_zero_exposure(self, engine):
        pos = engine.record_position("GBP/EUR", Decimal("50000"), Decimal("50000"))
        assert pos.net_exposure == Decimal("0")

    def test_record_position_snapshot_date_utc(self, engine):
        pos = engine.record_position("GBP/EUR", Decimal("1000"), Decimal("0"))
        assert pos.snapshot_date  # UTC timestamp

    def test_record_position_id_starts_hp(self, engine):
        pos = engine.record_position("GBP/EUR", Decimal("1000"), Decimal("0"))
        assert pos.position_id.startswith("hp_")


class TestGetNetExposure:
    def test_get_net_exposure_after_record(self, engine):
        engine.record_position("GBP/EUR", Decimal("100000"), Decimal("80000"))
        exposure = engine.get_net_exposure("GBP/EUR")
        assert exposure == Decimal("20000")

    def test_get_net_exposure_zero_if_no_position(self, engine):
        exposure = engine.get_net_exposure("GBP/CHF")
        assert exposure == Decimal("0")

    def test_get_net_exposure_is_decimal(self, engine):
        engine.record_position("EUR/USD", Decimal("50000"), Decimal("20000"))
        exposure = engine.get_net_exposure("EUR/USD")
        assert isinstance(exposure, Decimal)


class TestCheckThreshold:
    def test_below_threshold_no_hitl(self, engine):
        engine.record_position("GBP/EUR", Decimal("100000"), Decimal("80000"))
        result = engine.check_threshold("GBP/EUR")
        assert result is None

    def test_at_threshold_hitl(self, engine):
        engine.record_position("GBP/EUR", Decimal("500000"), Decimal("0"))
        result = engine.check_threshold("GBP/EUR")
        assert isinstance(result, HITLProposal)
        assert result.autonomy_level == "L4"

    def test_above_threshold_hitl(self, engine):
        engine.record_position("GBP/EUR", Decimal("1000000"), Decimal("0"))
        result = engine.check_threshold("GBP/EUR")
        assert isinstance(result, HITLProposal)

    def test_negative_exposure_above_threshold_hitl(self, engine):
        # Net short position
        engine.record_position("GBP/EUR", Decimal("0"), Decimal("600000"))
        result = engine.check_threshold("GBP/EUR")
        assert isinstance(result, HITLProposal)

    def test_threshold_constant(self):
        assert Decimal("500000") == HEDGE_ALERT_THRESHOLD_GBP

    def test_hitl_requires_treasury_ops(self, engine):
        engine.record_position("GBP/EUR", Decimal("600000"), Decimal("0"))
        result = engine.check_threshold("GBP/EUR")
        assert result is not None
        assert result.requires_approval_from == "TREASURY_OPS"


class TestTakeEODSnapshot:
    def test_eod_snapshot_returns_list(self, engine):
        engine.record_position("GBP/EUR", Decimal("100000"), Decimal("80000"))
        snapshots = engine.take_eod_snapshot()
        assert isinstance(snapshots, list)
        assert len(snapshots) >= 1

    def test_eod_snapshot_empty_with_no_positions(self, engine):
        snapshots = engine.take_eod_snapshot()
        assert snapshots == []


class TestGetHedgingSummary:
    def test_summary_structure(self, engine):
        engine.record_position("GBP/EUR", Decimal("100000"), Decimal("80000"))
        summary = engine.get_hedging_summary()
        assert "pairs" in summary
        assert "total_long" in summary
        assert "total_short" in summary
        assert "alert_count" in summary

    def test_summary_total_long_decimal(self, engine):
        engine.record_position("GBP/EUR", Decimal("100000"), Decimal("80000"))
        summary = engine.get_hedging_summary()
        assert isinstance(summary["total_long"], Decimal)

    def test_summary_alert_count_above_threshold(self, engine):
        engine.record_position("GBP/EUR", Decimal("600000"), Decimal("0"))
        summary = engine.get_hedging_summary()
        assert summary["alert_count"] >= 1
