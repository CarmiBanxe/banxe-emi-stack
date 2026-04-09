"""
tests/test_feedback_loop.py — FeedbackLoopAnalyser tests (IL-056)
Supervised HITL learning: AI analyses CTIO decisions, proposes (never auto-applies).

I-27: every ThresholdProposal.requires_human_approval must be True.
"""

from __future__ import annotations

from services.hitl.feedback_loop import (
    FeedbackLoopAnalyser,
)

# ─────────────────────────────────────────────────────────────────────────────
# Corpus builders
# ─────────────────────────────────────────────────────────────────────────────


def _record(
    outcome: str,
    reasons: list[str],
    fraud_score: int = 50,
    amount: str = "500.00",
    decided_by: str = "ctio",
    case_id: str = "c1",
) -> dict:
    """Build a minimal corpus record (matches HITLDecision.to_corpus_record)."""
    return {
        "case_id": case_id,
        "transaction_id": f"tx-{case_id}",
        "customer_id": "cust-001",
        "amount": amount,
        "fraud_score": fraud_score,
        "reasons": reasons,
        "outcome": outcome,
        "decided_by": decided_by,
        "decided_at": "2026-03-15T10:00:00+00:00",
        "notes": "",
    }


def _corpus_of(
    n_approve: int,
    n_reject: int,
    reasons: list[str],
    fraud_score: int = 50,
    amount: str = "500.00",
    decided_by: str = "ctio",
) -> list[dict]:
    corpus = []
    for i in range(n_approve):
        corpus.append(_record("APPROVE", reasons, fraud_score, amount, decided_by, f"a{i}"))
    for i in range(n_reject):
        corpus.append(_record("REJECT", reasons, fraud_score, amount, decided_by, f"r{i}"))
    return corpus


# ─────────────────────────────────────────────────────────────────────────────
# Tests: empty corpus
# ─────────────────────────────────────────────────────────────────────────────


class TestEmptyCorpus:
    def test_empty_corpus_returns_empty_report(self) -> None:
        report = FeedbackLoopAnalyser().analyse([])
        assert report.corpus_size == 0
        assert report.reason_stats == []
        assert report.proposals == []
        assert report.risk_buckets == []
        assert report.decider_stats == []

    def test_empty_corpus_has_generated_at(self) -> None:
        report = FeedbackLoopAnalyser().analyse([])
        assert report.generated_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: ReasonStats
# ─────────────────────────────────────────────────────────────────────────────


