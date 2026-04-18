"""
services/risk_management/threshold_manager.py
IL-RMS-01 | Phase 37 | banxe-emi-stack

Threshold Manager — get/set thresholds, breach detection, alert generation.
I-27: Threshold changes ALWAYS return HITLProposal.
I-01: All scores as Decimal.
"""

from __future__ import annotations

from decimal import Decimal

from services.risk_management.models import (
    RiskCategory,
    RiskScore,
    RiskThreshold,
)
from services.risk_management.risk_agent import HITLProposal

DEFAULT_THRESHOLDS: dict[RiskCategory, RiskThreshold] = {
    RiskCategory.AML: RiskThreshold(
        RiskCategory.AML, Decimal("25"), Decimal("50"), Decimal("75"), True
    ),
    RiskCategory.CREDIT: RiskThreshold(
        RiskCategory.CREDIT, Decimal("25"), Decimal("50"), Decimal("75"), True
    ),
    RiskCategory.OPERATIONAL: RiskThreshold(
        RiskCategory.OPERATIONAL, Decimal("25"), Decimal("50"), Decimal("75"), False
    ),
    RiskCategory.FRAUD: RiskThreshold(
        RiskCategory.FRAUD, Decimal("25"), Decimal("50"), Decimal("75"), True
    ),
    RiskCategory.MARKET: RiskThreshold(
        RiskCategory.MARKET, Decimal("25"), Decimal("50"), Decimal("75"), False
    ),
    RiskCategory.LIQUIDITY: RiskThreshold(
        RiskCategory.LIQUIDITY, Decimal("25"), Decimal("50"), Decimal("75"), True
    ),
    RiskCategory.REPUTATIONAL: RiskThreshold(
        RiskCategory.REPUTATIONAL, Decimal("25"), Decimal("50"), Decimal("75"), False
    ),
}


class ThresholdManager:
    """Manages risk thresholds; threshold changes are always HITL-gated (I-27)."""

    def __init__(self) -> None:
        self._thresholds: dict[RiskCategory, RiskThreshold] = dict(DEFAULT_THRESHOLDS)

    def get_threshold(self, category: RiskCategory) -> RiskThreshold:
        """Return threshold for a given category."""
        return self._thresholds[category]

    def set_threshold(self, category: RiskCategory, threshold: RiskThreshold) -> HITLProposal:
        """Propose a threshold change — ALWAYS returns HITL proposal (I-27)."""
        return HITLProposal(
            action="set_threshold",
            resource_id=category.value,
            requires_approval_from="Risk Officer",
            reason=(
                f"Threshold change for {category.value}: "
                f"LOW<={threshold.low_max}, MEDIUM<={threshold.medium_max}, "
                f"HIGH<={threshold.high_max}"
            ),
            autonomy_level="L4",
        )

    def check_breach(self, score: RiskScore) -> bool:
        """Return True if the score breaches the HIGH threshold for its category."""
        threshold = self._thresholds.get(score.category)
        if threshold is None:
            return False
        return score.score >= threshold.high_max

    def get_alerts(self, scores: list[RiskScore]) -> list[dict]:
        """Return list of breach alerts for scores exceeding HIGH threshold."""
        alerts = []
        for s in scores:
            threshold = self._thresholds.get(s.category)
            if threshold is None or not threshold.alert_on_breach:
                continue
            if s.score >= threshold.high_max:
                alerts.append(
                    {
                        "entity_id": s.entity_id,
                        "category": s.category.value,
                        "score": str(s.score),
                        "level": s.level.value,
                        "threshold_breached": str(threshold.high_max),
                        "alert_on_breach": threshold.alert_on_breach,
                    }
                )
        return alerts

    def list_thresholds(self) -> dict[str, dict]:
        """Return all thresholds serialised."""
        return {
            cat.value: {
                "category": cat.value,
                "low_max": str(t.low_max),
                "medium_max": str(t.medium_max),
                "high_max": str(t.high_max),
                "alert_on_breach": t.alert_on_breach,
            }
            for cat, t in self._thresholds.items()
        }
