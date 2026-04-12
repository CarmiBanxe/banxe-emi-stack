"""
tests/test_transaction_monitor/test_risk_scorer.py
IL-RTM-01 | banxe-emi-stack

Tests for RiskScorer pipeline: hard-block, high-amount, velocity threshold,
IMPROVING vs REGRESSING, weighted aggregation.
"""

from __future__ import annotations

from decimal import Decimal

from services.transaction_monitor.models.transaction import TransactionEvent, TransactionType
from services.transaction_monitor.scoring.risk_scorer import RiskScorer
from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker


def _make_event(
    amount: str = "1000.00",
    sender_jurisdiction: str = "GB",
    receiver_jurisdiction: str | None = None,
    transaction_type: TransactionType = TransactionType.PAYMENT,
    metadata: dict | None = None,
    customer_avg: str | None = None,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=f"TXN-{sender_jurisdiction}-{amount}",
        amount=Decimal(amount),
        sender_id="cust-score-test",
        sender_jurisdiction=sender_jurisdiction,
        receiver_jurisdiction=receiver_jurisdiction,
        transaction_type=transaction_type,
        metadata=metadata or {},
        customer_avg_amount=Decimal(customer_avg) if customer_avg else None,
    )


class TestRiskScorerHardBlock:
    def test_russian_jurisdiction_scores_critical(self):
        scorer = RiskScorer()
        event = _make_event(sender_jurisdiction="RU")
        rs = scorer.score(event)
        assert rs.score == 1.0
        assert rs.classification == "critical"

    def test_iranian_jurisdiction_scores_critical(self):
        scorer = RiskScorer()
        event = _make_event(sender_jurisdiction="IR")
        rs = scorer.score(event)
        assert rs.score == 1.0
        assert rs.classification == "critical"

    def test_hard_block_factor_included(self):
        scorer = RiskScorer()
        event = _make_event(sender_jurisdiction="KP")
        rs = scorer.score(event)
        factor_names = [f.name for f in rs.factors]
        assert "jurisdiction_hard_block" in factor_names


class TestRiskScorerScoring:
    def test_safe_transaction_scores_low(self):
        scorer = RiskScorer(velocity_tracker=InMemoryVelocityTracker())
        event = _make_event(amount="100.00", sender_jurisdiction="GB")
        rs = scorer.score(event)
        assert rs.score < 0.80  # Should not be critical for safe transaction

    def test_high_amount_deviation_increases_score(self):
        scorer = RiskScorer(velocity_tracker=InMemoryVelocityTracker())
        # Amount 9x above average
        high = _make_event(amount="9000.00", customer_avg="1000.00")
        low = _make_event(amount="500.00", customer_avg="1000.00")
        high_score = scorer.score(high)
        low_score = scorer.score(low)
        assert high_score.score > low_score.score

    def test_crypto_onramp_increases_score(self):
        scorer = RiskScorer(velocity_tracker=InMemoryVelocityTracker())
        crypto = _make_event(
            amount="5000.00",
            transaction_type=TransactionType.CRYPTO_ONRAMP,
        )
        regular = _make_event(
            amount="5000.00",
            transaction_type=TransactionType.PAYMENT,
        )
        assert scorer.score(crypto).score > scorer.score(regular).score

    def test_round_amount_contributes_to_score(self):
        scorer = RiskScorer(velocity_tracker=InMemoryVelocityTracker())
        round_txn = _make_event(amount="10000.00")
        odd_txn = _make_event(amount="10047.23")
        assert scorer.score(round_txn).score >= scorer.score(odd_txn).score

    def test_velocity_tracker_incremented_after_scoring(self):
        tracker = InMemoryVelocityTracker()
        scorer = RiskScorer(velocity_tracker=tracker)
        event = _make_event(amount="500.00", sender_jurisdiction="GB")
        scorer.score(event)
        assert tracker.get_count("cust-score-test", "24h") == 1

    def test_cross_border_high_risk_increases_score(self):
        scorer = RiskScorer(velocity_tracker=InMemoryVelocityTracker())
        cross = _make_event(sender_jurisdiction="GB", receiver_jurisdiction="AE")
        domestic = _make_event(sender_jurisdiction="GB", receiver_jurisdiction="GB")
        cross_score = scorer.score(cross)
        domestic_score = scorer.score(domestic)
        assert cross_score.score >= domestic_score.score