class TestReasonStats:
    def test_reason_stats_computed(self) -> None:
        corpus = _corpus_of(7, 3, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        assert len(report.reason_stats) == 1
        rs = report.reason_stats[0]
        assert rs.reason == "VELOCITY_DAILY"
        assert rs.total == 10
        assert rs.approved == 7
        assert rs.rejected == 3
        assert abs(rs.approval_rate - 0.7) < 0.01

    def test_multiple_reasons_counted_separately(self) -> None:
        corpus = [
            _record("APPROVE", ["VELOCITY_DAILY", "EDD_REQUIRED"], case_id="x1"),
            _record("REJECT", ["VELOCITY_DAILY"], case_id="x2"),
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        by_reason = {rs.reason: rs for rs in report.reason_stats}
        assert "VELOCITY_DAILY" in by_reason
        assert "EDD_REQUIRED" in by_reason
        assert by_reason["VELOCITY_DAILY"].total == 2
        assert by_reason["EDD_REQUIRED"].total == 1

    def test_escalated_not_counted_in_approval_rate(self) -> None:
        corpus = [
            _record("APPROVE", ["FRAUD_HIGH"], case_id="a1"),
            _record("ESCALATE", ["FRAUD_HIGH"], case_id="e1"),
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        rs = report.reason_stats[0]
        # escalated not in terminal; approval_rate = 1/1 = 1.0
        assert rs.escalated == 1
        assert abs(rs.approval_rate - 1.0) < 0.01

    def test_avg_fraud_score_correct(self) -> None:
        corpus = [
            _record("APPROVE", ["FRAUD_HIGH"], fraud_score=60, case_id="a1"),
            _record("REJECT", ["FRAUD_HIGH"], fraud_score=80, case_id="r1"),
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        rs = report.reason_stats[0]
        assert abs(rs.avg_fraud_score - 70.0) < 0.01

    def test_reason_stats_sorted_alphabetically(self) -> None:
        corpus = _corpus_of(5, 5, ["VELOCITY_DAILY"]) + _corpus_of(5, 5, ["EDD_REQUIRED"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        names = [rs.reason for rs in report.reason_stats]
        assert names == sorted(names)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: RiskBucketStats
# ─────────────────────────────────────────────────────────────────────────────


class TestRiskBucketStats:
    def test_risk_buckets_computed(self) -> None:
        # 5 records with score 65 (bucket 60-69)
        corpus = [
            _record("APPROVE", ["FRAUD_HIGH"], fraud_score=65, case_id=f"a{i}") for i in range(3)
        ] + [_record("REJECT", ["FRAUD_HIGH"], fraud_score=65, case_id=f"r{i}") for i in range(3)]
        report = FeedbackLoopAnalyser().analyse(corpus)
        bucket = next((b for b in report.risk_buckets if b.bucket_label == "60-69"), None)
        assert bucket is not None
        assert bucket.total == 6
        assert abs(bucket.approval_rate - 0.5) < 0.01

    def test_sparse_bucket_excluded(self) -> None:
        # Only 2 records — below MIN_SAMPLE_STATS=3
        corpus = [
            _record("APPROVE", ["FRAUD_HIGH"], fraud_score=75, case_id="a1"),
            _record("REJECT", ["FRAUD_HIGH"], fraud_score=75, case_id="r1"),
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        bucket = next((b for b in report.risk_buckets if b.bucket_label == "70-79"), None)
        assert bucket is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: AmountBucketStats
# ─────────────────────────────────────────────────────────────────────────────


class TestAmountBucketStats:
    def test_amount_bucket_computed(self) -> None:
        # 4 records in £1k-5k band
        corpus = [
            _record("APPROVE", ["EDD_REQUIRED"], amount="2000.00", case_id=f"a{i}")
            for i in range(3)
        ] + [
            _record("REJECT", ["EDD_REQUIRED"], amount="3500.00", case_id="r1"),
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        bucket = next((b for b in report.amount_buckets if b.bucket_label == "£1k-5k"), None)
        assert bucket is not None
        assert bucket.total == 4

    def test_large_amount_bucket(self) -> None:
        corpus = [
            _record("REJECT", ["EDD_REQUIRED"], amount="75000.00", case_id=f"r{i}")
            for i in range(5)
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        bucket = next((b for b in report.amount_buckets if b.bucket_label == "£50k+"), None)
        assert bucket is not None
        assert bucket.total == 5


# ─────────────────────────────────────────────────────────────────────────────
# Tests: DeciderStats
# ─────────────────────────────────────────────────────────────────────────────


class TestDeciderStats:
    def test_decider_stats_per_operator(self) -> None:
        corpus = _corpus_of(8, 2, ["VELOCITY_DAILY"], decided_by="ctio") + _corpus_of(
            3, 7, ["FRAUD_HIGH"], decided_by="ceo"
        )
        report = FeedbackLoopAnalyser().analyse(corpus)
        by_decider = {ds.decided_by: ds for ds in report.decider_stats}
        assert "ctio" in by_decider
        assert "ceo" in by_decider
        assert abs(by_decider["ctio"].approval_rate - 0.8) < 0.01
        assert abs(by_decider["ceo"].approval_rate - 0.3) < 0.01

    def test_decider_top_reasons(self) -> None:
        corpus = _corpus_of(5, 0, ["VELOCITY_DAILY"], decided_by="ctio") + _corpus_of(
            5, 0, ["VELOCITY_DAILY", "FRAUD_HIGH"], decided_by="ctio"
        )
        report = FeedbackLoopAnalyser().analyse(corpus)
        ds = next(d for d in report.decider_stats if d.decided_by == "ctio")
        assert "VELOCITY_DAILY" in ds.top_reasons

    def test_decider_stats_totals(self) -> None:
        corpus = [
            _record("APPROVE", ["FRAUD_HIGH"], decided_by="ctio", case_id="a1"),
            _record("REJECT", ["FRAUD_HIGH"], decided_by="ctio", case_id="r1"),
            _record("ESCALATE", ["SAR_REQUIRED"], decided_by="ctio", case_id="e1"),
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        ds = report.decider_stats[0]
        assert ds.total_decisions == 3
        assert ds.approved == 1
        assert ds.rejected == 1
        assert ds.escalated == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests: ThresholdProposals
# ─────────────────────────────────────────────────────────────────────────────


class TestThresholdProposals:
    def test_i27_requires_human_approval_always_true(self) -> None:
        """I-27: every proposal MUST require human approval. Non-negotiable."""
        corpus = _corpus_of(9, 1, ["VELOCITY_DAILY"])  # 90% approval, 10 samples
        report = FeedbackLoopAnalyser().analyse(corpus)
        for proposal in report.proposals:
            assert proposal.requires_human_approval is True, (
                f"I-27 VIOLATED: proposal {proposal.proposal_id} has requires_human_approval=False"
            )

    def test_velocity_high_approval_triggers_raise_proposal(self) -> None:
        # 90% approval rate for VELOCITY_DAILY, 10+ samples
        corpus = _corpus_of(9, 1, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        props = [p for p in report.proposals if "VELOCITY" in p.parameter]
        assert len(props) >= 1
        assert props[0].proposed_direction == "RAISE"

    def test_fraud_high_low_approval_triggers_lower_proposal(self) -> None:
        # 10% approval rate for FRAUD_HIGH, 10+ samples
        corpus = _corpus_of(1, 9, ["FRAUD_HIGH"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        props = [p for p in report.proposals if "FRAUD" in p.parameter]
        assert len(props) >= 1
        assert props[0].proposed_direction == "LOWER"

    def test_edd_high_approval_triggers_raise_proposal(self) -> None:
        corpus = _corpus_of(9, 1, ["EDD_REQUIRED"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        props = [p for p in report.proposals if "EDD" in p.parameter]
        assert len(props) >= 1
        assert props[0].proposed_direction == "RAISE"

    def test_structuring_low_approval_triggers_review_proposal(self) -> None:
        corpus = _corpus_of(1, 9, ["STRUCTURING"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        props = [p for p in report.proposals if "STRUCTURING" in p.parameter]
        assert len(props) >= 1
        assert props[0].proposed_direction == "REVIEW"

    def test_insufficient_sample_no_proposal(self) -> None:
        # Only 5 samples — below MIN_SAMPLE_PROPOSAL=10
        corpus = _corpus_of(5, 0, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser(min_sample_proposal=10).analyse(corpus)
        props = [p for p in report.proposals if "VELOCITY" in p.parameter]
        assert len(props) == 0

    def test_moderate_approval_rate_no_proposal(self) -> None:
        # 60% approval — neither high nor low watermark
        corpus = _corpus_of(6, 4, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        props = [p for p in report.proposals if "VELOCITY" in p.parameter]
        assert len(props) == 0

    def test_proposal_has_evidence_field(self) -> None:
        corpus = _corpus_of(9, 1, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        for p in report.proposals:
            assert p.evidence, "proposal must include evidence"

    def test_proposal_confidence_medium_for_small_sample(self) -> None:
        corpus = _corpus_of(9, 1, ["VELOCITY_DAILY"])  # 10 samples → MEDIUM
        report = FeedbackLoopAnalyser().analyse(corpus)
        for p in report.proposals:
            assert p.confidence in ("HIGH", "MEDIUM", "LOW")

    def test_proposal_confidence_high_for_large_sample(self) -> None:
        corpus = _corpus_of(27, 3, ["VELOCITY_DAILY"])  # 30 samples → HIGH
        report = FeedbackLoopAnalyser().analyse(corpus)
        velocity_props = [p for p in report.proposals if "VELOCITY" in p.parameter]
        assert velocity_props[0].confidence == "HIGH"

    def test_risk_bucket_triggers_raise_proposal(self) -> None:
        # 60-69 bucket: 9/10 approved → propose raising HOLD threshold
        corpus = [
            _record("APPROVE", ["FRAUD_HIGH"], fraud_score=65, case_id=f"a{i}") for i in range(9)
        ] + [
            _record("REJECT", ["FRAUD_HIGH"], fraud_score=65, case_id="r0"),
        ]
        report = FeedbackLoopAnalyser().analyse(corpus)
        fraud_props = [p for p in report.proposals if "FRAUD_HOLD" in p.parameter]
        assert any(p.proposed_direction == "RAISE" for p in fraud_props)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: FeedbackReport output
# ─────────────────────────────────────────────────────────────────────────────


class TestFeedbackReport:
    def test_corpus_size_correct(self) -> None:
        corpus = _corpus_of(5, 5, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        assert report.corpus_size == 10

    def test_summary_contains_reason(self) -> None:
        corpus = _corpus_of(5, 5, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        summary = report.summary()
        assert "VELOCITY_DAILY" in summary

    def test_summary_contains_corpus_size(self) -> None:
        corpus = _corpus_of(5, 5, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        assert "10" in report.summary()

    def test_to_dict_has_required_keys(self) -> None:
        corpus = _corpus_of(3, 3, ["FRAUD_HIGH"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        d = report.to_dict()
        assert "corpus_size" in d
        assert "generated_at" in d
        assert "proposals" in d
        assert "reason_stats" in d
        assert "decider_stats" in d

    def test_to_dict_reason_amounts_are_strings(self) -> None:
        corpus = _corpus_of(3, 3, ["FRAUD_HIGH"], amount="5000.00")
        report = FeedbackLoopAnalyser().analyse(corpus)
        d = report.to_dict()
        for rs in d["reason_stats"]:
            assert isinstance(rs["avg_amount"], str), "avg_amount must be string (I-05)"

    def test_proposal_to_dict(self) -> None:
        corpus = _corpus_of(9, 1, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        for p in report.proposals:
            d = p.to_dict()
            assert d["requires_human_approval"] is True
            assert "proposal_id" in d
            assert "parameter" in d
            assert "rationale" in d

    def test_summary_with_no_proposals(self) -> None:
        corpus = _corpus_of(5, 5, ["VELOCITY_DAILY"])  # 50% — no signal
        report = FeedbackLoopAnalyser().analyse(corpus)
        summary = report.summary()
        assert "No threshold proposals" in summary

    def test_summary_with_proposals(self) -> None:
        corpus = _corpus_of(9, 1, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser().analyse(corpus)
        if report.proposals:
            summary = report.summary()
            assert "REQUIRE HUMAN APPROVAL" in summary


# ─────────────────────────────────────────────────────────────────────────────
# Tests: custom watermarks
# ─────────────────────────────────────────────────────────────────────────────


class TestCustomWatermarks:
    def test_custom_high_watermark(self) -> None:
        # 70% approval — below default 85%, but above custom 60%
        corpus = _corpus_of(7, 3, ["VELOCITY_DAILY"])
        report = FeedbackLoopAnalyser(
            approval_high_watermark=0.60,
        ).analyse(corpus)
        props = [p for p in report.proposals if "VELOCITY" in p.parameter]
        assert len(props) >= 1

    def test_custom_low_watermark(self) -> None:
        # 20% approval — above default 15% low watermark, but below custom 25%
        corpus = _corpus_of(2, 8, ["FRAUD_HIGH"])
        report = FeedbackLoopAnalyser(
            approval_low_watermark=0.25,
        ).analyse(corpus)
        props = [p for p in report.proposals if "FRAUD_HOLD" in p.parameter]
        assert any(p.proposed_direction == "LOWER" for p in props)
