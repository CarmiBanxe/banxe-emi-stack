"""
tests/test_transaction_monitor/test_explanation_engine.py
IL-RTM-01 | banxe-emi-stack

Tests for ExplanationEngine: explanation generation, KB citation inclusion,
regulation refs extraction, recommendation per classification.
"""

from __future__ import annotations

from decimal import Decimal

from services.transaction_monitor.alerts.explanation_engine import (
    ExplanationEngine,
    InMemoryKBPort,
)
from services.transaction_monitor.models.risk_score import RiskFactor, RiskScore
from services.transaction_monitor.models.transaction import TransactionEvent


def _make_event_with_amount(amount: str = "5000.00") -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-EXP-001",
        amount=Decimal(amount),
        sender_id="cust-001",
        sender_jurisdiction="GB",
    )


def _make_risk_score(score: float, with_reg_ref: bool = True) -> RiskScore:
    factors = [
        RiskFactor(
            name="velocity_24h",
            weight=0.30,
            value=0.80,
            contribution=0.24,
            explanation="Transaction count exceeds 24h threshold.",
            regulation_ref="EBA GL/2021/02 §4.2" if with_reg_ref else None,
        )
    ]
    return RiskScore(score=score, factors=factors)


class TestExplanationEngine:
    def setup_method(self):
        self.engine = ExplanationEngine(kb_port=InMemoryKBPort())

    def test_generate_includes_transaction_id(self):
        event = _make_event_with_amount()
        rs = _make_risk_score(0.75)
        explanation = self.engine.generate(event, rs, ["EBA GL/2021/02 §4.2"])
        assert "TXN-EXP-001" in explanation

    def test_generate_includes_risk_score(self):
        event = _make_event_with_amount()
        rs = _make_risk_score(0.75)
        explanation = self.engine.generate(event, rs, [])
        assert "0.75" in explanation

    def test_generate_includes_risk_factor_name(self):
        event = _make_event_with_amount()
        rs = _make_risk_score(0.70)
        explanation = self.engine.generate(event, rs, [])
        assert "velocity_24h" in explanation

    def test_generate_includes_regulation_ref(self):
        event = _make_event_with_amount()
        rs = _make_risk_score(0.70, with_reg_ref=True)
        explanation = self.engine.generate(event, rs, ["EBA GL/2021/02 §4.2"])
        assert "EBA" in explanation

    def test_recommendation_critical_says_escalate(self):
        event = _make_event_with_amount()
        rs = _make_risk_score(0.85)
        explanation = self.engine.generate(event, rs, [])
        assert "ESCALATE" in explanation.upper()

    def test_recommendation_low_says_auto_close(self):
        event = _make_event_with_amount()
        rs = RiskScore(score=0.10)
        explanation = self.engine.generate(event, rs, [])
        assert "AUTO-CLOSE" in explanation.upper() or "auto-close" in explanation.lower()

    def test_extract_regulation_refs_from_factors(self):
        rs = _make_risk_score(0.75, with_reg_ref=True)
        refs = self.engine.extract_regulation_refs(rs)
        assert "EBA GL/2021/02 §4.2" in refs

    def test_extract_regulation_refs_empty_when_none(self):
        rs = _make_risk_score(0.50, with_reg_ref=False)
        refs = self.engine.extract_regulation_refs(rs)
        assert refs == []
