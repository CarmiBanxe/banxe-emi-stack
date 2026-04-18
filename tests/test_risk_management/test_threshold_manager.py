"""
tests/test_risk_management/test_threshold_manager.py
IL-RMS-01 | Phase 37 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

from decimal import Decimal

from services.risk_management.models import (
    InMemoryRiskScorePort,
    RiskCategory,
    RiskLevel,
    RiskThreshold,
    ScoreModel,
)
from services.risk_management.risk_agent import HITLProposal
from services.risk_management.risk_scorer import RiskScorer
from services.risk_management.threshold_manager import ThresholdManager


def _mgr() -> ThresholdManager:
    return ThresholdManager()


class TestGetThreshold:
    def test_returns_threshold_for_aml(self) -> None:
        mgr = _mgr()
        t = mgr.get_threshold(RiskCategory.AML)
        assert t.category == RiskCategory.AML

    def test_low_max_is_decimal(self) -> None:
        mgr = _mgr()
        t = mgr.get_threshold(RiskCategory.CREDIT)
        assert isinstance(t.low_max, Decimal)

    def test_all_categories_have_thresholds(self) -> None:
        mgr = _mgr()
        for cat in RiskCategory:
            t = mgr.get_threshold(cat)
            assert t is not None

    def test_default_aml_high_max_is_75(self) -> None:
        mgr = _mgr()
        t = mgr.get_threshold(RiskCategory.AML)
        assert t.high_max == Decimal("75")


class TestSetThreshold:
    def test_always_returns_hitl_proposal(self) -> None:
        mgr = _mgr()
        threshold = RiskThreshold(
            RiskCategory.AML, Decimal("20"), Decimal("45"), Decimal("70"), True
        )
        result = mgr.set_threshold(RiskCategory.AML, threshold)
        assert isinstance(result, HITLProposal)

    def test_hitl_status(self) -> None:
        mgr = _mgr()
        threshold = RiskThreshold(
            RiskCategory.FRAUD, Decimal("20"), Decimal("45"), Decimal("70"), True
        )
        result = mgr.set_threshold(RiskCategory.FRAUD, threshold)
        assert result.autonomy_level == "L4"

    def test_hitl_requires_risk_officer(self) -> None:
        mgr = _mgr()
        threshold = RiskThreshold(
            RiskCategory.CREDIT, Decimal("20"), Decimal("45"), Decimal("70"), True
        )
        result = mgr.set_threshold(RiskCategory.CREDIT, threshold)
        assert "Risk Officer" in result.requires_approval_from

    def test_hitl_resource_id_is_category(self) -> None:
        mgr = _mgr()
        threshold = RiskThreshold(
            RiskCategory.MARKET, Decimal("20"), Decimal("45"), Decimal("70"), False
        )
        result = mgr.set_threshold(RiskCategory.MARKET, threshold)
        assert result.resource_id == "MARKET"


class TestCheckBreach:
    def test_breach_at_high_max(self) -> None:
        mgr = _mgr()
        store = InMemoryRiskScorePort()
        store._scores.clear()
        scorer = RiskScorer(store)
        s = scorer.score_entity("e-1", {"f": Decimal("999")}, RiskCategory.AML)
        assert mgr.check_breach(s) is True

    def test_no_breach_below_high(self) -> None:
        mgr = _mgr()
        store = InMemoryRiskScorePort()
        store._scores.clear()
        scorer = RiskScorer(store)
        s = scorer.score_entity("e-1", {"f": Decimal("1")}, RiskCategory.AML)
        assert mgr.check_breach(s) is False

    def test_exactly_at_high_max(self) -> None:
        mgr = _mgr()
        store = InMemoryRiskScorePort()
        store._scores.clear()
        scorer = RiskScorer(store)
        # Force a score manually
        from datetime import UTC, datetime

        from services.risk_management.models import RiskScore

        s = RiskScore(
            entity_id="e-1",
            category=RiskCategory.AML,
            score=Decimal("75"),
            level=RiskLevel.CRITICAL,
            model=ScoreModel.RULE_BASED,
            factors={},
            assessed_at=datetime.now(UTC),
            assessed_by="test",
        )
        assert mgr.check_breach(s) is True


class TestGetAlerts:
    def test_returns_alert_for_breach(self) -> None:
        mgr = _mgr()
        from datetime import UTC, datetime

        from services.risk_management.models import RiskScore

        s = RiskScore(
            entity_id="e-breach",
            category=RiskCategory.AML,
            score=Decimal("80"),
            level=RiskLevel.CRITICAL,
            model=ScoreModel.RULE_BASED,
            factors={},
            assessed_at=datetime.now(UTC),
            assessed_by="test",
        )
        alerts = mgr.get_alerts([s])
        assert len(alerts) == 1

    def test_no_alert_below_threshold(self) -> None:
        mgr = _mgr()
        from datetime import UTC, datetime

        from services.risk_management.models import RiskScore

        s = RiskScore(
            entity_id="e-low",
            category=RiskCategory.AML,
            score=Decimal("10"),
            level=RiskLevel.LOW,
            model=ScoreModel.RULE_BASED,
            factors={},
            assessed_at=datetime.now(UTC),
            assessed_by="test",
        )
        alerts = mgr.get_alerts([s])
        assert len(alerts) == 0

    def test_no_alert_for_non_alert_category(self) -> None:
        mgr = _mgr()
        from datetime import UTC, datetime

        from services.risk_management.models import RiskScore

        s = RiskScore(
            entity_id="e-op",
            category=RiskCategory.OPERATIONAL,
            score=Decimal("90"),
            level=RiskLevel.CRITICAL,
            model=ScoreModel.RULE_BASED,
            factors={},
            assessed_at=datetime.now(UTC),
            assessed_by="test",
        )
        alerts = mgr.get_alerts([s])
        assert len(alerts) == 0

    def test_alert_contains_entity_id(self) -> None:
        mgr = _mgr()
        from datetime import UTC, datetime

        from services.risk_management.models import RiskScore

        s = RiskScore(
            entity_id="e-target",
            category=RiskCategory.FRAUD,
            score=Decimal("90"),
            level=RiskLevel.CRITICAL,
            model=ScoreModel.RULE_BASED,
            factors={},
            assessed_at=datetime.now(UTC),
            assessed_by="test",
        )
        alerts = mgr.get_alerts([s])
        assert alerts[0]["entity_id"] == "e-target"
